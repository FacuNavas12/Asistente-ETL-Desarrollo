from pydantic import BaseModel
from typing import List, Optional


# ─── INPUT ────────────────────────────────────────────────────────────────────

class ColumnaStaging(BaseModel):
    nombre: str
    tipo: str
    regla: str
    dato_no_valido: str


class EsquemaStaging(BaseModel):
    nombre_tabla: str
    columnas: List[ColumnaStaging]


class ColumnaDwh(BaseModel):
    nombre: str
    tipo: str
    es_surrogate_key: bool


class TablaDwh(BaseModel):
    tipo: str                    # Fact | Dimension
    nombre: str
    origen_vinculado: str = ""
    columnas: List[ColumnaDwh]


class ModeloDwh(BaseModel):
    tables: List[TablaDwh]


class ETLRequest(BaseModel):
    origen_texto: str
    staging_def: EsquemaStaging
    dwh_model: ModeloDwh
    reglas_negocio: str


class ETLValidateRequest(BaseModel):
    proceso_etl: dict            # proceso_etl ya generado


class ETLDocumentRequest(BaseModel):
    proceso_etl: dict            # proceso_etl ya generado


# ─── OUTPUT ───────────────────────────────────────────────────────────────────

class StepETL(BaseModel):
    orden: int
    tipo_step_pdi: str           # nombre exacto del step en Pentaho PDI
    nombre: str
    descripcion: str
    configuracion: dict
    justificacion: str           # RNF9 — por qué se usa este step


class ProcesoETL(BaseModel):
    nombre: str
    descripcion: str
    steps: List[StepETL]


class Validacion(BaseModel):
    tipo: str                    # error | warning | info
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
    metadata: MetadataResponse


class ETLValidateResponse(BaseModel):
    validaciones: List[Validacion]
    advertencias_buenas_practicas: List[str]
    metadata: MetadataResponse


class ETLDocumentResponse(BaseModel):
    documentacion: str
    metadata: MetadataResponse
