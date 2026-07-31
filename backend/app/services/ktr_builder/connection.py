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

from app.domain.table_layer import infer_table_layer
from app.services.ktr_builder.common import _sub

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
    layer = infer_table_layer(table)

    if layer == "dwh":
        inferred = "conn_dwh"
    elif layer == "staging":
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

# Nombre de variable Kettle para el password de cada capa lógica — el usuario
# la completa en kettle.properties o en el conector de Spoon, nunca acá.
_PASSWORD_VAR_NAMES: dict[str, str] = {
    "conn_origen":  "ORIGEN_DB_PASSWORD",
    "conn_staging": "STAGING_DB_PASSWORD",
    "conn_dwh":     "DWH_DB_PASSWORD",
}


def _password_var_name(logical_name: str) -> str:
    return _PASSWORD_VAR_NAMES.get(logical_name, f"{_generic_var(logical_name)}_PASSWORD")


def missing_layer_warnings(real_connections: dict[str, dict]) -> list[str]:
    """Una capa lógica (origen/staging/dwh) sin entrada en real_connections
    sale como placeholder en el .ktr — se completa a mano en Spoon (D15,
    docs/refactor/02-decisiones.md: se avisa, no aborta). Cubre TANTO la capa
    que nunca se mandó en connections_map (el motivo original del bug de
    'conn_origen quedó sin resolver' que tumbaba el build entero) COMO la que
    se mandó pero resolve_real_connections() no pudo resolver (id inválido,
    no encontrada, motor sin mapeo, ya avisado con más detalle en su propio
    warning) — acá no se distingue el motivo porque desde el punto de vista
    del .ktr final el resultado es el mismo: placeholder, completar en Spoon."""
    return [
        f"Conexión '{name}': sin resolver — se completa a mano en Spoon "
        f"(host/puerto/base/usuario, variable de password ${{{var}}})."
        for name, var in _PASSWORD_VAR_NAMES.items()
        if name not in real_connections
    ]


