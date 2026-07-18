"""
superset_client — paquete que integra el backend con la API REST de Superset.

Reexporta la API pública para que `from app.services.superset_client import X`
siga funcionando igual que cuando este era un único módulo.

Flujo (ver client.py:SupersetClient.import_dashboard):
  1. POST /api/v1/security/login            → access_token + csrf_token   (client.py)
  2. GET  /api/v1/database/                 → busca ETL_DWH por nombre    (database.py)
  3. POST /api/v1/database/ (si no existe)  → crea conexión ETL_DWH       (database.py)
  4. _strip_and_rewrite_zip()               → limpia ZIP + database_uuid  (zip_tools.py)
  5. sqllab/execute/                        → siembra tablas del DWH      (dwh_tables.py)
  6. POST /api/v1/assets/import/            → importa datasets/charts/dashboard
  7. GET  /api/v1/dashboard/{uuid}          → obtiene ID numérico y arma la URL

Ver uri.py para el sqlalchemy_uri real de una Connection, provisioning.py para
el alineado síncrono de ETL_DWH (usado desde etl_generator apenas se conoce
conn_dwh), datasets.py/charts.py para la creación directa desde los YAMLs del
ZIP, y dashboard.py para el fallback paso-a-paso y el fix de chartId.
"""
from app.services.superset_client.client import SupersetClient
from app.services.superset_client.constants import DB_NAME, DB_UUID_FRONTEND, STAGING_PREFIXES
from app.services.superset_client.errors import SupersetError
from app.services.superset_client.provisioning import provision_database_sync
from app.services.superset_client.uri import build_superset_uri

__all__ = [
    "SupersetClient",
    "SupersetError",
    "build_superset_uri",
    "provision_database_sync",
    "STAGING_PREFIXES",
    "DB_NAME",
    "DB_UUID_FRONTEND",
]
