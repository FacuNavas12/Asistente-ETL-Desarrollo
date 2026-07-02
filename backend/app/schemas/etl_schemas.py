from __future__ import annotations

from pydantic import BaseModel
from typing import Any, Dict, List, Optional


# ─── INPUT — Origen ───────────────────────────────────────────────────────────

class ColumnaOrigen(BaseModel):
    name: str
    dataType: str
    dataFormat: str = ""
    role: str = "atributo"
    # Deprecated since Fase 2: raw sample values are no longer transported.
    # CSV/Excel sources now embed stats in TablaOrigen.canonical_schema.profile.
    # Kept as Optional for backward compatibility with stored drafts.
    data: Optional[List[str]] = None


class TablaOrigen(BaseModel):
    tableName: str
    columns: List[ColumnaOrigen]
    # Set by the frontend when the table comes from a DB connection.
    # Used by context_builder to re-query via db_connector. Never sent to model.
    connection_id: Optional[str] = None
    schema_name: Optional[str] = None
    # Set by the frontend when the table comes from a file (CSV/Excel).
    # Contains the CanonicalSchema returned by POST /api/schema/infer.
    # context_builder uses this to build ModelContext without re-reading the file.
    canonical_schema: Optional[CanonicalSchema] = None  # type: ignore[type-arg]


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
    configuracion: dict = {}
    justificacion: str = ""


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
    documentacion: str = ""
    advertencias_buenas_practicas: List[str]
    dwh_sample: Dict[str, List[Dict[str, Any]]] = {}
    ktr_xml: str = ""
    ktr_filename: str = ""
    lineage: Optional["Lineage"] = None
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


class BuildFromRawRequest(BaseModel):
    """Reconstruye el .ktr a partir de una respuesta cruda del modelo guardada
    previamente por el frontend (descargada tras un fallo de build_ktr). Sin llamada al LLM."""
    raw_llm_data: Dict[str, Any]


# ─── GENERATE ASYNC + CONEXIONES EN PARALELO ─────────────────────────────────

class ConnectionsMapRequest(BaseModel):
    """IDs de Connection ya creados (vía POST /api/connections) por nombre lógico
    de capa. Nunca credenciales — solo referencias a filas ya existentes."""
    conn_origen: Optional[str] = None
    conn_staging: Optional[str] = None
    conn_dwh: Optional[str] = None


class GenerateAsyncResponse(BaseModel):
    job_id: str


class KtrJobStatusResponse(BaseModel):
    model_status: str
    build_status: str
    error: Optional[str] = None
    result: Optional[ETLGenerateResponse] = None
    # Poblado solo cuando build_status == "failed": el modelo ya respondió pero
    # build_ktr() falló. Le permite al frontend guardar/reutilizar esa respuesta
    # sin pagar de nuevo la llamada al LLM.
    raw_llm_data: Optional[Dict[str, Any]] = None


# Resolve forward references.
# Imports at bottom to avoid circular imports.
from app.schemas.canonical import CanonicalSchema  # noqa: E402
from app.schemas.lineage import Lineage  # noqa: E402
TablaOrigen.model_rebuild()
ETLGenerateResponse.model_rebuild()
