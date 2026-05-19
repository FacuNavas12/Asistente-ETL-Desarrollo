from pydantic import BaseModel
from typing import Any, Dict, List, Optional


# ─── INPUT — Origen ───────────────────────────────────────────────────────────

class ColumnaOrigen(BaseModel):
    name: str
    dataType: str
    dataFormat: str = ""
    role: str = "atributo"
    data: List[str] = []


class TablaOrigen(BaseModel):
    tableName: str
    columns: List[ColumnaOrigen]


# ─── INPUT — Staging ──────────────────────────────────────────────────────────

class ColumnaStaging(BaseModel):
    origenColumna: str = ""
    nombre: str
    tipo: str
    reglas: List[str] = []       # array de reglas de limpieza
    datoNoValido: str = "Reemplazar por NULL"


class TablaStaging(BaseModel):
    tableName: str
    origenVinculado: str = ""
    columns: List[ColumnaStaging]
    reglasTabla: Optional[dict] = None   # filtros, dedup, politicaError
    metadata: Optional[dict] = None      # sourceSystem, etc.


# ─── INPUT — DWH ─────────────────────────────────────────────────────────────

class ColumnaDwh(BaseModel):
    origenColumna: str = ""
    nombre: str
    tipo: str
    esSurrogateKey: bool


class TablaDwh(BaseModel):
    tipo: str               # Fact | Dimension
    nombre: str
    origenVinculado: str = ""
    columnas: List[ColumnaDwh]


class ModeloDwh(BaseModel):
    tables: List[TablaDwh]


# ─── INPUT — Request principal ────────────────────────────────────────────────

class ETLRequest(BaseModel):
    descripcionObjetivo: str = ""
    origenTables: List[TablaOrigen]
    stagingDef: List[TablaStaging]
    dwhModel: ModeloDwh
    reglasNegocio: str


class ETLValidateRequest(BaseModel):
    proceso_etl: dict


class ETLDocumentRequest(BaseModel):
    proceso_etl: dict


# ─── OUTPUT ───────────────────────────────────────────────────────────────────

class StepETL(BaseModel):
    orden: int
    tipo_step_pdi: str
    nombre: str
    descripcion: str
    configuracion: dict
    justificacion: str          # RNF9


class ProcesoETL(BaseModel):
    nombre: str
    descripcion: str
    steps: List[StepETL]


class Validacion(BaseModel):
    tipo: str                   # error | warning | info
    campo: str
    mensaje: str


class MetadataResponse(BaseModel):
    modelo_usado: str
    tokens_input: int
    tokens_output: int
    region_inferencia: str


class ETLGenerateResponse(BaseModel):
    proceso_etl: ProcesoETL
    validaciones: List[Validacion]
    documentacion: str
    advertencias_buenas_practicas: List[str]
    ktr_xml: str = ""
    ktr_filename: str = ""
    metadata: MetadataResponse


class ETLValidateResponse(BaseModel):
    validaciones: List[Validacion]
    advertencias_buenas_practicas: List[str]
    metadata: MetadataResponse


class ETLDocumentResponse(BaseModel):
    documentacion: str
    metadata: MetadataResponse


# ─── INFERENCIA DE ESTRUCTURAS ────────────────────────────────────────────────

class InferRequest(BaseModel):
    source_structure: str           # origenTables serializado como JSON string
    process_description: str
    business_rules: str


class RefineRequest(BaseModel):
    source_structure: str
    process_description: str
    business_rules: str
    current_stg: str                # DDL STG de la iteración anterior
    current_dwh: str                # DDL DWH de la iteración anterior
    correction: str                 # instrucción del usuario en lenguaje natural
    history: List[Dict[str, Any]] = []   # [{correction, stg, dwh}, ...]


class InferResponse(BaseModel):
    stg_definition: str
    dwh_model: str
    stg_rationale: str
    dwh_rationale: str
    iteration: int = 1
    metadata: MetadataResponse


# ─── GENERATE DESDE INFERENCIA ───────────────────────────────────────────────

class ETLFromInferenceRequest(BaseModel):
    """Request para generar el ETL completo usando estructuras inferidas por el modelo."""
    descripcionObjetivo: str = ""
    origenTables: List[TablaOrigen]
    stg_definition: str             # DDL STG confirmado por el usuario
    dwh_model: str                  # DDL DWH confirmado por el usuario
    reglasNegocio: str
