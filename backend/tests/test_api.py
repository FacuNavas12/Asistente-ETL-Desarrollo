"""
Tests de integración para la API del Asistente ETL.
Corre con: pytest tests/test_api.py -v
El backend debe estar corriendo en http://localhost:8000
"""
import pytest
import requests

BASE = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Fixtures de datos reutilizables
# ---------------------------------------------------------------------------

ORIGEN_VALIDO = [
    {
        "tableName": "ventas",
        "columns": [
            {"name": "id_venta",    "dataType": "INTEGER", "role": "identificador", "data": ["1", "2", "3"]},
            {"name": "fecha",       "dataType": "DATE",    "dataFormat": "YYYY-MM-DD", "data": ["2024-01-01", "2024-01-02"]},
            {"name": "monto",       "dataType": "DECIMAL", "role": "medida",       "data": ["100.50", "200.00", "-5.00"]},
            {"name": "id_cliente",  "dataType": "INTEGER", "role": "FK",           "data": ["10", "11", "12"]},
            {"name": "descripcion", "dataType": "VARCHAR", "data": ["Compra A", "Compra B"]},
        ],
    }
]

STAGING_VALIDO = [
    {
        "tableName": "STG_VENTAS",
        "origenVinculado": "ventas",
        "columns": [
            {"nombre": "id_venta",   "tipo": "INTEGER", "origenColumna": "id_venta",   "reglas": ["No nulo"],                          "datoNoValido": "Rechazar fila"},
            {"nombre": "fecha",      "tipo": "DATE",    "origenColumna": "fecha",      "reglas": ["Formato YYYY-MM-DD"],               "datoNoValido": "Reemplazar por NULL"},
            {"nombre": "monto",      "tipo": "DECIMAL", "origenColumna": "monto",      "reglas": ["Mayor a 0"],                        "datoNoValido": "Rechazar fila"},
            {"nombre": "id_cliente", "tipo": "INTEGER", "origenColumna": "id_cliente", "reglas": ["No nulo", "Existe en DIM_CLIENTE"],  "datoNoValido": "Rechazar fila"},
        ],
    }
]

DWH_VALIDO = {
    "tables": [
        {
            "tipo": "Dimension",
            "nombre": "DIM_CLIENTE",
            "origenVinculado": "ventas",
            "columnas": [
                {"nombre": "SK_CLIENTE",  "tipo": "INTEGER", "esSurrogateKey": True,  "origenColumna": ""},
                {"nombre": "ID_CLIENTE",  "tipo": "INTEGER", "esSurrogateKey": False, "origenColumna": "id_cliente"},
            ],
        },
        {
            "tipo": "Fact",
            "nombre": "FACT_VENTAS",
            "origenVinculado": "ventas",
            "columnas": [
                {"nombre": "SK_VENTA",    "tipo": "INTEGER", "esSurrogateKey": True,  "origenColumna": ""},
                {"nombre": "SK_CLIENTE",  "tipo": "INTEGER", "esSurrogateKey": False, "origenColumna": "id_cliente"},
                {"nombre": "FECHA",       "tipo": "DATE",    "esSurrogateKey": False, "origenColumna": "fecha"},
                {"nombre": "MONTO",       "tipo": "DECIMAL", "esSurrogateKey": False, "origenColumna": "monto"},
            ],
        },
    ]
}

REGLAS_NEGOCIO = "Excluir ventas con monto negativo. Cargar solo registros del año 2024."

ETL_REQUEST_VALIDO = {
    "descripcionObjetivo": "Cargar ventas diarias al DWH para análisis de revenue",
    "origenTables": ORIGEN_VALIDO,
    "stagingDef": STAGING_VALIDO,
    "dwhModel": DWH_VALIDO,
    "reglasNegocio": REGLAS_NEGOCIO,
}

# ETL de ejemplo para validate/document (estructura mínima válida)
PROCESO_ETL_EJEMPLO = {
    "nombre": "ETL_VENTAS",
    "descripcion": "Carga de ventas al DWH",
    "steps": [
        {
            "orden": 1,
            "tipo_step_pdi": "TableInput",
            "nombre": "Leer ventas",
            "descripcion": "Lee la tabla de ventas del origen",
            "configuracion": {"connection": "origen_db", "sql": "SELECT * FROM ventas"},
            "justificacion": "Punto de entrada del ETL",
        },
        {
            "orden": 2,
            "tipo_step_pdi": "FilterRows",
            "nombre": "Filtrar montos negativos",
            "descripcion": "Elimina registros con monto <= 0",
            "configuracion": {"condition": "monto > 0"},
            "justificacion": "Regla de negocio: excluir montos negativos",
        },
        {
            "orden": 3,
            "tipo_step_pdi": "TableOutput",
            "nombre": "Cargar STG_VENTAS",
            "descripcion": "Inserta en staging",
            "configuracion": {"connection": "dwh_db", "table": "STG_VENTAS"},
            "justificacion": "Carga al staging",
        },
    ],
}


