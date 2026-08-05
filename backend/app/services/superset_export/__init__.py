"""
superset_export — paquete que construye el ZIP de export de Superset (formato
assets/import/: metadata + database + datasets + charts + dashboard) a partir de
un Etl ya persistido en DB. Reemplaza la construccion que antes vivia en
frontend/src/utils/supersetExport.js: el frontend ahora solo pide
(POST /api/v1/etl/{etl_id}/superset/export), el backend arma el ZIP y se lo pasa
a superset_client.SupersetClient.import_dashboard para importarlo.

Flujo (ver zip_builder.build):
  1. Resolver el esquema DWH: result["dwh_sample"] si tiene filas reales, si no
     parsear form_data["dwh_model"] (DDL confirmado por el usuario) con
     ddl_adapter.parse_ddl — NUNCA re-parsea el XML .ktr que el propio backend
     genero (a diferencia del extractDwhSchemaFromKtrs que tenia el JS original).
  2. build_tables()            → arma tabla+columnas+pickColumn (zip_builder.py)
  3. select_charts_for_table() → decide que charts van por tabla (chart_selection.py)
  4. *_yaml()                  → serializan cada asset al formato YAML de Superset (asset_yaml.py)
  5. zipfile.ZipFile           → empaqueta todo (zip_builder.py)

Ver semantic_types.py para la clasificacion de columnas (usable/id/metric/category/date),
synthetic_values.py para los valores de demo cuando no hay filas reales todavia, y
constants.py para las listas de keywords/prefijos compartidas.
"""

from app.services.superset_export.zip_builder import build

__all__ = ["build"]
