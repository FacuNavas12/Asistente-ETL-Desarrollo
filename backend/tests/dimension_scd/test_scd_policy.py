"""
Unit tests — D37 (docs/refactor/02-decisiones.md): criterio determinista de
SCD1 vs SCD2. Todo puro/sin LLM/sin DB — mismo espíritu que
test_dimension_step_policy.py: el criterio de aceptación es que las reglas
mecánicas y estructurales no dependan del modelo.
"""
from __future__ import annotations

from app.domain.scd import (
    ATTRIBUTE_UPDATE_TYPE_CODES,
    ScdVerdict,
    classify_scd_candidates,
    derive_attribute_update_mode,
    derive_dimension_loader_step,
    derive_fact_lookup_step,
    detect_history_intent,
    is_calendar_dimension,
)
from app.services.ktr_builder import dimension_step_policy


# ─── Reexportación (D44/D51): dimension_step_policy no debe bifurcar la función ───

def test_derive_dimension_loader_step_reexport_is_same_object():
    assert dimension_step_policy.derive_dimension_loader_step is derive_dimension_loader_step


def test_derive_fact_lookup_step_reexport_is_same_object():
    assert dimension_step_policy.derive_fact_lookup_step is derive_fact_lookup_step


def test_derive_attribute_update_mode_reexport_is_same_object():
    assert dimension_step_policy.derive_attribute_update_mode is derive_attribute_update_mode


# ─── D44/D51/R-K7: vocabulario uniforme por rol — un solo step para TODO scd_type ───

def test_loader_step_is_dimension_lookup_for_every_scd_type():
    """R-K7 Postura A: scd_type==0 no tiene semántica propia en Kettle
    (ningún modo de atributo significa 'no tocar si ya existe') — colapsa a
    la misma configuración que scd_type==1. CombinationLookup sale de la
    derivación por defecto (D44) — solo alcanzable vía override registrado."""
    assert derive_dimension_loader_step(0) == "DimensionLookup"
    assert derive_dimension_loader_step(1) == "DimensionLookup"
    assert derive_dimension_loader_step(2) == "DimensionLookup"


def test_fact_lookup_step_is_dimension_lookup_for_every_scd_type():
    """R-K2: el rango [date_from, date_to) resuelve bien incluso en una
    dimensión sin historial real — ya no hay excepción TableInput+StreamLookup
    para scd_type 0/1 (D16 residual, cerrado)."""
    assert derive_fact_lookup_step(0) == "DimensionLookup"
    assert derive_fact_lookup_step(1) == "DimensionLookup"
    assert derive_fact_lookup_step(2) == "DimensionLookup"


def test_attribute_update_mode_scd2_is_insert_rest_is_update():
    """S-8: el modo es propiedad del ATRIBUTO, no de la dimensión."""
    assert derive_attribute_update_mode("categoria", attributes_scd1=[], attributes_scd2=["categoria"]) == "Insert"
    assert derive_attribute_update_mode("nombre", attributes_scd1=["nombre"], attributes_scd2=["categoria"]) == "Update"
    # scd_type==0 colapsado a 1: TODO atributo no-clave cae acá (ninguno en attributes_scd2).
    assert derive_attribute_update_mode("anio", attributes_scd1=["anio", "mes"], attributes_scd2=[]) == "Update"


def test_attribute_update_type_codes_matches_kettle_source():
    """R-K7: DimensionLookupMeta.getUpdateType() typeCodes — cualquier literal
    fuera de esta lista cae silenciosamente en 'Insert' (Kettle), sin error."""
    assert ATTRIBUTE_UPDATE_TYPE_CODES == (
        "Insert", "Update", "Punch through",
        "DateInsertedOrUpdated", "DateInserted", "DateUpdated", "LastVersion",
    )


# ─── is_calendar_dimension: predicado único (D51), reusado por el guard de contrato ───

def test_is_calendar_dimension_matches_name_single_key_date_type():
    assert is_calendar_dimension("dim_fecha", ["fecha"], ["fecha"]) is True


def test_is_calendar_dimension_false_without_name_match():
    assert is_calendar_dimension("dim_cliente", ["id_cliente_origen"], ["cliente_fecha_alta"]) is False


