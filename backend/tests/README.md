# Tests — Asistente ETL Backend

Índice. Cada subcarpeta agrupa tests por la capa/módulo que valida y tiene su
propio `README.md` con la tabla archivo → qué valida. Esta reorganización es
de 2026-08-04 — antes todos los `test_*.py` vivían sueltos en `tests/`.

## Requisitos previos

```bash
cd backend
venv\Scripts\activate          # activar el entorno virtual
pip install -r requirements.txt
```

## Estructura

| Carpeta | Qué cubre | Costo real (LLM/API) |
|---|---|---|
| [`api/`](api/README.md) | HTTP end-to-end contra servidor vivo | **Sí** — requiere `uvicorn` corriendo y llama al LLM real |
| [`ktr_builder/build/`](ktr_builder/build/README.md) | Emisión de steps/XML del `.ktr` | No |
| [`ktr_builder/validators/`](ktr_builder/validators/README.md) | Passes de validación pre-emisión | No |
| [`ktr_builder/connections/`](ktr_builder/connections/README.md) | Resolución de conexiones, XML de conexión | No |
| [`dimension_scd/`](dimension_scd/README.md) | `domain/scd.py` + `dimension_step_policy` | No |
| [`fragmentation/`](fragmentation/README.md) | Corte N-KTR, lineage, wiring | No |
| [`schema_adapters/`](schema_adapters/README.md) | `CanonicalSchema`, adapters DDL/CSV/DB, dialect, profiler | No |
| [`etl_generator/`](etl_generator/README.md) | Orquestación, prompt, contratos, progreso async | Parcial — ver su README (`test_structured_outputs.py` tiene tests marcados `integration`) |
| [`superset/`](superset/README.md) | Export a Superset | No |
| [`architecture/`](architecture/README.md) | Checks estáticos cross-cutting | No |

`fixtures/` no se movió — sigue en `tests/fixtures/`, referenciada por
`ktr_builder/connections/test_ktr_connection_golden.py` y
`ktr_builder/validators/test_error_catalog_checks.py`.

## Correr todo (con costo)

```bash
pytest tests/ -v
```

Esto incluye `api/` (necesita `uvicorn app.main:app --reload` corriendo y
`.env` con credenciales reales de LLM) y los tests marcados `integration`
(llamadas reales a la API del LLM, sin servidor).

## Correr solo lo gratis (recomendado para el día a día)

Sin servidor vivo, sin llamadas reales a ningún LLM — todo mockeado o con
SQLite en memoria:

```bash
pytest tests/ --ignore=tests/api -m "not integration" -v
```

Este es el comando que corre CI / que corrés antes de un commit.

## Correr una carpeta puntual

```bash
pytest tests/schema_adapters/ -v
pytest tests/ktr_builder/ -v
```

## Correr un test específico

Por nombre de función:

```bash
pytest tests/dimension_scd/test_scd_policy.py::test_no_key_forces_scd1 -v
```

Por nombre de clase y método:

```bash
pytest tests/schema_adapters/test_connection_schemas.py::TestPostgresConnectionCreate::test_ssl_mode_invalid -v
```

Filtrar por palabra clave en el nombre (`-k`):

```bash
pytest tests/ -k "password" -v
```

## Correr solo los tests que fallaron

```bash
pytest tests/ --lf -v      # repetir últimos fallos
pytest tests/ --ff -v      # fallos primero, luego el resto
```

## Opciones útiles

```bash
pytest tests/ -x -v                 # detener al primer fallo
pytest tests/ --maxfail=3 -v        # detener luego de N fallos
pytest tests/ -s -v                 # ver output de print()
pytest tests/ -v --durations=10     # resumen de tests más lentos
```
