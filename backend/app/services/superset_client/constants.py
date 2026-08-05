"""Constantes compartidas del paquete superset_client: UUID/nombre fijos de la
conexión ETL_DWH y los prefijos de tablas staging excluidas de datasets/charts."""

# UUID fijo de referencia (frontend). Si Superset ya tiene ETL_DWH con otro UUID,
# se detecta y los dataset YAMLs se reescriben para usar el UUID real.
DB_UUID_FRONTEND = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
DB_NAME = "ETL_DWH"

# Prefijos de tablas intermedias/staging — excluidas de datasets/charts y del
# gate de estado del DWH. Espejo del STAGING_PREFIXES corto de db_connector
# (7 items) — la lista larga (11 items) vive en frontend/src/utils/supersetExport.js.
STAGING_PREFIXES = ["stg_", "staging_", "tmp_", "temp_", "ods_", "raw_", "wrk_"]
