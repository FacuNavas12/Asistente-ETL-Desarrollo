"""
D37 (docs/refactor/02-decisiones.md): criterio determinista de SCD1 vs SCD2.

Hasta acá dos decisiones distintas se trataban como una sola:
  A) scd_type (0/1/2) por dimensión           -> juicio del LLM, sin criterio
     escrito en ningún prompt vivo (el único texto con criterio real del repo
     vivía en promptfoo/prompts/inference.yaml, una copia congelada que no
     corre).
  B) qué step de Pentaho la implementa        -> derive_dimension_step_type()
     de abajo, determinista desde D11/D16 (ver dimension_step_policy.py, que
     reexporta esta función — vivía ahí antes de D37).

Este módulo ataca A, no reemplaza a A: SCD2 vs SCD1 es una decisión de negocio
("¿un reporte del pasado debe mostrar el atributo como era entonces?"), no una
propiedad derivable de datos crudos — el backend no puede inventarla sola (D6:
"la línea divisoria es dónde ya vive la información"). Lo que sí puede hacer es
descartar los casos donde SCD2 es mecánicamente imposible o ya está declarado
por evidencia estructural, y acotar el residuo que sí depende de juicio de
negocio — mismo patrón que D16/D21 (backend acota, el modelo decide el resto y
justifica).

Ni siquiera Pentaho tiene criterio propio de decisión: adopta Kimball y delega.
Su única prescripción propia es negativa y sobre volatilidad de ESQUEMA, no de
datos ("Introducing changes to the dimensional model in Type 2 could be very
expensive... not recommended... where a new attribute could be added in the
future" — Pentaho Academy, SCDs). El criterio de este módulo está fundado en
esa doc + Kimball Group ("Slowly Changing Dimensions", 2008; "Design Tip #152",
2013) — citas completas en el cuerpo de D37, docs/refactor/02-decisiones.md.

Capa `domain` (R1, arquitectura-objetivo.md): solo stdlib, nada de
CanonicalSchema/Pydantic acá. La proyección CanonicalSchema -> primitivos la
hace el llamador en services/ (ver structure_inferrer._build_scd_precheck_block).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Mapping, Sequence

# ─── Vocabulario de intención de negocio (alcance PROYECTO, no por entidad) ───
#
# CORRECCIÓN DE ALCANCE (revisión de D37 antes de cerrarla): business_rules y
# process_goal son texto de PROYECTO; el veredicto de classify_scd_candidates
# es POR ENTIDAD. Si esta lista alimentara el veredicto por entidad, una sola
# aparición de "histórico" en la prosa inclinaría TODA dimensión del modelo
# hacia SCD2 — y "histórico" es de las palabras más sobrecargadas del dominio:
# "carga histórica inicial de 5 años" (volumen de hechos) y "datos históricos
# de ventas" (alcance temporal del hecho) matchean sin que ninguna hable de
# versionar un atributo. Por eso detect_history_intent() NO devuelve un
# veredicto por tabla — devuelve una señal de proyecto que el prompt declara
# con su alcance explícito, y decidir a qué dimensión aplica queda como el
# residuo de juicio que le corresponde al modelo (D16/D21).
_HISTORY_INTENT_PHRASES: tuple[str, ...] = (
    # Stem, no palabra completa: cubre histórico/histórica/históricos/históricas
    # y sus variantes sin tilde en un solo término (Caso D de la revisión de
    # D37: "carga histórica de ventas" tiene que matchear la señal de
    # PROYECTO — lo que corrige el alcance es que esta señal no decide sola
    # a qué dimensión aplica, no que deje de detectarse).
    "históric", "historic",
    "as-of", "as of",
    "evolución de", "evolucion de",
    "trazabilidad",
    "cambios de",
    "vigente a la fecha",
    "snapshot",
    "auditoría de cambios", "auditoria de cambios",
)

# Único caso donde SCD1 no es preferencia sino prohibición (Kimball, 2008:
# "In financial reporting environments with month end close processes and in
# any environment subject to regulatory or legal compliance, Type 1 changes
# may be outlawed. In these cases, the Type 2 technique must be used.") — por
# eso esta lista invierte el default (SCD1) en vez de solo matizarlo.
_COMPLIANCE_PHRASES: tuple[str, ...] = (
    "cierre contable", "cierre mensual",
    "auditoría", "auditoria",
    "regulatorio", "regulatoria",
    "normativa",
    "compliance",
    "reproducir reportes",
    "período cerrado", "periodo cerrado",
)

# Evidencia estructural de que el ORIGEN ya declaró que le importa el
# historial (regla 3-bis) — nombres de columna típicos de un Type 2 ya
# modelado aguas arriba (Pentaho Academy, SCDs: "'effective date' and
# 'current indicator' columns are used in this method").
_ORIGIN_HISTORY_COLUMNS: tuple[str, ...] = (
    "valid_from", "valid_to",
    "vigente_desde", "vigente_hasta",
    "fecha_desde", "fecha_hasta",
    "current_flag", "activo", "version",
)

# Nombre de tabla candidata a dimensión de calendario (regla 2).
_CALENDAR_NAME_RE = re.compile(r"fecha|tiempo|calendar", re.IGNORECASE)

# Cardinalidad "única por fila": no es lentamente cambiante, versionarla
# produce una fila nueva por carga (el extremo opuesto de "constante").
_NEAR_UNIQUE_RATIO = 0.95


class ScdVerdict(str, Enum):
    NO_HISTORY_POSSIBLE = "no_history_possible"
    HISTORY_DECLARED = "history_declared"
    UNDECIDED = "undecided"


@dataclass(frozen=True)
class ScdPrecheck:
    """Resultado por entidad — una línea del bloque de pre-check que entra al
    prompt de inferencia (ver structure_inferrer._build_scd_precheck_block)."""
    table: str
    verdict: ScdVerdict
    forced_scd_type: int | None
    mutable_attributes: tuple[str, ...]
    scd2_candidates: tuple[str, ...]
    reason: str
    evidence: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ProjectHistorySignal:
    """Resultado de detect_history_intent() — alcance PROYECTO, nunca un
    veredicto por entidad. Ver nota de alcance arriba de _HISTORY_INTENT_PHRASES."""
    matched_phrases: tuple[str, ...]
    compliance: bool

    @property
    def matched(self) -> bool:
        return bool(self.matched_phrases)


def detect_history_intent(text: str) -> ProjectHistorySignal:
    """Scan determinista de frases sobre business_rules + process_goal. NO
    decide qué dimensión versiona — eso es el residuo de juicio del modelo,
    ver nota de alcance arriba."""
    lowered = (text or "").lower()
    matched = tuple(p for p in _HISTORY_INTENT_PHRASES if p in lowered)
    compliance = any(p in lowered for p in _COMPLIANCE_PHRASES)
    return ProjectHistorySignal(matched_phrases=matched, compliance=compliance)


def _is_near_unique(distinct: int, row_count: int) -> bool:
    if row_count <= 0:
        return False
    return distinct >= row_count * _NEAR_UNIQUE_RATIO


def classify_scd_candidates(
    *,
    table_name: str,
    column_names: Sequence[str],
    key_columns: Sequence[str],
    key_columns_trusted: bool = True,
    date_type_columns: Iterable[str] = (),
    distinct_counts: Mapping[str, int] | None = None,
    row_count_estimate: int | None = None,
    declared_intent: str | None = None,
) -> ScdPrecheck:
    """Único punto de decisión de ScdPrecheck por entidad. Precedencia, de
    mayor a menor (razonada en docs/refactor/02-decisiones.md, D37):

      0. Sin candidato a clave natural durable **Y key_columns_trusted=True**
         -> NO_HISTORY_POSSIBLE, forced=1. Mecánica de la herramienta, no
         criterio de modelado: Dimension Lookup/Update no puede operar sin
         ella (Pentaho Academy, SCDs: "Both the prior and new rows contain as
         attributes the natural key (or another durable identifier)").
         Vinculante incluso sobre declared_intent.

         key_columns_trusted distingue "confirmado que no hay clave" (BD/DDL,
         que sí resuelven PK/UNIQUE reales) de "no se sabe si hay clave"
         (Formulario/CSV/Excel — el camino MÁS COMÚN, que nunca declara
         is_primary_key/unique). Sin esta distinción, key_columns=[] por
         AUSENCIA DE METADATA se confunde con key_columns=[] por AUSENCIA
         REAL de clave, y la regla 0 fuerza scd_type=1 en casi cualquier ETL
         armado a mano — encontrado en test_refine_untouched_dimension_
         preserves_dim_contracts (test_structured_outputs.py) antes de
         agregar este parámetro: el modelo, correctamente instruido, degradaba
         un dim_contract legítimo scd_type=2 a 1 con "CONTRATO MODIFICADO"
         porque el origen de prueba (Formulario) no traía PK estructural.
      1. Sin atributos mutables (todo lo no-clave es la propia clave) ->
         NO_HISTORY_POSSIBLE, forced=1. Versionar no produce ninguna versión
         distinta. Igual de vinculante que 0.
      2. Dimensión de calendario (nombre + única clave de tipo fecha) ->
         NO_HISTORY_POSSIBLE, forced=0 (Type 0 de Kimball, "Design Tip #152":
         atributo fijo). Angosto a propósito — un falso positivo acá fuerza
         SCD0 sobre una dimensión legítima.
      3. declared_intent (TableSemantics.dwh_intent.scd_type, ya llenado por
         el usuario) -> HISTORY_DECLARED si pide "2", UNDECIDED-preferente en
         otro caso. Por debajo de 0-2: la imposibilidad mecánica no se
         negocia ni con declaración explícita.
      4. Evidencia estructural en el propio origen (columnas tipo
         valid_from/current_flag/version) -> HISTORY_DECLARED. D6 puro: la
         información ya vive en el origen, es lectura, no inferencia.
      5. Resto -> UNDECIDED. El modelo decide, con scd2_candidates como techo.
    """
    key_set = {c.lower() for c in key_columns}
    mutable = tuple(c for c in column_names if c.lower() not in key_set)

    # Regla 0 — sin clave natural durable CONFIRMADA, SCD2 no tiene sobre qué
    # operar. Con key_columns_trusted=False (Formulario/CSV/Excel: no hay
    # metadata de PK/UNIQUE en absoluto) esto se salta — key_columns=[] ahí
    # significa "no lo sabemos", no "confirmado que no existe".
    if key_columns_trusted and not key_columns:
        return ScdPrecheck(
            table=table_name,
            verdict=ScdVerdict.NO_HISTORY_POSSIBLE,
            forced_scd_type=1,
            mutable_attributes=mutable,
            scd2_candidates=(),
            reason=(
                "sin clave natural durable identificada — Dimension Lookup/Update "
                "no puede operar sin ella (Pentaho Academy, SCDs)."
            ),
        )

    # Regla 1 — nada que versionar.
    if not mutable:
        return ScdPrecheck(
            table=table_name,
            verdict=ScdVerdict.NO_HISTORY_POSSIBLE,
            forced_scd_type=1,
            mutable_attributes=(),
            scd2_candidates=(),
            reason="toda columna no-clave es parte de la clave natural — no hay atributo que versionar.",
        )

    # Regla 2 — calendario: una sola clave, de tipo fecha, y nombre de tabla
    # que la delata. Angosto a propósito (ver docstring).
    date_key_set = {c.lower() for c in date_type_columns}
    if (
        _CALENDAR_NAME_RE.search(table_name)
        and len(key_columns) == 1
        and key_columns[0].lower() in date_key_set
    ):
        return ScdPrecheck(
            table=table_name,
            verdict=ScdVerdict.NO_HISTORY_POSSIBLE,
            forced_scd_type=0,
            mutable_attributes=mutable,
            scd2_candidates=(),
            reason="dimensión de calendario — atributos derivados de la fecha, fijos por definición (Type 0, Kimball).",
        )

    # scd2_candidates: atributos mutables ni casi-únicos por fila (versionar
    # produciría una fila nueva por carga) ni constantes (nunca cambian). Con
    # o sin perfil estadístico disponible — degradación explícita, no silenciosa.
    if distinct_counts and row_count_estimate is not None and row_count_estimate > 0:
        scd2_candidates = tuple(
            c for c in mutable
            if not (
                _is_near_unique(distinct_counts.get(c, 0), row_count_estimate)
                or distinct_counts.get(c, 0) <= 1
            )
        )
        cardinality_note = (
            "candidatos filtrados por cardinalidad frente al conteo de filas — "
            "es un PROXY de tasa de cambio (una sola foto del origen), no churn real."
        )
    else:
        scd2_candidates = mutable
        cardinality_note = "sin perfil estadístico disponible (DDL pegado o formulario manual) — todos los atributos mutables quedan como candidatos, sin filtro de cardinalidad."

    # Regla 3 — intención declarada explícitamente por el usuario
    # (TableSemantics.dwh_intent.scd_type), forma ya reservada en canonical.py.
    if declared_intent == "2":
        return ScdPrecheck(
            table=table_name,
            verdict=ScdVerdict.HISTORY_DECLARED,
            forced_scd_type=None,
            mutable_attributes=mutable,
            scd2_candidates=scd2_candidates,
            reason=f"declarado explícitamente por el usuario (dwh_intent.scd_type=2). {cardinality_note}",
            evidence=("dwh_intent.scd_type=2",),
        )

    # Regla 3-bis — evidencia estructural en el propio origen.
    origin_hits = tuple(c for c in column_names if c.lower() in _ORIGIN_HISTORY_COLUMNS)
    if origin_hits:
        return ScdPrecheck(
            table=table_name,
            verdict=ScdVerdict.HISTORY_DECLARED,
            forced_scd_type=None,
            mutable_attributes=mutable,
            scd2_candidates=scd2_candidates,
            reason=(
                f"el origen ya trae columna(s) de historial ({', '.join(origin_hits)}) — "
                f"el negocio ya declaró que le importa el historial (D6: la información ya vive en el origen). {cardinality_note}"
            ),
            evidence=origin_hits,
        )

    trust_note = (
        "" if key_columns_trusted else
        " (origen sin metadata de clave estructural — Formulario/CSV/Excel; "
        "la ausencia de key_columns acá no es evidencia de nada, solo indica "
        "que no se pudo verificar.)"
    )
    return ScdPrecheck(
        table=table_name,
        verdict=ScdVerdict.UNDECIDED,
        forced_scd_type=None,
        mutable_attributes=mutable,
        scd2_candidates=scd2_candidates,
        reason=f"sin evidencia estructural ni declaración explícita — decisión de negocio, default SCD1 si no hay señal de proyecto aplicable. {cardinality_note}{trust_note}",
    )


# ─── B: qué step de Pentaho carga la dimensión (movida desde
# dimension_step_policy.py — D11 fijó que el step se deriva de scd_type; D37
# fija de dónde sale scd_type, que D11 daba por dado. dimension_step_policy.py
# reexporta esta función, mismo patrón de excepción nombrada que
# schemas/canonical.py -> domain/canonical_types.py, para no tocar los call
# sites existentes) ─────────────────────────────────────────────────────────

def derive_dimension_step_type(scd_type: int) -> str:
    """Unica fuente de verdad para "qué step carga esta dimensión". Toda
    dimensión en dim_contracts ya declara su propia surrogate key (D2/D4 de
    la inferencia — el contrato completo es obligatorio sea SCD1 o SCD2), así
    que el único eje de decisión real es si versiona (SCD2) o no.

    Dimensiones sin surrogate key que gestionar (tablas de referencia
    estáticas, PK = clave natural) no entran en dim_contracts en absoluto —
    no llegan a esta función."""
    return "DimensionLookup" if scd_type == 2 else "CombinationLookup"
