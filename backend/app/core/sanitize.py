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


# Clasificación de errores de conexión (psycopg2/pyodbc, vía SQLAlchemy) a
# mensajes cortos y accionables para el usuario final. El texto técnico
# original queda solo en los logs (sanitize_error + logger.warning/error).
_CONNECTION_ERROR_PATTERNS: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"password authentication failed|login failed for user|authentication failed", re.IGNORECASE),
        "Usuario o contraseña incorrectos.",
    ),
    (
        re.compile(r"no pg_hba\.conf entry", re.IGNORECASE),
        "El servidor rechazó la conexión por política de acceso (pg_hba.conf).",
    ),
    (
        re.compile(r"could not translate host name|name or service not known|getaddrinfo failed|no such host", re.IGNORECASE),
        "No se encontró el host. Verificá la dirección.",
    ),
    (
        re.compile(r"connection refused", re.IGNORECASE),
        "El servidor rechazó la conexión. Verificá host y puerto.",
    ),
    (
        re.compile(r"timeout expired|timed out|connection timeout", re.IGNORECASE),
        "Tiempo de espera agotado. Verificá que el servidor esté accesible.",
    ),
    (
        re.compile(r'database "[^"]+" does not exist|cannot open database', re.IGNORECASE),
        "La base de datos indicada no existe.",
    ),
    (
        re.compile(r"ssl|certificate", re.IGNORECASE),
        "Error de SSL/certificado. Revisá el modo SSL configurado.",
    ),
]

_DEFAULT_CONNECTION_ERROR = "No se pudo conectar. Verificá host, puerto, base de datos y credenciales."


def friendly_connection_error(msg: str) -> str:
    """Traduce un error de driver DB a un mensaje corto y accionable para el usuario."""
    for pattern, friendly in _CONNECTION_ERROR_PATTERNS:
        if pattern.search(msg):
            return friendly
    return _DEFAULT_CONNECTION_ERROR
