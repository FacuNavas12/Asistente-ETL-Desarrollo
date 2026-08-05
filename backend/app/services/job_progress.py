"""
D29 (docs/refactor/02-decisiones.md): progreso observable del job async de
generación de ETL.

Dos piezas:
1. `emit()` / `ProgressSink` — escritor de KtrBuildJob.progress_json. Sesión de
   DB propia y corta, SIEMPRE — nunca la sesión larga de generate_etl_async
   (ver la nota junto a la columna en app/models/ktr_build_job.py). Reasigna
   la columna entera en cada escritura (no basta con mutar el dict en el
   lugar): un `obj.attr = valor` es lo que dispara el dirty-tracking de
   SQLAlchemy para una columna JSON, esté o no el dict de adentro mutado.

2. `_ProgressLogHandler` — captura los WARNING de reintento/fallback de
   gemini_llm.py y anthropic_llm.py, y el INFO de reparación por-step de
   ktr_builder/repair.py, SIN TOCAR esos tres archivos. Ruteado por un
   ContextVar: sin un ProgressSink activo (request normal, log de otro
   momento), es no-op — así jobs concurrentes no se pisan entre sí.
   `ddl_validation.py` queda deliberadamente fuera de esta whitelist: su
   información ya sale por los eventos explícitos `ddl.audit.*` que
   etl_generator.py emite alrededor de validate_and_correct_ddl(); duplicarla
   acá hubiera sido la misma información por dos caminos.

   Verificado antes de decidir: gemini_llm.py:109 corre el backoff dentro de
   `asyncio.to_thread`, que copia el `contextvars.Context` al worker thread —
   el retry sincrónico de Gemini queda cubierto igual, sin bloquear el event
   loop.

   El handler matchea el TEMPLATE crudo de record.msg (antes del %-format),
   no record.getMessage() ya renderizado — nunca reenvía texto libre del
   proveedor (puede traer fragmentos del prompt o del error real). El mensaje
   que sí se muestra se arma a mano en español a partir de record.args.
"""
from __future__ import annotations

import contextvars
import datetime as dt
import logging
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Literal, Optional, Tuple

from app.core.log_filters import PasswordFilter

_log = logging.getLogger(__name__)

_MAX_EVENTS = 120
_MAX_MSG = 240

Level = Literal["info", "warning", "error"]
StageName = Literal["job", "ddl", "origen_stg", "stg_dwh", "build"]


def _now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _truncate(message: str, limit: int = _MAX_MSG) -> str:
    if len(message) <= limit:
        return message
    return message[: limit - 1].rstrip() + "…"


def emit(
    job_id: Any,
    session_factory: Any,
    *,
    stage: StageName,
    code: str,
    message: str,
    level: Level = "info",
) -> None:
    """Sesión propia y corta. No-op silencioso si el job ya no existe (TTL lo
    barrió) — el progreso es best-effort: nunca debe tumbar la generación real.

    IMPORTANTE — por qué se arma un dict *nuevo* en cada escritura en vez de
    mutar `job.progress_json` in-place y reasignarlo: SQLAlchemy determina si
    una columna cambió comparando el objeto viejo contra el nuevo en
    `get_history()`. Si `book = job.progress_json` y después se mutan sus
    listas/dicts internos in-place, `job.progress_json = book` reasigna el
    MISMO objeto (misma identidad) — SQLAlchemy lo clasifica como "unchanged"
    y la columna queda afuera del UPDATE, así que el commit es un no-op
    silencioso. Confirmado empíricamente: con esa forma, solo el primer
    evento (None → dict) llegaba a persistir; todos los siguientes se
    perdían sin error. La lista `[*prev_events, nuevo]` de abajo crea un
    objeto nuevo siempre — mismo patrón que ya usa etl_generator.py con
    `{**(job.model_json or {}), ...}` para los checkpoints."""
    from app.models.ktr_build_job import KtrBuildJob  # import perezoso: evita ciclo de imports en arranque

    db = session_factory()
    try:
        job = db.get(KtrBuildJob, job_id)
        if job is None:
            return

        prev = job.progress_json or {"next_seq": 0, "truncated": False, "events": []}
        prev_events = prev["events"]

        if len(prev_events) >= _MAX_EVENTS:
            if not prev["truncated"]:
                seq = prev["next_seq"]
                job.progress_json = {
                    "next_seq": seq + 1,
                    "truncated": True,
                    "events": [
                        *prev_events,
                        {
                            "seq": seq, "ts": _now_iso(), "stage": "job",
                            "code": "job.progress_truncated", "level": "warning",
                            "message": "Se alcanzó el máximo de eventos de progreso mostrados.",
                        },
                    ],
                }
                db.commit()
            return

        seq = prev["next_seq"]
        job.progress_json = {
            "next_seq": seq + 1,
            "truncated": prev["truncated"],
            "events": [
                *prev_events,
                {
                    "seq": seq,
                    "ts": _now_iso(),
                    "stage": stage,
                    "code": code,
                    "level": level,
                    "message": _truncate(message),
                },
            ],
        }
        db.commit()
    except Exception:
        _log.exception("job_progress.emit: fallo no anticipado (job_id=%s, code=%s)", job_id, code)
        db.rollback()
    finally:
        db.close()


