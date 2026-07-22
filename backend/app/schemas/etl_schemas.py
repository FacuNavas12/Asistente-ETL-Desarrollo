from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional


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
    # Flujo de 2 KTR + 1 .kjb (origen→STG / STG→DWH orquestados en secuencia).
    # Vacíos ("") en el flujo monolítico legacy (build-from-raw) — el frontend
    # los trata como "no hay KTR_2/.kjb para este resultado".
    ktr2_xml: str = ""
    ktr2_filename: str = ""
    kjb_xml: str = ""
    kjb_filename: str = ""
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
    source_schema_json: str         # origenTables serializado como JSON string
    process_goal: str
    business_rules: str


class DimContract(BaseModel):
    """Contrato Dimension lookup/update de una dimensión del DWH inferido —
    consumido por la fase de generación de steps en vez de parsear el DDL."""
    table: str
    scd_type: int
    technical_key: str
    version_field: str
    date_from: str
    date_to: str
    natural_keys: List[str]
    unknown_key_value: int
    attributes_scd1: List[str] = []
    attributes_scd2: List[str] = []


class RefineRequest(BaseModel):
    source_schema_json: str
    process_goal: str
    business_rules: str
    previous_stg: str               # DDL STG de la iteración anterior
    previous_dwh: str               # DDL DWH de la iteración anterior
    correction: str                 # instrucción del usuario en lenguaje natural
    correction_history: List[Dict[str, Any]] = []   # [{correction, stg_ddl, dwh_ddl}, ...]
    # Parte 4 (bloque B): sin esto, un refinamiento que cambia el DDL deja los
    # dim_contracts previos desincronizados sin que nada lo detecte. Default []
    # para no romper llamadas viejas — ver _build_refine_prompt() en
    # structure_inferrer.py, que instruye preservar por default y marcar
    # "CONTRATO MODIFICADO" en assumptions cuando el feedback cambia una
    # dimensión ya existente.
    previous_dim_contracts: List[DimContract] = []


class InferResponse(BaseModel):
    stg_ddl: str
    dwh_ddl: str
    dim_contracts: List[DimContract] = []
    assumptions: List[str] = []
    stg_rationale: str
    dwh_rationale: str
    iteration_count: int = 1
    metadata: MetadataResponse


# ─── GENERATE DESDE INFERENCIA ───────────────────────────────────────────────

class ETLFromInferenceRequest(BaseModel):
    """Request para generar el ETL completo usando estructuras inferidas por el modelo."""
    descripcionObjetivo: str = ""
    origenTables: List[TablaOrigen]
    stg_definition: str             # DDL STG confirmado por el usuario
    dwh_model: str                  # DDL DWH confirmado por el usuario
    reglasNegocio: str
    # Contrato por dimensión devuelto por /infer-structures — consumido por la
    # fase de generación de steps (KTR STG→DWH) para configurar Dimension
    # lookup/update sin adivinar por parseo del DDL. Default [] para no romper
    # llamadas viejas; ver _dim_contracts_anomaly_warning() en etl_generator.py
    # para la señal explícita cuando esto llega vacío pero dwh_model sí declara dim_*.
    dim_contracts: List[DimContract] = []


class DdlValidationResponse(BaseModel):
    """Salida de ddl_validation.validate_and_correct_ddl() (Parte 3) — audita
    dwh_ddl contra dim_contracts y las invariantes I2-I9, agrega lo que falte
    (nunca elimina/renombra/reduce) y reporta lo que no puede resolver solo.
    conflictos reusa Validacion en vez de un shape propio."""
    dwh_ddl: str
    sin_cambios: bool
    cambios_aplicados: List[str] = []
    conflictos: List[Validacion] = []
    metadata: MetadataResponse


class BuildFromRawRequest(BaseModel):
    """Reconstruye el .ktr a partir de una respuesta cruda del modelo guardada
    previamente por el frontend (descargada tras un fallo de build_ktr). Sin llamada al LLM.

    raw_llm_data trae dict plano (flujo legacy monolítico, claves proceso_etl/ktr
    en el nivel top) o {"ktr_1": {...}, "ktr_2": {...}} (flujo de 2 KTR) — ver
    build_etl_from_raw() en etl_generator.py, que detecta el shape.

    dim_contracts: el contrato de la inferencia (ver DimContract) no viaja
    dentro de raw_llm_data — es un campo del request de generación (ETLFromInferenceRequest),
    no de la salida del modelo que arma el KTR. Sin pasarlo acá aparte, este
    endpoint no tiene forma de correr enforce_dimension_step_policy() sobre el
    KTR reconstruido. Opcional (default vacío) por compatibilidad con datos
    guardados antes de este campo — en ese caso no se corre el enforcement."""
    raw_llm_data: Dict[str, Any]
    dim_contracts: List[DimContract] = []


# ─── GENERATE ASYNC + CONEXIONES EN PARALELO ─────────────────────────────────

class InlineConnection(BaseModel):
    """Metadata de conexión destino (staging/DWH) tal cual la completa el
    usuario en el formulario — nunca se crea una fila Connection para esto
    (no es una conexión reusable, es solo el destino de ESTE ETL) y NUNCA
    lleva password: resolve_real_connections() la deja siempre como variable
    Kettle, igual que para las conexiones por connection_id (ver
    ktr_builder/connection.py)."""
    db_type: Literal["postgresql", "sqlserver"]
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    ssl_mode: Optional[str] = None


class ConnectionsMapRequest(BaseModel):
    """conn_origen: id de una Connection ya creada (vía POST /api/connections)
    — el origen sigue necesitando una fila real porque el explorador de
    esquema conecta de verdad contra ella antes de este paso.

    conn_staging/conn_dwh: metadata inline (InlineConnection) o None. None
    significa "completar en Spoon" — resolve_real_connections() lo deja como
    placeholder, igual que hoy para una conexión no resuelta. Nunca se
    persiste como fila Connection: es solo la metadata de destino de ESTE
    ETL, no una conexión reusable."""
    conn_origen: Optional[str] = None
    conn_staging: Optional[InlineConnection] = None
    conn_dwh: Optional[InlineConnection] = None


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
