from __future__ import annotations

"""
Two entrypoints for the drain loop — decoupled from the drain logic itself.

Entrypoint A (in-process):   run_in_process()   — asyncio task, started in FastAPI lifespan.
Entrypoint B (standalone):   run_drain_once_sync() — blocking, for CLI/cron/external process.

Switching from A to B:
  - Remove run_in_process() from lifespan in main.py.
  - Wire run_drain_once_sync() to a cron or a separate __main__ block.
  - Pieces 1 (OutboxPort) and 2 (drain()) are not touched.
"""

import asyncio
import logging
import random
from typing import Callable

from sqlalchemy.orm import Session

from app.outbox.drainer import drain
from app.outbox.port import OutboxPort

logger = logging.getLogger(__name__)

# Backoff config (seconds)
_BASE_DELAY = 5.0
_MAX_DELAY = 300.0  # 5 min ceiling
_MULTIPLIER = 2.0
_JITTER_RATIO = 0.2  # ±20 %
_MAX_ATTEMPTS = 5


def _backoff(consecutive_empty: int) -> float:
    """Exponential backoff with jitter based on consecutive idle cycles."""
    delay = min(_BASE_DELAY * (_MULTIPLIER**consecutive_empty), _MAX_DELAY)
    jitter = delay * _JITTER_RATIO * (2 * random.random() - 1)
    return max(_BASE_DELAY, delay + jitter)


async def run_in_process(outbox: OutboxPort, session_factory: Callable[[], Session]) -> None:
    """
    Entrypoint A — long-running asyncio task.

    Drain loop with exponential backoff:
    - Active queue (processed > 0): reset backoff, drain again soon.
    - Idle queue (processed == 0): back off exponentially up to _MAX_DELAY.
    - Error in drain() itself (unexpected): log + back off, never crash the loop.
    """
    consecutive_empty = 0
    logger.info("outbox.runner started (in-process)")

    while True:
        try:
            processed = await drain(outbox, session_factory, max_attempts=_MAX_ATTEMPTS)
            if processed > 0:
                consecutive_empty = 0
                delay = _BASE_DELAY
            else:
                consecutive_empty += 1
                delay = _backoff(consecutive_empty)
        except Exception:
            logger.exception("outbox.runner unexpected error in drain(); backing off")
            consecutive_empty += 1
            delay = _backoff(consecutive_empty)

        logger.debug("outbox.runner sleeping %.1fs (idle_cycles=%d)", delay, consecutive_empty)
        await asyncio.sleep(delay)


def run_drain_once_sync(outbox: OutboxPort, session_factory: Callable[[], Session]) -> int:
    """
    Entrypoint B — blocking, single-shot drain.

    Call from a cron job, a management CLI, or a separate process:

        from app.outbox.runner import run_drain_once_sync
        from app.outbox import get_outbox
        from app.core.database import _get_session_factory

        processed = run_drain_once_sync(get_outbox(), _get_session_factory())
        print(f"processed {processed} entries")
    """
    return asyncio.run(drain(outbox, session_factory, max_attempts=_MAX_ATTEMPTS))