@dataclass
class ProgressSink:
    """Closure de emisión atado a un job concreto — lo que viaja en el
    ContextVar. `current_stage` lo va moviendo generate_etl_async a medida
    que avanza el pipeline, para que el handler de logs (que no conoce en
    qué etapa está el pipeline) etiquete sus eventos correctamente."""
    job_id: Any
    session_factory: Any
    current_stage: StageName = "job"

    def emit(
        self,
        *,
        code: str,
        message: str,
        level: Level = "info",
        stage: Optional[StageName] = None,
    ) -> None:
        emit(
            self.job_id, self.session_factory,
            stage=stage or self.current_stage, code=code, message=message, level=level,
        )


_current: "contextvars.ContextVar[Optional[ProgressSink]]" = contextvars.ContextVar(
    "ktr_progress_sink", default=None
)


@contextmanager
def active_sink(sink: ProgressSink):
    token = _current.set(sink)
    try:
        yield sink
    finally:
        _current.reset(token)


def current_sink() -> Optional[ProgressSink]:
    return _current.get()


# ─── Handler de captura de reintentos (sin tocar gemini_llm.py / anthropic_llm.py / repair.py) ──

_GEMINI_RETRY = "[Gemini] Transient error (attempt %d/%d): %s — retrying in %ds"
_GEMINI_FALLBACK = "[Gemini] 400 error with response_json_schema (attempt %d) — entering text-mode fallback: %s"
_ANTHROPIC_RETRY = "[Anthropic] Transient error (attempt %d/%d): %s — retrying in %ds"
_ANTHROPIC_FALLBACK = "[Anthropic] BadRequestError with output_config (attempt %d) — entering text-mode fallback: %s"
_REPAIR_STEP_RETRY = "repair_ktr_steps: reparando '%s' (%s), intento %d/%d, faltan=%s"

_WATCHED_LOGGERS = (
    "app.models.gemini_llm",
    "app.models.anthropic_llm",
    "app.services.ktr_builder.repair",
)


def _map_record(record: logging.LogRecord) -> Optional[Tuple[str, Level, str]]:
    """Devuelve (code, level, message) o None si el record no matchea ningún
    template conocido — TODO record que no matchee se descarta, nunca se
    reenvía texto libre del logger de origen."""
    msg = record.msg
    args = record.args or ()

    if record.name in ("app.models.gemini_llm", "app.models.anthropic_llm"):
        provider = "Gemini" if record.name.endswith("gemini_llm") else "Anthropic"
        if msg in (_GEMINI_RETRY, _ANTHROPIC_RETRY):
            attempt, max_retries, _exc, wait = args
            return (
                "stage.llm.retry", "warning",
                f"El modelo ({provider}) no respondió — reintento {attempt}/{max_retries} en {wait}s",
            )
        if msg in (_GEMINI_FALLBACK, _ANTHROPIC_FALLBACK):
            return (
                "stage.llm.fallback", "warning",
                f"El modelo ({provider}) rechazó el formato estructurado — reintentando en modo texto",
            )
        return None

    if record.name == "app.services.ktr_builder.repair":
        if msg == _REPAIR_STEP_RETRY:
            step_name, canonical, attempt, max_retries, _missing = args
            return (
                "stage.repair.retry", "info",
                f"Reparando el step '{step_name}' ({canonical}) — intento {attempt}/{max_retries}",
            )
        return None

    return None


class _ProgressLogHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.INFO)
        # Redacción propia — no depender del filtro del logger root, que no
        # llega a estos records en la propagación (ver H33 en 01-hallazgos.md).
        self.addFilter(PasswordFilter())

    def emit(self, record: logging.LogRecord) -> None:
        sink = _current.get()
        if sink is None:
            return
        try:
            mapped = _map_record(record)
        except Exception:
            return
        if mapped is None:
            return
        code, level, message = mapped
        sink.emit(code=code, level=level, message=message)


_handler = _ProgressLogHandler()
for _name in _WATCHED_LOGGERS:
    logging.getLogger(_name).addHandler(_handler)
