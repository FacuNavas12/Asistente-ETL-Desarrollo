from __future__ import annotations

import re

_PATTERNS = [
    (re.compile(r"password=[^\s&;'\"]+", re.IGNORECASE), "password=***"),
    (re.compile(r"(://[^:]+:)[^@]+(@)", re.IGNORECASE), r"\1***\2"),
    (re.compile(r"PWD=[^\s;]+", re.IGNORECASE), "PWD=***"),
]

_MAX_LEN = 500


def sanitize_error(msg: str) -> str:
    """Elimina credenciales de mensajes de error antes de logguearlos."""
    for pattern, replacement in _PATTERNS:
        msg = pattern.sub(replacement, msg)
    return msg[:_MAX_LEN] if len(msg) > _MAX_LEN else msg
