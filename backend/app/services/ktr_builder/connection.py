"""
Resolución y serialización de conexiones Kettle: mapeo motor->tipo Kettle,
inferencia de conexión lógica por prefijo de tabla, resolución de conexiones
reales (Connection ORM, sin password — ver decisión de diseño de no
persistencia) y construcción del bloque <connection> del XML.
"""
from __future__ import annotations

import re
import uuid
from xml.etree.ElementTree import Element, SubElement

from app.services.ktr_builder.common import _sub

_STAGING_PREFIXES = ("stg_", "staging_", "tmp_", "temp_", "ods_", "raw_", "wrk_", "work_")
_DWH_PREFIXES     = ("dim_", "fact_", "fct_", "hecho_", "ft_", "dwh_", "bridge_", "br_", "rel_")

# Step types que requieren un tag <connection> en el XML
_STEPS_NEEDING_CONNECTION = {
    "TableInput", "TableOutput", "InsertUpdate", "Update", "Delete",
    "DimensionLookup", "CombinationLookup", "DBLookup", "ExecSQL",
    "DynamicSQLRow", "CallDBProc",
}


def _resolve_connection(
    cfg: dict,
    canonical_type: str,
    connection_names: list,
    pass_source_connection: str | None = None,
    pass_dest_connection: str | None = None,
) -> str:
    """
    Devuelve el nombre de conexión a usar en el step.
    Prioridad: campo 'connection' del config → rol de pase (si se pasó) → inferencia por tabla.

    pass_source_connection / pass_dest_connection: usados por el flujo de generación
    en 2 KTR (origen→STG / STG→DWH). Cada build_ktr() cubre un solo pase con exactamente
    2 conexiones relevantes — TableInput siempre lee la conexión origen de ESE pase,
    cualquier otro step que necesite conexión (TableOutput, DimensionLookup, DBLookup,
    etc.) escribe/consulta la conexión destino de ESE pase. No hace falta mirar nombre
    de tabla para esto: el rol alcanza porque dentro de un pase solo hay 2 capas.
    Ambos None (flujo monolítico actual) preserva el comportamiento previo sin cambios.
    """
    conn = (cfg.get("connection") or cfg.get("connection_name") or "").strip()
    if conn:
        return conn

    if pass_source_connection or pass_dest_connection:
        inferred = pass_source_connection if canonical_type == "TableInput" else pass_dest_connection
        if inferred and inferred in connection_names:
            return inferred

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


def resolve_real_connections(
    connections_map: dict,
    db,
    owner: str | None = None,
) -> tuple[dict[str, dict], list[str]]:
    """
    Resuelve un mapa {nombre_lógico: connection_id} contra la tabla Connection,
    validando que exista y que le pertenezca al owner del job.

    El backend ya no persiste passwords de conexión (ver decisión de diseño) —
    esta función deliberadamente NO arma un dict "real" con credenciales: cada
    conn_id resuelto o no cae en el mismo camino de warning/placeholder, que
    build.py ya sabía manejar. El próximo cambio reintroduce host/port/db/user
    reales en el .ktr (dejando el password como variable de Kettle, nunca
    embebido) — ver ktr_builder/build.py.

    owner: owner_id del job que dispara este build (KtrBuildJob.owner_id). Si no
    es None, cualquier conn_id cuyo Connection.owner_id no coincida se trata
    igual que "no encontrada" — evita que un connections_map armado a mano con
    el UUID de la conexión de otro usuario resuelva algo de esa conexión ajena.
    owner=None (AUTH_REQUIRED=false) salta el chequeo.

    Devuelve (real_connections, warnings). Toda conexión que no se pueda resolver
    genera un warning en vez de fallar — el .ktr sigue el build con placeholder.
    """
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
        if conn is None or (owner is not None and conn.owner_id != owner):
            warnings.append(f"Conexión '{logical_name}': no encontrada — se usará placeholder, configurar manualmente en Spoon.")
            continue

        db_type_key = conn.db_type.value if hasattr(conn.db_type, "value") else str(conn.db_type)
        kettle_meta = _DB_TYPE_TO_KETTLE.get(db_type_key)
        if kettle_meta is None:
            warnings.append(f"Conexión '{logical_name}': motor '{db_type_key}' sin mapeo Kettle — se usará placeholder.")
            continue

        warnings.append(
            f"Conexión '{logical_name}': el backend ya no completa credenciales en el .ktr "
            "— completar host/usuario/password manualmente en Spoon."
        )

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


