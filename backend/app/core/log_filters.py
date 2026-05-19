from __future__ import annotations

import logging
import re


class PasswordFilter(logging.Filter):
    """Elimina passwords de los mensajes de log antes de que sean emitidos."""

    _patterns = [
        (re.compile(r"password=[^\s&;'\"]+", re.IGNORECASE), "password=***"),
        (re.compile(r"(://[^:]+:)[^@]+(@)"), r"\1***\2"),
        (re.compile(r"PWD=[^\s;]+", re.IGNORECASE), "PWD=***"),
    ]

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self._redact(str(record.msg))
        record.args = self._redact_args(record.args)
        return True

    def _redact(self, text: str) -> str:
        for pattern, replacement in self._patterns:
            text = pattern.sub(replacement, text)
        return text

    def _redact_args(self, args):
        if isinstance(args, tuple):
            return tuple(self._redact(str(a)) if isinstance(a, str) else a for a in args)
        if isinstance(args, dict):
            return {k: self._redact(str(v)) if isinstance(v, str) else v for k, v in args.items()}
        return args