def resolve_real_connections(
    connections_map: dict,
    db,
    owner: str | None = None,
) -> tuple[dict[str, dict], list[str]]:
    """
    Resuelve un mapa {nombre_lógico: connection_id} a metadata real de conexión
    (host/port/database/username/type/access) consultando la tabla Connection.

    El password NUNCA se resuelve ni se embebe — el backend no lo persiste
    (ver decisión de diseño de no-custodia de credenciales). En su lugar, cada
    conexión resuelta trae "password_var": el nombre de la variable Kettle
    (ej. "ORIGEN_DB_PASSWORD") que build.py declara en <parameters> con
    default vacío y documenta en la plantilla kettle.properties — nunca un
    valor de password, en ninguna forma (ni claro, ni ofuscado, ni codificado).

    owner: owner_id del job que dispara este build (KtrBuildJob.owner_id). Si no
    es None, cualquier conn_id cuyo Connection.owner_id no coincida se trata
    igual que "no encontrada" — evita que un connections_map armado a mano con
    el UUID de la conexión de otro usuario resuelva algo de esa conexión ajena.
    owner=None (AUTH_REQUIRED=false) salta el chequeo.

    conn_staging/conn_dwh pueden llegar como dict (metadata inline completada
    a mano en el formulario de destino — ver InlineConnection en
    etl_schemas.py) en vez de connection_id: esa capa nunca tuvo ni tendrá
    una fila Connection propia (no es una conexión reusable, es el destino
    de ESTE ETL puntual). Se resuelve igual que una conexión real, mismo
    password_var, sin tocar la tabla Connection ni el chequeo de owner
    (no hay owner que validar sobre un dict que el propio dueño del job mandó).

    Devuelve (real_connections, warnings). Toda conexión que no se pueda resolver
    genera un warning en vez de fallar — el .ktr sigue el build con placeholder.
    """
    from app.models.connection import Connection

    real: dict[str, dict] = {}
    warnings: list[str] = []

    for logical_name, value in (connections_map or {}).items():
        if not value:
            continue

        if isinstance(value, dict):
            db_type_key = value.get("db_type")
            kettle_meta = _DB_TYPE_TO_KETTLE.get(db_type_key)
            if kettle_meta is None:
                warnings.append(f"Conexión '{logical_name}': motor '{db_type_key}' sin mapeo Kettle — se usará placeholder.")
                continue

            real[logical_name] = {
                "host":         value.get("host"),
                "port":         value.get("port"),
                "database":     value.get("database"),
                "username":     value.get("username"),
                "password_var": _password_var_name(logical_name),
                "type":         kettle_meta["type"],
                "access":       kettle_meta["access"],
            }
            if value.get("ssl_mode"):
                warnings.append(
                    f"Conexión '{logical_name}': ssl_mode='{value['ssl_mode']}' configurado en la app — "
                    "verificar/configurar el modo SSL en la pestaña Options del conector "
                    "en Spoon (Kettle no lo hereda automáticamente de este backend)."
                )
            continue

        conn_id = value
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

        password_var = _password_var_name(logical_name)
        real[logical_name] = {
            "host":         conn.host,
            "port":         conn.port,
            "database":     conn.database,
            "username":     conn.username,
            "password_var": password_var,
            "type":         kettle_meta["type"],
            "access":       kettle_meta["access"],
        }

        # ssl_mode no se traduce a un atributo JDBC de Kettle acá: no hay un
        # export real de Spoon contra el que confirmar el código de atributo
        # correcto para POSTGRESQL/MSSQLNATIVE nativos (a diferencia de
        # CUSTOM_DRIVER_CLASS/CUSTOM_URL para GENERIC, que sí están
        # verificados — ver connections_sample.ktr), y escribir un atributo
        # inventado puede quedar silenciosamente ignorado o, peor, confundir
        # a Spoon. Se documenta como advertencia en vez de adivinar XML.
        if conn.ssl_mode:
            warnings.append(
                f"Conexión '{logical_name}': ssl_mode='{conn.ssl_mode}' configurado en la app — "
                "verificar/configurar el modo SSL en la pestaña Options del conector "
                "en Spoon (Kettle no lo hereda automáticamente de este backend)."
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

# Sin estos dos atributos, Postgres corre con soporte boolean/timestamp
# apagado (default de Kettle: N) -- silencioso hasta que un step compara un
# boolean nativo o un timestamp y Kettle lo trata como otra cosa. Confirmado
# contra export real de Spoon (los códigos de atributo son los que Spoon
# efectivamente escribe). Se aplican a POSTGRESQL real y a GENERIC (el
# fallback de este builder siempre apunta a org.postgresql.Driver -- ver
# _GENERIC_DRIVER_CLASS), no a MSSQLNATIVE.
_POSTGRES_LIKE_TYPES = {"POSTGRESQL", "GENERIC"}

# D49 (docs/refactor/02-decisiones.md): PREFERRED_SCHEMA_NAME obligatorio en
# toda <connection> emitida -- sin esto, un <schema/> vacío en un step (todo
# step de este builder lo deja vacío, ver steps/output.py) resuelve vía el
# search_path de la sesión JDBC en vez del artefacto, no reproducible desde
# el .ktr (C-4, confirmado en fuente contra DatabaseMeta.getQuotedSchemaTableCombination,
# investigacion-pentaho-C10-C11-C12.md §C.11). Alcance mínimo (C.11a): un
# default fijo por motor, mismo criterio de "public" que superset_export ya
# asume para el DWH -- no hay todavía un campo de schema por conexión en el
# contrato (dim_contracts/modelo de staging/DDL), eso es C.11b, sin decidir.
_DEFAULT_SCHEMA_BY_TYPE: dict[str, str] = {
    "POSTGRESQL":  "public",
    "GENERIC":     "public",  # fallback siempre apunta a org.postgresql.Driver
    "MSSQLNATIVE": "dbo",
}


def _add_attribute(attributes: Element, code: str, value: str) -> None:
    attr = SubElement(attributes, "attribute")
    _sub(attr, "code", code)
    _sub(attr, "attribute", value)


def _generic_var(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_]", "_", name or "conn").upper()


def _build_connection(trans: Element, conn: dict, real: dict | None = None) -> list[tuple[str, str]]:
    """Devuelve [(nombre_variable_Kettle, valor_default)] para toda variable
    ${...} que quedó en el XML de esta conexión — el caller (build.py) las
    declara como <parameters> de la transformación y las vuelca a una
    plantilla kettle.properties, así el .ktr documenta qué variables tiene
    que completar el usuario antes de ejecutar en Spoon en vez de dejarlas
    ${SIN_DECLARAR} silenciosas (Kettle resuelve una variable no declarada a
    string vacío sin avisar).

    El password SIEMPRE es una variable Kettle, nunca un valor embebido —
    tanto si `real` se resolvió (host/port/db/user reales, password
    parametrizado) como si no (todo placeholder). Ver resolve_real_connections
    para real["password_var"]."""
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
        password_var = real["password_var"]
        _sub(c, "password", f"${{{password_var}}}")
        undeclared_params = [(password_var, "")]
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
    conn_type_upper = str(conn_type).strip().upper()
    _add_attribute(
        attributes, "PREFERRED_SCHEMA_NAME",
        _DEFAULT_SCHEMA_BY_TYPE.get(conn_type_upper, "public"),
    )
    if conn_type_upper == "GENERIC":
        var = _generic_var(name)
        custom_url = f"jdbc:postgresql://${{{var}_HOST}}:${{{var}_PORT}}/${{{var}_DATABASE}}"
        _add_attribute(attributes, "CUSTOM_DRIVER_CLASS", _GENERIC_DRIVER_CLASS)
        _add_attribute(attributes, "CUSTOM_URL", custom_url)
    if conn_type_upper in _POSTGRES_LIKE_TYPES:
        _add_attribute(attributes, "SUPPORTS_BOOLEAN_DATA_TYPE", "Y")
        _add_attribute(attributes, "SUPPORTS_TIMESTAMP_DATA_TYPE", "Y")
    return undeclared_params


def build_kettle_properties_template(undeclared_params: list[tuple[str, str]]) -> str:
    """Plantilla kettle.properties para toda variable ${...} que quedó en las
    conexiones del .ktr (ver _build_connection) — tanto los *_DB_PASSWORD de
    conexiones resueltas como los *_HOST/_PORT/_DATABASE/_USER de conexiones
    sin resolver. "" si no hay ninguna variable.

    Las variables de password se declaran acá CON NOMBRE pero SIEMPRE con
    default vacío ("VAR=") — nunca un valor. El usuario completa el valor acá
    o directamente en el conector de Spoon; el backend no lo conoce."""
    if not undeclared_params:
        return ""
    lines = [
        "# Generado por el acelerador ETL — completar antes de ejecutar en Spoon/Kitchen/Pan.",
        "# Pegar en $HOME/.kettle/kettle.properties (Linux/Mac) o",
        "# %USERPROFILE%\\.kettle\\kettle.properties (Windows), o pasar como",
        "# parametro de ejecucion de Kitchen/Pan (-param:NOMBRE=valor).",
        "# Las variables *_DB_PASSWORD quedan sin valor a proposito -- completarlas",
        "# aca o directamente en el conector de Spoon. Nunca subir este archivo",
        "# ya completado a un repositorio ni compartirlo fuera del equipo.",
    ]
    seen: set[str] = set()
    for var_name, default in undeclared_params:
        if var_name in seen:
            continue
        seen.add(var_name)
        lines.append(f"{var_name}={default}")
    return "\n".join(lines) + "\n"
