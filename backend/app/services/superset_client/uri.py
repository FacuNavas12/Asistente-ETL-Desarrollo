"""Construye el sqlalchemy_uri real de una Connection (conn_dwh) para registrarla
en Superset — con los drivers que existen EN EL ENTORNO DE SUPERSET, no en este backend."""


def build_superset_uri(conn) -> str:
    """
    sqlalchemy_uri real para el connection registrado en Superset, a partir
    de un Connection ya resuelto (conn_dwh). Deliberadamente NO reusa los
    driver strings de db_connector.py (postgresql+psycopg / mssql+pyodbc):
    esos apuntan a lo instalado en EL ENTORNO DE ESTE BACKEND, no en el de
    Superset (proceso/entorno Python separado). Postgres usa el driver
    default de Superset (sin sufijo); SQL Server usa pymssql (convención más
    común en imágenes de Superset — no requiere ODBC de sistema).
    """
    from urllib.parse import quote

    from app.core.config import settings
    from app.core.crypto import decrypt_password
    from app.models.connection import DbType

    password = decrypt_password(conn.encrypted_password)
    safe_user = quote(conn.username, safe="")
    safe_pass = quote(password, safe="")
    host_db = f"{conn.host}:{conn.port}/{conn.database}"

    db_type = conn.db_type.value if hasattr(conn.db_type, "value") else str(conn.db_type)
    if db_type == DbType.postgresql.value:
        return f"postgresql://{safe_user}:{safe_pass}@{host_db}"
    return f"mssql+{settings.superset_mssql_driver}://{safe_user}:{safe_pass}@{host_db}"