def test_is_calendar_dimension_false_with_two_keys():
    assert is_calendar_dimension("dim_tiempo", ["fecha", "turno"], ["fecha"]) is False


def test_is_calendar_dimension_false_when_key_not_date_typed():
    assert is_calendar_dimension("dim_fecha", ["fecha"], []) is False


# ─── Regla 0: sin clave natural durable ───────────────────────────────────────

def test_no_key_columns_forces_scd1_no_history_possible():
    result = classify_scd_candidates(
        table_name="dim_catalogo",
        column_names=["descripcion", "activo_bool"],
        key_columns=[],
    )
    assert result.verdict == ScdVerdict.NO_HISTORY_POSSIBLE
    assert result.forced_scd_type == 1
    assert "clave natural durable" in result.reason


def test_no_key_columns_untrusted_does_not_force_anything():
    """Regresión: Formulario/CSV/Excel nunca declaran PK/UNIQUE — key_columns=[]
    ahí es "no se sabe", no "confirmado sin clave". Encontrado en
    test_refine_untouched_dimension_preserves_dim_contracts
    (test_structured_outputs.py): sin este parámetro, la regla 0 degradaba en
    silencio un dim_contract legítimo scd_type=2 armado a mano."""
    result = classify_scd_candidates(
        table_name="dim_cliente",
        column_names=["id_cliente_origen", "nombre"],
        key_columns=[],
        key_columns_trusted=False,
    )
    assert result.verdict != ScdVerdict.NO_HISTORY_POSSIBLE
    assert result.mutable_attributes == ("id_cliente_origen", "nombre")


# ─── Regla 1: sin atributos mutables ──────────────────────────────────────────

def test_no_mutable_attributes_forces_scd1():
    result = classify_scd_candidates(
        table_name="dim_pais",
        column_names=["id_pais_origen", "codigo_iso"],
        key_columns=["id_pais_origen", "codigo_iso"],
    )
    assert result.verdict == ScdVerdict.NO_HISTORY_POSSIBLE
    assert result.forced_scd_type == 1
    assert result.mutable_attributes == ()


# ─── Regla 2: dimensión de calendario ─────────────────────────────────────────

def test_calendar_dimension_forces_scd0():
    result = classify_scd_candidates(
        table_name="dim_fecha",
        column_names=["fecha", "anio", "mes", "dia_semana"],
        key_columns=["fecha"],
        date_type_columns=["fecha"],
    )
    assert result.verdict == ScdVerdict.NO_HISTORY_POSSIBLE
    assert result.forced_scd_type == 0


def test_calendar_name_alone_does_not_match_control_case():
    """cliente_fecha_alta es un ATRIBUTO, no el nombre de la tabla — no debe
    disparar la regla de calendario."""
    result = classify_scd_candidates(
        table_name="dim_cliente",
        column_names=["id_cliente_origen", "nombre", "cliente_fecha_alta"],
        key_columns=["id_cliente_origen"],
        date_type_columns=["cliente_fecha_alta"],
    )
    assert result.verdict != ScdVerdict.NO_HISTORY_POSSIBLE or result.forced_scd_type != 0


def test_calendar_rule_requires_exactly_one_date_key():
    """Dos claves (aunque una sea fecha) no matchea — angosto a propósito."""
    result = classify_scd_candidates(
        table_name="dim_tiempo",
        column_names=["fecha", "turno", "anio"],
        key_columns=["fecha", "turno"],
        date_type_columns=["fecha"],
    )
    assert result.forced_scd_type != 0 or result.verdict != ScdVerdict.NO_HISTORY_POSSIBLE


# ─── scd2_candidates: cardinalidad ────────────────────────────────────────────

def test_scd2_candidates_excludes_near_unique_and_constant():
    result = classify_scd_candidates(
        table_name="dim_producto",
        column_names=["id_producto_origen", "categoria", "codigo_barras_unico", "activo_constante"],
        key_columns=["id_producto_origen"],
        distinct_counts={"categoria": 8, "codigo_barras_unico": 995, "activo_constante": 1},
        row_count_estimate=1000,
    )
    assert "categoria" in result.scd2_candidates
    assert "codigo_barras_unico" not in result.scd2_candidates
    assert "activo_constante" not in result.scd2_candidates
    assert "proxy" in result.reason.lower() or "PROXY" in result.reason


