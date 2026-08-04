"""
Unit tests — D44/D51/R-K7 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md):
check_dimension_lookup_fields cierra dos defaults silenciosos del emisor
(steps/lookups.py:_step_DimensionLookup): date_from/date_to ausentes (cae a
literales 'fecha_desde'/'fecha_hasta') y fields[].type ausente o no
reconocido por Kettle (cae a 'Insert', semántica SCD2). Puro/sin LLM/sin DB.
"""
from __future__ import annotations

from app.services.ktr_builder.validators import ValidationContext
from app.services.ktr_builder.validators.dimension_lookup_fields import (
    DIMENSION_LOOKUP_FIELDS_PREFIX,
    check_dimension_lookup_fields,
)

STEP_TYPE_ALIASES: dict[str, str] = {}


def _dim_lookup(name: str, config: dict) -> dict:
    return {"name": name, "type": "DimensionLookup", "config": config}


def _ctx(steps: list[dict]) -> ValidationContext:
    return ValidationContext({"steps": steps, "hops": []}, STEP_TYPE_ALIASES, frozenset())


def test_complete_config_produces_no_findings():
    step = _dim_lookup("Cargar Dim Cliente", {
        "table": "dim_cliente", "connection": "conn_dwh", "returnfield": "sk_cliente",
        "date_from": "fecha_inicio", "date_to": "fecha_fin",
        "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": "Update"}],
    })
    assert check_dimension_lookup_fields(_ctx([step])) == []


def test_missing_date_from_is_error():
    step = _dim_lookup("Cargar Dim Cliente", {
        "table": "dim_cliente", "date_to": "fecha_fin", "fields": [],
    })
    findings = check_dimension_lookup_fields(_ctx([step]))
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert findings[0].message.startswith(DIMENSION_LOOKUP_FIELDS_PREFIX)
    assert "date_from" in findings[0].message


def test_missing_date_to_is_error():
    step = _dim_lookup("Cargar Dim Cliente", {
        "table": "dim_cliente", "date_from": "fecha_inicio", "fields": [],
    })
    findings = check_dimension_lookup_fields(_ctx([step]))
    assert len(findings) == 1
    assert "date_to" in findings[0].message


def test_field_without_type_is_error():
    step = _dim_lookup("Cargar Dim Cliente", {
        "table": "dim_cliente", "date_from": "fecha_inicio", "date_to": "fecha_fin",
        "fields": [{"stream_field": "nombre", "table_field": "nombre"}],  # sin 'type'
    })
    findings = check_dimension_lookup_fields(_ctx([step]))
    assert len(findings) == 1
    assert "sin 'type' explícito" in findings[0].message


def test_field_with_unrecognized_type_literal_is_error():
    """R-K7: DimensionLookupMeta.getUpdateType() cae en 'Insert' silenciosamente
    ante cualquier literal fuera de su tabla typeCodes — 'SCD1' no es Kettle."""
    step = _dim_lookup("Cargar Dim Cliente", {
        "table": "dim_cliente", "date_from": "fecha_inicio", "date_to": "fecha_fin",
        "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": "SCD1"}],
    })
    findings = check_dimension_lookup_fields(_ctx([step]))
    assert len(findings) == 1
    assert "SCD1" in findings[0].message


def test_field_type_case_insensitive_is_accepted():
    step = _dim_lookup("Cargar Dim Cliente", {
        "table": "dim_cliente", "date_from": "fecha_inicio", "date_to": "fecha_fin",
        "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": "update"}],
    })
    assert check_dimension_lookup_fields(_ctx([step])) == []


def test_field_type_with_padding_whitespace_is_rejected():
    """D60 (Bloque 0, hueco 0a): Kettle compara con equalsIgnoreCase(), que NO
    recorta whitespace — ' Update' (con espacio) no matchea 'Update' en
    Kettle real, aunque el .strip() ingenuo de un chequeo previo lo hubiera
    dado por válido. El pass no debe normalizar espacios antes de comparar."""
    step = _dim_lookup("Cargar Dim Cliente", {
        "table": "dim_cliente", "date_from": "fecha_inicio", "date_to": "fecha_fin",
        "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": " Update"}],
    })
    findings = check_dimension_lookup_fields(_ctx([step]))
    assert len(findings) == 1
    assert findings[0].severity == "error"


def test_field_with_unrecognized_type_predicts_kettle_effect_mode_y():
    """D60 (criterio de terminado 3): el finding tiene que predecir el efecto
    real en Kettle, no solo nombrar el vocabulario esperado — R-K7."""
    step = _dim_lookup("Cargar Dim Cliente", {
        "table": "dim_cliente", "date_from": "fecha_inicio", "date_to": "fecha_fin",
        "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": "SCD1"}],
    })
    findings = check_dimension_lookup_fields(_ctx([step]))
    assert len(findings) == 1
    assert "Insert" in findings[0].message and "R-K7" in findings[0].message


def test_field_with_crossed_vocabulary_mode_n_is_error_and_predicts_type_none():
    """D58/D60: step ya en modo N (fact_lookup, solo lectura) con 'fields'
    heredado en vocabulario modo Y ('Update') — vocabulario cruzado. Antes
    vivía duplicado en dimension_step_policy.py (D58); D60 Bloque 1 decidió
    este pass como canal único. Efecto predicho: ValueMetaFactory.
    getIdForValueMeta() cae a TYPE_NONE."""
    step = _dim_lookup("Lookup Dim Producto", {
        "table": "dim_producto", "update": "N",
        "date_from": "fecha_inicio", "date_to": "fecha_fin",
        "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": "Update"}],
    })
    findings = check_dimension_lookup_fields(_ctx([step]))
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert "TYPE_NONE" in findings[0].message


def test_combination_lookup_is_ignored():
    step = {"name": "Cargar Dim Pais", "type": "CombinationLookup", "config": {"table": "dim_pais"}}
    assert check_dimension_lookup_fields(_ctx([step])) == []
