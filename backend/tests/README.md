# Tests — Asistente ETL Backend

## Requisitos previos

```bash
cd backend
venv\Scripts\activate          # activar el entorno virtual
pip install -r requirements.txt
```

## Tipos de test

| Archivo | Tipo | Requiere servidor |
|---|---|---|
| `test_api.py` | Integración HTTP | Sí — backend en `localhost:8000` |
| `test_connections_api.py` | Integración (SQLite en memoria) | No |
| `test_connection_schemas.py` | Unitarios (Pydantic) | No |
| `test_db_connector.py` | Unitarios (mocks) | No |

Para `test_api.py`, levantá el backend antes de correr:

```bash
uvicorn app.main:app --reload
```

## Comandos básicos

Correr todos los tests (desde `backend/`):

```bash
pytest tests/ -v
```

Correr todos los tests de una carpeta:

```bash
pytest tests/ -v
```

Correr todos los tests de un archivo:

```bash
pytest tests/test_connection_schemas.py -v
pytest tests/test_db_connector.py -v
pytest tests/test_connections_api.py -v
pytest tests/test_api.py -v
```

## Correr un test específico

Por nombre de función:

```bash
pytest tests/test_api.py::test_health_check -v
pytest tests/test_connections_api.py::test_create_returns_masked_password -v
```

Por nombre de clase y método (tests en clases):

```bash
pytest tests/test_connection_schemas.py::TestPostgresConnectionCreate::test_ssl_mode_invalid -v
pytest tests/test_db_connector.py::TestBuildUrl::test_build_url_mssql_with_trust_server_certificate -v
```

Filtrar por palabra clave en el nombre (`-k`):

```bash
pytest tests/ -k "password" -v
pytest tests/ -k "fallo" -v
pytest tests/ -k "ssl" -v
```

## Correr solo los tests que fallaron

Repetir únicamente los tests que fallaron en la última ejecución:

```bash
pytest tests/ --lf -v
```

Correr primero los que fallaron y luego el resto:

```bash
pytest tests/ --ff -v
```

## Opciones útiles

Detener al primer fallo:

```bash
pytest tests/ -x -v
```

Detener luego de N fallos:

```bash
pytest tests/ --maxfail=3 -v
```

Ver el output de `print()` dentro de los tests:

```bash
pytest tests/ -s -v
```

Ver un resumen al final con los tests lentos:

```bash
pytest tests/ -v --durations=10
```
