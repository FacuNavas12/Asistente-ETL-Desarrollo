"""
Resolución y serialización de conexiones Kettle: mapeo motor->tipo Kettle,
inferencia de conexión lógica por prefijo de tabla, resolución de conexiones
reales (Connection ORM + password desofuscado en memoria) y construcción del
bloque <connection> del XML.
"""
from __future__ import annotations

import re
import uuid
from xml.etree.ElementTree import Element, SubElement

from app.core.kettle_crypto import encode as kettle_encode
from app.services.ktr_builder.common import _sub

_STAGING_PREFIXES = ("stg_", "staging_", "tmp_", "temp_", "ods_", "raw_", "wrk_", "work_")
_DWH_PREFIXES     = ("dim_", "fact_", "fct_", "hecho_", "ft_", "dwh_", "bridge_", "br_", "rel_")

# Step types que requieren un tag <connection> en el XML
_STEPS_NEEDING_CONNECTION = {
    "TableInput", "TableOutput", "InsertUpdate", "Update", "Delete",
    "DimensionLookup", "CombinationLookup", "DBLookup", "ExecSQL",
    "DynamicSQLRow", "CallDBProc",
}


def _resolve_connection(cfg: dict, canonical_type: str, connection_names: list) -> str:
    """
    Devuelve el nombre de conexión a usar en el step.
    Prioridad: campo 'connection' del config → campo 'connection_name' → inferencia por tabla.
    """
    conn = (cfg.get("connection") or cfg.get("connection_name") or "").strip()
    if conn:
        return conn

    table = (cfg.get("table") or cfg.get("schema_table") or "").lower().strip()

    if any(table.startswith(p) for p in _DWH_PREFIXES):
        inferred = "conn_dwh"
    elif any(table.startswith(p) for p in _STAGING_PREFIXES):
        inferred = "conn_staging"
    elif canonical_type == "TableInput":
        inferred = "conn_origen"
    else:
        inferred = connection_names[0] if connection_names else "conn_origen"

    # Preferir el nombre inferido si existe en las conexiones declaradas
    if inferred in connection_names:
        return inferred
    return connection_names[0] if connection_names else inferred


# ─── Motor -> tipo de conexión Kettle ──────────────────────────────────────────
# MSSQLNATIVE = driver JDBC oficial de Microsoft (confirmado contra export real
# de Spoon 9.x, ver tests/fixtures/connections_sample.ktr). Si el Spoon del
# equipo usa jTDS en vez del driver Microsoft, cambiar a "MSSQL" acá.
_DB_TYPE_TO_KETTLE: dict[str, dict] = {
    "postgresql": {"type": "POSTGRESQL",  "access": "Native"},
    "sqlserver":  {"type": "MSSQLNATIVE", "access": "Native"},
}


def resolve_real_connections(connections_map: dict, db) -> tuple[dict[str, dict], list[str]]:
    """
    Resuelve un mapa {nombre_lógico: connection_id} a datos de conexión reales
    (host/port/database/username/password-ofuscado/type) consultando la tabla
    Connection y desofuscando el password SOLO en memoria, para inyectarlo en el
    XML final. Nunca devuelve el password en claro ni lo loguea.

    Devuelve (real_connections, warnings). Toda conexión que no se pueda resolver
    genera un warning en vez de fallar — el .ktr sigue el build con placeholder.
    """
    from app.core.crypto import decrypt_password
    from app.models.connection import Connection

    real: dict[str, dict] = {}
    warnings: list[str] = []

    for logical_name, conn_id in (connections_map or {}).items():
        if not conn_id:
            continue
        try:
            conn_uuid = uuid.UUID(str(conn_id))
        except (ValueError, TypeError, AttributeError):
            warnings.append(f"Conexión '{logical_name}': id inválido — se usará placeholder, configurar manualmente en Spoon.")
            continue

        conn = db.get(Connection, conn_uuid)
        if conn is None:
            warnings.append(f"Conexión '{logical_name}': no encontrada — se usará placeholder, configurar manualmente en Spoon.")
            continue

        db_type_key = conn.db_type.value if hasattr(conn.db_type, "value") else str(conn.db_type)
        kettle_meta = _DB_TYPE_TO_KETTLE.get(db_type_key)
        if kettle_meta is None:
            warnings.append(f"Conexión '{logical_name}': motor '{db_type_key}' sin mapeo Kettle — se usará placeholder.")
            continue

        password_plain = decrypt_password(conn.encrypted_password)
        real[logical_name] = {
            "host":     conn.host,
            "port":     conn.port,
            "database": conn.database,
            "username": conn.username,
            "password": kettle_encode(password_plain),
            "type":     kettle_meta["type"],
            "access":   kettle_meta["access"],
        }
        password_plain = None  # nunca queda referenciado más allá de este punto

    return real, warnings


# ─── Connection block ─────────────────────────────────────────────────────────

# GENERIC en Kettle (DatabaseMeta) no trae driver embebido — sin estos dos
# atributos en <attributes>, Spoon tira "Driver class '' could not be found"
# al abrir el .ktr. org.postgresql.Driver es el default: el prompt (K6) fuerza
# "GENERIC" siempre en la salida del modelo y esta rama solo se alcanza cuando
# la conexión NO se pudo resolver a un motor real (ver resolve_real_connections),
# es decir el motor real es desconocido acá. El usuario ajusta el driver real
# en Spoon si no es Postgres — pero el .ktr ya carga sin error en vez de re
# ventar por atributos faltantes.
_GENERIC_DRIVER_CLASS = "org.postgresql.Driver"


def _add_attribute(attributes: Element, code: str, value: str) -> None:
    attr = SubElement(attributes, "attribute")
    _sub(attr, "code", code)
    _sub(attr, "attribute", value)


def _generic_var(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name or "conn").upper()


def _build_connection(trans: Element, conn: dict, real: dict | None = None) -> None:
    c = SubElement(trans, "connection")
    name = conn.get("name", "conn_default")
    _sub(c, "name", name)
    if real:
        _sub(c, "server",   real["host"])
        _sub(c, "type",     real["type"])
        _sub(c, "access",   real.get("access", "Native"))
        _sub(c, "database", real["database"])
        _sub(c, "port",     str(real["port"]))
        _sub(c, "username", real["username"])
        _sub(c, "password", real["password"])
        conn_type = real["type"]
    else:
        _sub(c, "server",   conn.get("host", "PLACEHOLDER_HOST"))
        conn_type = conn.get("type", "GENERIC")
        _sub(c, "type",     conn_type)
        _sub(c, "access",   "Native")
        _sub(c, "database", conn.get("database", "PLACEHOLDER_DATABASE"))
        _sub(c, "port",     str(conn.get("port", 0)))
        _sub(c, "username", conn.get("username", "PLACEHOLDER_USER"))
        # Sin conexión real resuelta: no hay password que ofuscar. Vacío es
        # honesto (Spoon lo muestra en blanco); "Encrypted " a secas simulaba
        # un password ofuscado inexistente.
        _sub(c, "password", "")
    _sub(c, "servername")
    _sub(c, "data_tablespace")
    _sub(c, "index_tablespace")
    attributes = SubElement(c, "attributes")
    if str(conn_type).strip().upper() == "GENERIC":
        var = _generic_var(name)
        custom_url = f"jdbc:postgresql://${{{var}_HOST}}:${{{var}_PORT}}/${{{var}_DATABASE}}"
        _add_attribute(attributes, "CUSTOM_DRIVER_CLASS", _GENERIC_DRIVER_CLASS)
        _add_attribute(attributes, "CUSTOM_URL", custom_url)