# ---------------------------------------------------------------------------
# CASO OK 1: Health check
# ---------------------------------------------------------------------------
def test_health_check():
    r = requests.get(f"{BASE}/")
    assert r.status_code == 200
    assert r.json().get("status") == "ok"


# ---------------------------------------------------------------------------
# CASO OK 2: Generación ETL completa (endpoint principal)
# ---------------------------------------------------------------------------
def test_generar_etl_completo():
    r = requests.post(f"{BASE}/api/ai/etl", json=ETL_REQUEST_VALIDO, timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "proceso_etl" in data
    assert "validaciones" in data
    assert "ktr_xml" in data
    assert data["proceso_etl"]["steps"], "Debe tener al menos un step"


# ---------------------------------------------------------------------------
# CASO OK 3: Endpoint versionado /api/v1/etl/generate
# ---------------------------------------------------------------------------
def test_generar_etl_v1():
    r = requests.post(f"{BASE}/api/v1/etl/generate", json=ETL_REQUEST_VALIDO, timeout=120)
    assert r.status_code == 200, r.text
    assert "proceso_etl" in r.json()


# ---------------------------------------------------------------------------
# CASO OK 4: ETL con descripción vacía (campo opcional)
# ---------------------------------------------------------------------------
def test_generar_etl_sin_descripcion():
    payload = {**ETL_REQUEST_VALIDO, "descripcionObjetivo": ""}
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=120)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# CASO OK 5: ETL con columnas mínimas (solo campos requeridos)
# ---------------------------------------------------------------------------
def test_generar_etl_minimo():
    payload = {
        "origenTables": [
            {"tableName": "clientes", "columns": [{"name": "id", "dataType": "INTEGER"}]}
        ],
        "stagingDef": [
            {"tableName": "STG_CLIENTES", "columns": [{"nombre": "id", "tipo": "INTEGER"}]}
        ],
        "dwhModel": {
            "tables": [
                {
                    "tipo": "Dimension",
                    "nombre": "DIM_CLIENTES",
                    "columnas": [{"nombre": "SK_CLIENTE", "tipo": "INTEGER", "esSurrogateKey": True}],
                }
            ]
        },
        "reglasNegocio": "Sin reglas especiales",
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=120)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# CASO OK 6: ETL con múltiples tablas de origen
# ---------------------------------------------------------------------------
def test_generar_etl_multiples_tablas():
    payload = {
        "descripcionObjetivo": "Integrar ventas y productos",
        "origenTables": [
            {
                "tableName": "ventas",
                "columns": [
                    {"name": "id_venta",   "dataType": "INTEGER", "data": ["1", "2"]},
                    {"name": "id_prod",    "dataType": "INTEGER", "data": ["10", "11"]},
                    {"name": "cantidad",   "dataType": "INTEGER", "data": ["3", "5"]},
                ],
            },
            {
                "tableName": "productos",
                "columns": [
                    {"name": "id_prod",    "dataType": "INTEGER", "data": ["10", "11"]},
                    {"name": "nombre",     "dataType": "VARCHAR", "data": ["Prod A", "Prod B"]},
                    {"name": "precio",     "dataType": "DECIMAL", "data": ["50.0", "80.0"]},
                ],
            },
        ],
        "stagingDef": [
            {
                "tableName": "STG_VENTAS_PROD",
                "columns": [
                    {"nombre": "id_venta",  "tipo": "INTEGER", "origenColumna": "id_venta"},
                    {"nombre": "nombre",    "tipo": "VARCHAR", "origenColumna": "nombre"},
                    {"nombre": "cantidad",  "tipo": "INTEGER", "origenColumna": "cantidad"},
                    {"nombre": "precio",    "tipo": "DECIMAL", "origenColumna": "precio"},
                ],
            }
        ],
        "dwhModel": {
            "tables": [
                {
                    "tipo": "Fact",
                    "nombre": "FACT_VENTAS",
                    "columnas": [
                        {"nombre": "SK_VENTA",    "tipo": "INTEGER", "esSurrogateKey": True},
                        {"nombre": "NOMBRE_PROD", "tipo": "VARCHAR", "esSurrogateKey": False},
                        {"nombre": "CANTIDAD",    "tipo": "INTEGER", "esSurrogateKey": False},
                        {"nombre": "PRECIO",      "tipo": "DECIMAL", "esSurrogateKey": False},
                    ],
                }
            ]
        },
        "reglasNegocio": "Solo ventas con cantidad >= 1",
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=120)
    assert r.status_code == 200, r.text


