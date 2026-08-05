# services/superset_export

**Capa:** `infrastructure/superset/`
**Propósito:** armar el ZIP de export (`assets/import/`) que Superset espera, sin llamar a ningún LLM ni a la API de Superset — eso lo hace `superset_client/` con el ZIP ya armado.

## Qué entra
El `DwhModel`/esquema del DWH generado por el flujo ETL — de dónde salen los charts y datasets a exportar.

## Qué sale
Un ZIP en memoria/disco con la estructura de assets que `superset_client.import_dashboard` sube.

## Archivos
| Archivo | Qué hace |
|---|---|
| `zip_builder.py` (308) | `build()` (`:196`) — orquesta el armado completo del ZIP. |
| `asset_yaml.py` (349) | Serialización de cada asset a YAML (el más grande del paquete). |
| `chart_selection.py` (227) | Decide qué charts generar según el modelo DWH. |
| `semantic_types.py` (124) | Mapeo de tipos DWH → tipos semánticos de Superset. |
| `synthetic_values.py` (44) | Valores sintéticos para preview de charts. |
| `constants.py` (87) | Constantes del paquete. |

## Reglas que aplican
R6 — un solo punto (`zip_builder.build()`) arma el ZIP; nada más en el repo debería reimplementar esa estructura.

## Qué NO va acá
- Llamada HTTP a Superset — eso es `services/superset_client/`.
- Lectura del esquema del DWH desde la request — eso llega ya armado desde `services/etl_generator.py`/el router.