def _build_connection(trans: Element, conn: dict, real: dict | None = None) -> list[tuple[str, str]]:
    """Devuelve [(nombre_variable_Kettle, valor_default)] para toda variable
    ${...} que esta conexión dejó sin resolver en el XML (lista vacía si
    `real` estaba disponible) — el caller (build.py) las declara como
    <parameters> de la transformación y las vuelca a una plantilla
    kettle.properties, así el .ktr documenta qué variables tiene que
    completar el usuario antes de ejecutar en Spoon en vez de dejarlas
    ${SIN_DECLARAR} silenciosas (Kettle resuelve una variable no declarada a
    string vacío sin avisar)."""
    c = SubElement(trans, "connection")
    name = conn.get("name", "conn_default")
    _sub(c, "name", name)
    undeclared_params: list[tuple[str, str]] = []
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
        var = _generic_var(name)
        conn_type = conn.get("type", "GENERIC")
        _sub(c, "server",   conn.get("host", "PLACEHOLDER_HOST"))
        _sub(c, "type",     conn_type)
        _sub(c, "access",   "Native")
        _sub(c, "database", conn.get("database", "PLACEHOLDER_DATABASE"))
        _sub(c, "port",     str(conn.get("port", 0)))
        # username SÍ se parametriza (a diferencia de server/database, que
        # quedan como texto plano PLACEHOLDER_* solo para diagnóstico visual
        # en Spoon): es el único de los tres que Kettle realmente usa para
        # autenticar contra el motor real vía CUSTOM_URL.
        _sub(c, "username", f"${{{var}_USER}}")
        # Sin conexión real resuelta: no hay password que ofuscar. Vacío es
        # honesto (Spoon lo muestra en blanco); "Encrypted " a secas simulaba
        # un password ofuscado inexistente. El password NUNCA se declara acá
        # ni en la plantilla kettle.properties (ver build_kettle_properties_template)
        # — se completa a mano en el conector de Spoon, nunca en texto plano.
        _sub(c, "password", "")
        undeclared_params = [
            (f"{var}_HOST",     conn.get("host", "PLACEHOLDER_HOST")),
            (f"{var}_PORT",     str(conn.get("port") or 5432)),
            (f"{var}_DATABASE", conn.get("database", "PLACEHOLDER_DATABASE")),
            (f"{var}_USER",     conn.get("username", "PLACEHOLDER_USER")),
        ]
    _sub(c, "servername")
    _sub(c, "data_tablespace")
    _sub(c, "index_tablespace")
    attributes = SubElement(c, "attributes")
    if str(conn_type).strip().upper() == "GENERIC":
        var = _generic_var(name)
        custom_url = f"jdbc:postgresql://${{{var}_HOST}}:${{{var}_PORT}}/${{{var}_DATABASE}}"
        _add_attribute(attributes, "CUSTOM_DRIVER_CLASS", _GENERIC_DRIVER_CLASS)
        _add_attribute(attributes, "CUSTOM_URL", custom_url)
    return undeclared_params


def build_kettle_properties_template(undeclared_params: list[tuple[str, str]]) -> str:
    """Plantilla kettle.properties para toda variable ${...} que quedó sin
    resolver en las conexiones del .ktr (ver _build_connection). "" si no hay
    ninguna. Nunca incluye password — eso se completa a mano en Spoon."""
    if not undeclared_params:
        return ""
    lines = [
        "# Generado por el acelerador ETL — completar antes de ejecutar en Spoon/Kitchen/Pan.",
        "# Pegar en $HOME/.kettle/kettle.properties (Linux/Mac) o",
        "# %USERPROFILE%\\.kettle\\kettle.properties (Windows), o pasar como",
        "# parametro de ejecucion de Kitchen/Pan (-param:NOMBRE=valor).",
        "# El password de cada conexion NO se incluye aca por seguridad --",
        "# completarlo directamente en el conector de Spoon.",
    ]
    seen: set[str] = set()
    for var_name, default in undeclared_params:
        if var_name in seen:
            continue
        seen.add(var_name)
        lines.append(f"{var_name}={default}")
    return "\n".join(lines) + "\n"