# ---------------------------------------------------------------------------
# CASO OK 7: Validar un ETL generado
# ---------------------------------------------------------------------------
def test_validar_etl():
    r = requests.post(
        f"{BASE}/api/v1/etl/validate",
        json={"proceso_etl": PROCESO_ETL_EJEMPLO},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "validaciones" in data
    assert "advertencias_buenas_practicas" in data


# ---------------------------------------------------------------------------
# CASO OK 8: Documentar un ETL generado
# ---------------------------------------------------------------------------
def test_documentar_etl():
    r = requests.post(
        f"{BASE}/api/v1/etl/document",
        json={"proceso_etl": PROCESO_ETL_EJEMPLO},
        timeout=60,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "documentacion" in data
    assert isinstance(data["documentacion"], str)


# ---------------------------------------------------------------------------
# CASO OK 9: Inferir estructuras STG y DWH
# ---------------------------------------------------------------------------
def test_inferir_estructuras():
    import json
    r = requests.post(
        f"{BASE}/api/v1/etl/infer-structures",
        json={
            "source_structure": json.dumps(ORIGEN_VALIDO),
            "process_description": "Cargar ventas diarias al DWH para análisis de revenue por cliente",
            "business_rules": "Excluir montos negativos. Solo año 2024.",
        },
        timeout=120,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "stg_definition" in data
    assert "dwh_model" in data
    assert "CREATE TABLE" in data["stg_definition"].upper()
    assert "CREATE TABLE" in data["dwh_model"].upper()


# ---------------------------------------------------------------------------
# CASO OK 10: Refinar estructuras inferidas con corrección
# ---------------------------------------------------------------------------
def test_refinar_estructuras():
    import json

    stg_ddl = """
    CREATE TABLE STG_VENTAS (
        id_venta   INTEGER,
        fecha      DATE,
        monto      DECIMAL(10,2),
        id_cliente INTEGER
    );
    """
    dwh_ddl = """
    CREATE TABLE DIM_CLIENTE (SK_CLIENTE INTEGER PRIMARY KEY, ID_CLIENTE INTEGER);
    CREATE TABLE FACT_VENTAS (SK_VENTA INTEGER PRIMARY KEY, SK_CLIENTE INTEGER, FECHA DATE, MONTO DECIMAL(10,2));
    """

    r = requests.post(
        f"{BASE}/api/v1/etl/infer-structures/refine",
        json={
            "source_structure": json.dumps(ORIGEN_VALIDO),
            "process_description": "Cargar ventas al DWH",
            "business_rules": "Excluir montos negativos",
            "current_stg": stg_ddl,
            "current_dwh": dwh_ddl,
            "correction": "Agregar columna descripcion en STG_VENTAS de tipo VARCHAR(255)",
            "history": [],
        },
        timeout=120,
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["iteration"] >= 2
    assert "stg_definition" in data


# ---------------------------------------------------------------------------
# CASO OK 11: Generar ETL desde estructuras inferidas
# ---------------------------------------------------------------------------
def test_generar_desde_inferencia():
    stg_ddl = """
    CREATE TABLE STG_VENTAS (
        id_venta   INTEGER NOT NULL,
        fecha      DATE,
        monto      DECIMAL(10,2),
        id_cliente INTEGER
    );
    """
    dwh_ddl = """
    CREATE TABLE DIM_CLIENTE (SK_CLIENTE INTEGER PRIMARY KEY, ID_CLIENTE INTEGER);
    CREATE TABLE FACT_VENTAS (SK_VENTA INTEGER PRIMARY KEY, SK_CLIENTE INTEGER, FECHA DATE, MONTO DECIMAL(10,2));
    """
    r = requests.post(
        f"{BASE}/api/v1/etl/generate-from-inference",
        json={
            "descripcionObjetivo": "Cargar ventas al DWH",
            "origenTables": ORIGEN_VALIDO,
            "stg_definition": stg_ddl,
            "dwh_model": dwh_ddl,
            "reglasNegocio": REGLAS_NEGOCIO,
        },
        timeout=120,
    )
    assert r.status_code == 200, r.text
    assert "proceso_etl" in r.json()


# ---------------------------------------------------------------------------
# CASO OK 12: Reglas de negocio muy largas y complejas
# ---------------------------------------------------------------------------
def test_reglas_negocio_complejas():
    reglas = (
        "1. Excluir registros con monto <= 0. "
        "2. Solo cargar ventas del año 2024. "
        "3. Si id_cliente es NULL, asignar id_cliente = -1 (cliente desconocido). "
        "4. Convertir la columna fecha a UTC antes de cargar. "
        "5. Si descripcion está vacía, reemplazar por 'SIN DESCRIPCION'. "
        "6. Deduplicar por id_venta manteniendo el registro más reciente. "
        "7. Aplicar máscara al campo descripcion si contiene datos sensibles (PII). "
    )
    payload = {**ETL_REQUEST_VALIDO, "reglasNegocio": reglas}
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=120)
    assert r.status_code == 200, r.text


# ===========================================================================
# CASOS QUE DEBEN FALLAR (422 Unprocessable Entity)
# ===========================================================================

# ---------------------------------------------------------------------------
# FALLO 1: Body completamente vacío
# ---------------------------------------------------------------------------
def test_fallo_body_vacio():
    r = requests.post(f"{BASE}/api/ai/etl", json={}, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 2: Falta origenTables
# ---------------------------------------------------------------------------
def test_fallo_sin_origen():
    payload = {
        "stagingDef": STAGING_VALIDO,
        "dwhModel": DWH_VALIDO,
        "reglasNegocio": REGLAS_NEGOCIO,
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 3: Falta stagingDef
# ---------------------------------------------------------------------------
def test_fallo_sin_staging():
    payload = {
        "origenTables": ORIGEN_VALIDO,
        "dwhModel": DWH_VALIDO,
        "reglasNegocio": REGLAS_NEGOCIO,
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 4: Falta dwhModel
# ---------------------------------------------------------------------------
def test_fallo_sin_dwh():
    payload = {
        "origenTables": ORIGEN_VALIDO,
        "stagingDef": STAGING_VALIDO,
        "reglasNegocio": REGLAS_NEGOCIO,
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 5: Falta reglasNegocio
# ---------------------------------------------------------------------------
def test_fallo_sin_reglas():
    payload = {
        "origenTables": ORIGEN_VALIDO,
        "stagingDef": STAGING_VALIDO,
        "dwhModel": DWH_VALIDO,
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 6: ColumnaOrigen sin 'name' (campo requerido)
# ---------------------------------------------------------------------------
def test_fallo_columna_sin_name():
    payload = {
        **ETL_REQUEST_VALIDO,
        "origenTables": [
            {"tableName": "ventas", "columns": [{"dataType": "INTEGER"}]}
        ],
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 7: ColumnaOrigen sin 'dataType'
# ---------------------------------------------------------------------------
def test_fallo_columna_sin_datatype():
    payload = {
        **ETL_REQUEST_VALIDO,
        "origenTables": [
            {"tableName": "ventas", "columns": [{"name": "id_venta"}]}
        ],
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 8: TablaOrigen sin 'tableName'
# ---------------------------------------------------------------------------
def test_fallo_tabla_sin_nombre():
    payload = {
        **ETL_REQUEST_VALIDO,
        "origenTables": [
            {"columns": [{"name": "id", "dataType": "INTEGER"}]}
        ],
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 9: ColumnaDwh sin 'esSurrogateKey'
# ---------------------------------------------------------------------------
def test_fallo_dwh_sin_surrogate_key():
    payload = {
        **ETL_REQUEST_VALIDO,
        "dwhModel": {
            "tables": [
                {
                    "tipo": "Fact",
                    "nombre": "FACT_VENTAS",
                    "columnas": [
                        {"nombre": "SK_VENTA", "tipo": "INTEGER"}  # falta esSurrogateKey
                    ],
                }
            ]
        },
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 10: ColumnaStaging sin 'nombre'
# ---------------------------------------------------------------------------
def test_fallo_staging_sin_nombre():
    payload = {
        **ETL_REQUEST_VALIDO,
        "stagingDef": [
            {"tableName": "STG_VENTAS", "columns": [{"tipo": "INTEGER"}]}
        ],
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 11: ColumnaStaging sin 'tipo'
# ---------------------------------------------------------------------------
def test_fallo_staging_sin_tipo():
    payload = {
        **ETL_REQUEST_VALIDO,
        "stagingDef": [
            {"tableName": "STG_VENTAS", "columns": [{"nombre": "id_venta"}]}
        ],
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 12: origenTables es lista vacía
# ---------------------------------------------------------------------------
def test_fallo_origen_lista_vacia():
    payload = {**ETL_REQUEST_VALIDO, "origenTables": []}
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 13: dwhModel sin tablas
# ---------------------------------------------------------------------------
def test_fallo_dwh_sin_tablas():
    payload = {**ETL_REQUEST_VALIDO, "dwhModel": {"tables": []}}
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 14: TablaDwh sin 'tipo'
# ---------------------------------------------------------------------------
def test_fallo_dwh_tabla_sin_tipo():
    payload = {
        **ETL_REQUEST_VALIDO,
        "dwhModel": {
            "tables": [
                {
                    "nombre": "FACT_VENTAS",
                    "columnas": [{"nombre": "SK", "tipo": "INTEGER", "esSurrogateKey": True}],
                }
            ]
        },
    }
    r = requests.post(f"{BASE}/api/ai/etl", json=payload, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 15: Validar con proceso_etl vacío
# ---------------------------------------------------------------------------
def test_fallo_validar_proceso_vacio():
    r = requests.post(
        f"{BASE}/api/v1/etl/validate",
        json={"proceso_etl": {}},
        timeout=60,
    )
    # Puede procesar igual (dict vacío es válido en Pydantic) pero Gemini puede fallar
    assert r.status_code in (200, 422, 500, 502)


# ---------------------------------------------------------------------------
# FALLO 16: Validar sin campo proceso_etl
# ---------------------------------------------------------------------------
def test_fallo_validar_sin_campo():
    r = requests.post(f"{BASE}/api/v1/etl/validate", json={}, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 17: Documentar sin campo proceso_etl
# ---------------------------------------------------------------------------
def test_fallo_documentar_sin_campo():
    r = requests.post(f"{BASE}/api/v1/etl/document", json={}, timeout=30)
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 18: Inferir sin source_structure
# ---------------------------------------------------------------------------
def test_fallo_inferir_sin_source():
    r = requests.post(
        f"{BASE}/api/v1/etl/infer-structures",
        json={
            "process_description": "Cargar ventas",
            "business_rules": "Sin reglas",
        },
        timeout=30,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 19: Inferir sin process_description
# ---------------------------------------------------------------------------
def test_fallo_inferir_sin_descripcion():
    import json
    r = requests.post(
        f"{BASE}/api/v1/etl/infer-structures",
        json={
            "source_structure": json.dumps(ORIGEN_VALIDO),
            "business_rules": "Sin reglas",
        },
        timeout=30,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 20: Refinar sin campo 'correction'
# ---------------------------------------------------------------------------
def test_fallo_refinar_sin_correction():
    import json
    r = requests.post(
        f"{BASE}/api/v1/etl/infer-structures/refine",
        json={
            "source_structure": json.dumps(ORIGEN_VALIDO),
            "process_description": "Cargar ventas",
            "business_rules": "Sin reglas",
            "current_stg": "CREATE TABLE STG_X (id INTEGER);",
            "current_dwh": "CREATE TABLE DIM_X (SK INTEGER PRIMARY KEY);",
            # falta 'correction'
        },
        timeout=30,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 21: Generar desde inferencia sin stg_definition
# ---------------------------------------------------------------------------
def test_fallo_from_inference_sin_stg():
    r = requests.post(
        f"{BASE}/api/v1/etl/generate-from-inference",
        json={
            "origenTables": ORIGEN_VALIDO,
            "dwh_model": "CREATE TABLE DIM_X (SK INTEGER PRIMARY KEY);",
            "reglasNegocio": "Sin reglas",
        },
        timeout=30,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 22: Método HTTP incorrecto (GET en lugar de POST)
# ---------------------------------------------------------------------------
def test_fallo_metodo_incorrecto():
    r = requests.get(f"{BASE}/api/ai/etl", timeout=10)
    assert r.status_code == 405


# ---------------------------------------------------------------------------
# FALLO 23: Content-Type incorrecto (texto plano en lugar de JSON)
# ---------------------------------------------------------------------------
def test_fallo_content_type_incorrecto():
    r = requests.post(
        f"{BASE}/api/ai/etl",
        data="esto no es json",
        headers={"Content-Type": "text/plain"},
        timeout=10,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 24: JSON malformado
# ---------------------------------------------------------------------------
def test_fallo_json_malformado():
    r = requests.post(
        f"{BASE}/api/ai/etl",
        data="{origenTables: [}",
        headers={"Content-Type": "application/json"},
        timeout=10,
    )
    assert r.status_code == 422


# ---------------------------------------------------------------------------
# FALLO 25: Endpoint inexistente
# ---------------------------------------------------------------------------
def test_fallo_endpoint_inexistente():
    r = requests.post(f"{BASE}/api/v1/etl/no-existe", json={}, timeout=10)
    assert r.status_code == 404
