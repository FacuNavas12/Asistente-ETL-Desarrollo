from __future__ import annotations

from pydantic import BaseModel, Field
from typing import Any, Dict, List, Literal, Optional, Union


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


class ArchivoKtr(BaseModel):
    """Un archivo físico ya serializado (.ktr o .kjb)."""
    xml: str
    filename: str


class EtapaOutput(BaseModel):
    """D20 (docs/refactor/02-decisiones.md) — una fase lógica del proceso
    materializada en 1..N archivos físicos, según lo que decidió
    compute_cut() (D6/D19) para esa fase. tipo determina qué campo mirar:
    - "ktr": la fase entera cupo en 1 archivo — archivo.
    - "kjb": compute_cut() encontró señal estructural de corte (C1/C1-bis,
      err1.ktr/err2.ktr, H21) y la fase se partió en N — kjb (el .kjb
      intermedio que las orquesta) + archivos (los N .ktr, en orden de
      ejecución).
    nombre (D28): la etiqueta de la etapa ("origen_stg"/"stg_dwh"/"proceso")
    que _build_job_plan ya usa internamente — expuesta para que el consumidor
    (frontend, D20-punto5) pueda nombrar la carpeta del ZIP cuando tipo="kjb"
    (D20-punto4), sin inferirla por índice."""
    tipo: Literal["ktr", "kjb"]
    nombre: str
    archivo: Optional[ArchivoKtr] = None
    kjb: Optional[ArchivoKtr] = None
    archivos: List[ArchivoKtr] = []


class ETLGenerateResponse(BaseModel):
    proceso_etl: ProcesoETL
    validaciones: List[Validacion]
    documentacion: str = ""
    advertencias_buenas_practicas: List[str]
    dwh_sample: Dict[str, List[Dict[str, Any]]] = {}
    # D20: reemplaza los slots fijos ktr_xml/ktr2_xml/kjb_xml (siempre exactamente
    # 2 KTR + 1 kjb) — ver docs/refactor/02-decisiones.md. Orden fijo cuando hay
    # 2 fases: Origen→Staging, Staging→DWH (flujo generate-from-inference). El
    # flujo monolítico legacy (build-from-raw con "ktr" plano) expone 1 sola
    # etapa. kjb_master orquesta las etapas entre sí — solo existe cuando hay
    # más de 1 etapa; None en el flujo monolítico (nada que secuenciar).
    etapas: List[EtapaOutput] = []
    kjb_master: Optional[ArchivoKtr] = None
    lineage: Optional["Lineage"] = None
    metadata: MetadataResponse
    # DDL final del DWH (post validate_and_correct_ddl — Parte 3): el mismo
    # contra el que se armó KTR_2 (STG→DWH), no el dwh_model crudo del request.
    # None en el flujo monolítico legacy (build-from-raw sin auditoría).
    dwh_ddl: Optional[str] = None


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
    # D37 (docs/refactor/02-decisiones.md): la razón del scd_type elegido,
    # como artefacto persistido — no prosa suelta. Default "" para que los
    # dim_contracts ya persistidos en etls.result_json (anteriores a D37)
    # sigan validando sin migración.
    scd_rationale: str = ""


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
    # D31 (docs/refactor/02-decisiones.md): salida cruda del modelo para la
    # etapa origen→STG de un intento anterior, tal como la devuelve
    # GET /{job_id}/status en stages[].data. Si viene, generate_etl_async NO
    # llama al modelo para esa etapa ni corre sus repairs — ya vienen
    # aplicados en el checkpoint; solo corre normalize_step_configs como red
    # defensiva barata (determinística, sin LLM). NO es salida que produzca
    # el LLM en este request: es entrada del cliente, misma superficie de
    # confianza que BuildFromRawRequest.raw_llm_data. validate_and_correct_ddl
    # y la etapa STG→DWH SIGUEN corriendo — no se saltea todo, solo 3 de 5
    # llamadas al modelo. Los tokens de la etapa reutilizada no se cuentan en
    # MetadataResponse.
    reuse_stage_1: Optional[Dict[str, Any]] = None


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


# ─── CONEXIONES (inline, sin custodia de password) ────────────────────────────
# Movido arriba de BuildFromRawRequest (antes vivía junto a "GENERATE ASYNC +
# CONEXIONES EN PARALELO" más abajo) para que BuildFromRawRequest pueda usar
# ConnectionsMapRequest sin forward ref — build-from-raw ahora también acepta
# un mapa de conexiones (ver connections_map abajo).

class InlineConnection(BaseModel):
    """Metadata de conexión destino (staging/DWH) o de origen sin fila
    Connection guardada, tal cual la completa el usuario en el formulario —
    nunca se crea una fila Connection para esto (no es una conexión
    reusable, es solo la metadata de ESTE ETL puntual) y NUNCA lleva
    password: resolve_real_connections() la deja siempre como variable
    Kettle, igual que para las conexiones por connection_id (ver
    ktr_builder/connection.py)."""
    db_type: Literal["postgresql", "sqlserver"]
    host: str = Field(..., min_length=1, max_length=255)
    port: int = Field(..., ge=1, le=65535)
    database: str = Field(..., min_length=1, max_length=255)
    username: str = Field(..., min_length=1, max_length=255)
    ssl_mode: Optional[str] = None