def test_scd2_candidates_without_profile_falls_back_to_all_mutable_and_says_so():
    result = classify_scd_candidates(
        table_name="dim_producto",
        column_names=["id_producto_origen", "categoria", "marca"],
        key_columns=["id_producto_origen"],
        distinct_counts=None,
        row_count_estimate=None,
    )
    assert set(result.scd2_candidates) == {"categoria", "marca"}
    assert "sin perfil" in result.reason.lower()


# ─── Regla 3: intención declarada explícitamente ──────────────────────────────

def test_declared_intent_2_yields_history_declared():
    result = classify_scd_candidates(
        table_name="dim_cliente",
        column_names=["id_cliente_origen", "categoria"],
        key_columns=["id_cliente_origen"],
        declared_intent="2",
    )
    assert result.verdict == ScdVerdict.HISTORY_DECLARED
    assert "dwh_intent.scd_type=2" in result.evidence


def test_declared_intent_does_not_override_mechanical_impossibility():
    """Regla 0/1 (mecánica) es vinculante incluso sobre una declaración
    explícita del usuario."""
    result = classify_scd_candidates(
        table_name="dim_pais",
        column_names=["id_pais_origen"],
        key_columns=["id_pais_origen"],
        declared_intent="2",
    )
    assert result.verdict == ScdVerdict.NO_HISTORY_POSSIBLE
    assert result.forced_scd_type == 1


# ─── Regla 3-bis: evidencia estructural en el origen ──────────────────────────

def test_origin_history_columns_yield_history_declared():
    result = classify_scd_candidates(
        table_name="dim_producto",
        column_names=["id_producto_origen", "categoria", "fecha_desde", "fecha_hasta"],
        key_columns=["id_producto_origen"],
    )
    assert result.verdict == ScdVerdict.HISTORY_DECLARED
    assert "fecha_desde" in result.evidence
    assert "fecha_hasta" in result.evidence


def test_undecided_when_no_signal_at_all():
    result = classify_scd_candidates(
        table_name="dim_cliente",
        column_names=["id_cliente_origen", "nombre", "email"],
        key_columns=["id_cliente_origen"],
    )
    assert result.verdict == ScdVerdict.UNDECIDED


# ─── detect_history_intent: señal de PROYECTO, nunca veredicto por entidad ────

def test_detect_history_intent_matches_real_business_rule():
    signal = detect_history_intent("Se necesita el histórico de cambios de categoría del producto.")
    assert signal.matched
    assert any("histór" in p or "cambios de" in p for p in signal.matched_phrases)
    assert signal.compliance is False


def test_detect_history_intent_no_match_on_clean_text():
    signal = detect_history_intent("Consolidar ventas mensuales por sucursal.")
    assert not signal.matched


def test_detect_history_intent_compliance_vocabulary():
    signal = detect_history_intent("Se requiere trazabilidad por auditoría y cierre contable mensual.")
    assert signal.matched
    assert signal.compliance is True


def test_detect_history_intent_false_positive_case_d_is_still_a_match_but_caller_must_scope_it():
    """'carga histórica de ventas' matchea la frase — el punto de D37 es que
    ESTA función nunca decide a qué dimensión aplica; eso es responsabilidad
    del llamador (bloque de prompt) y del modelo. La corrección de alcance no
    se prueba acá, se prueba en que classify_scd_candidates no recibe esta
    señal como input en absoluto."""
    signal = detect_history_intent("Se requiere la carga histórica de ventas de los últimos 5 años.")
    assert signal.matched  # la frase matchea — es la señal de proyecto, no un veredicto
    # classify_scd_candidates no tiene ningún parámetro que reciba `signal`:
    # confirmalo por diseño de firma, no por comportamiento en runtime.
    import inspect
    sig = inspect.signature(classify_scd_candidates)
    assert "business_rules" not in sig.parameters
    assert "process_goal" not in sig.parameters
    assert "history_signal" not in sig.parameters