class ConnectionsMapRequest(BaseModel):
    """conn_origen: id de una Connection ya creada (vía POST /api/connections,
    string) cuando el origen vino del explorador de esquema en vivo — esa
    fila sigue haciendo falta ahí porque el explorador conectó de verdad
    contra ella. O metadata inline (InlineConnection) cuando el origen NO
    vino de una conexión guardada (CSV/Excel/DDL/formulario) y el usuario la
    completa a mano en el paso de conexiones del job, igual que staging/DWH.
    None (o ausente) significa "completar en Spoon" — mismo criterio que
    conn_staging/conn_dwh, resuelve a placeholder, ya no aborta el build
    (D15, docs/refactor/02-decisiones.md).

    conn_staging/conn_dwh: metadata inline (InlineConnection) o None. None
    significa "completar en Spoon" — resolve_real_connections() lo deja como
    placeholder, igual que hoy para una conexión no resuelta. Nunca se
    persiste como fila Connection: es solo la metadata de destino de ESTE
    ETL, no una conexión reusable."""
    conn_origen: Optional[Union[str, InlineConnection]] = None
    conn_staging: Optional[InlineConnection] = None
    conn_dwh: Optional[InlineConnection] = None


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
    guardados antes de este campo — en ese caso no se corre el enforcement.

    connections_map: mismo shape que usa el flujo async (POST /{job_id}/connections)
    — antes este endpoint no tenía forma de recibir conexiones y siempre entregaba
    el .ktr con placeholder, aunque el usuario ya las hubiera completado en el
    formulario (ver docs/refactor/02-decisiones.md). None (default) preserva el
    comportamiento histórico: todo placeholder."""
    raw_llm_data: Dict[str, Any]
    dim_contracts: List[DimContract] = []
    connections_map: Optional[ConnectionsMapRequest] = None


class GenerateAsyncResponse(BaseModel):
    job_id: str


class ProgressEvent(BaseModel):
    """Un evento de la bitácora de progreso de un KtrBuildJob (D29,
    docs/refactor/02-decisiones.md). seq es monotónico y denso dentro del
    job — el cliente pide desde el último seq que ya mostró; nunca se
    reordena ni se reescribe un evento ya emitido.

    code es vocabulario cerrado (ver _PROGRESS_CODES en
    app.services.job_progress) — no texto libre, para poder assertarlo
    en tests sin acoplarse a la redacción exacta del mensaje."""
    seq: int
    ts: str                        # ISO-8601 UTC
    stage: Literal["job", "ddl", "origen_stg", "stg_dwh", "build"]
    code: str
    level: Literal["info", "warning", "error"]
    message: str                   # español, listo para mostrar, <= 240 chars


class StageRawInfo(BaseModel):
    """Estado y payload crudo de UNA de las dos llamadas de generación
    (D30/D32, docs/refactor/02-decisiones.md). `data` se puebla SOLO
    cuando el job está en estado terminal — durante el polling activo
    viaja siempre None, porque mandarlo en cada tick de 1.2s sería del
    orden de 10 MB por generación (payloads de cientos de KB)."""
    nombre: Literal["origen_stg", "stg_dwh"]
    status: Literal["pending", "running", "done", "failed", "reused"]
    data: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class KtrJobStatusResponse(BaseModel):
    model_status: str
    build_status: str
    error: Optional[str] = None
    result: Optional[ETLGenerateResponse] = None
    # Poblado solo cuando build_status == "failed" o "built" (y ambas etapas
    # están completas): el modelo ya respondió. Le permite al frontend
    # guardar/reutilizar esa respuesta sin pagar de nuevo la llamada al LLM.
    #
    # D32: este campo NUNCA lleva una etapa en null — build_etl_from_raw()
    # (etl_generator.py:758) discrimina el shape por presencia de clave
    # ("ktr_1" in raw_llm_data), no por valor, así que un {"ktr_2": null}
    # pasaría ese chequeo y explotaría con TypeError más abajo. Lo parcial
    # (una sola etapa lista) va en `stages`, campo separado que ningún
    # consumidor viejo mira.
    raw_llm_data: Optional[Dict[str, Any]] = None
    progress: List[ProgressEvent] = []
    # Siempre las 2 entradas, en orden D28 (origen_stg, stg_dwh) — ver D30/D32.
    stages: List[StageRawInfo] = []


# Resolve forward references.
# Imports at bottom to avoid circular imports.
from app.schemas.canonical import CanonicalSchema  # noqa: E402
from app.schemas.lineage import Lineage  # noqa: E402
TablaOrigen.model_rebuild()
ETLGenerateResponse.model_rebuild()
