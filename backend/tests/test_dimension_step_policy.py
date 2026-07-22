"""
Unit tests — Parte 4 (bloque A) de la serie dim_contracts: derivación
determinista del step de dimensión a partir de scd_type, y su enforcement
post-generación. Todo puro/sin LLM — el criterio de aceptación de esta parte
es justamente que la decisión NO dependa del modelo.
"""
from __future__ import annotations

from app.services.ktr_builder.dimension_step_policy import (
    OVERRIDE_STEP_PREFIX,
    derive_dimension_step_type,
    enforce_dimension_step_policy,
)
from app.services.ktr_builder.registry import STEP_TYPE_ALIASES


class _FakeDimContract:
    def __init__(self, table: str, scd_type: int):
        self.table = table
        self.scd_type = scd_type


def test_scd2_derives_dimension_lookup():
    assert derive_dimension_step_type(2) == "DimensionLookup"


def test_scd1_derives_combination_lookup():
    assert derive_dimension_step_type(1) == "CombinationLookup"


def test_scd0_derives_combination_lookup():
    assert derive_dimension_step_type(0) == "CombinationLookup"


def test_matching_step_is_left_untouched():
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_cliente", "type": "DimensionLookup",
             "config": {"table": "dim_cliente", "connection": "conn_dwh", "returnfield": "sk_cliente"}},
        ],
    }
    contracts = [_FakeDimContract("dim_cliente", 2)]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    assert results == []
    assert ktr_data["steps"][0]["type"] == "DimensionLookup"


def test_dimension_lookup_downgraded_to_combination_when_scd_type_not_2():
    """Downgrade seguro: CombinationLookup es un subconjunto del config de
    DimensionLookup — no hace falta inventar nada para corregirlo."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_pais", "type": "DimensionLookup",
             "config": {
                 "table": "dim_pais", "connection": "conn_dwh", "returnfield": "sk_pais",
                 "keys": [{"stream_field": "pais_id", "table_field": "id_pais_origen"}],
                 "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": "Insert"}],
                 "date_from": "fecha_inicio", "date_to": "fecha_fin",
             }},
        ],
    }
    contracts = [_FakeDimContract("dim_pais", 1)]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["type"] == "CombinationLookup"
    assert "keys" in step["config"]
    assert "fields" not in step["config"]
    assert "date_from" not in step["config"]
    assert len(results) == 1
    assert results[0]["tipo"] == "warning"
    assert results[0]["campo"] == "dim_pais"


def test_combination_lookup_where_dimension_lookup_required_is_reported_not_fixed():
    """No hay downgrade seguro en esta dirección: faltarían fields/date_from/
    date_to que nadie puede inventar sin criterio de negocio — se reporta,
    no se repara (mismo principio que check_missing_required_fields)."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_cliente", "type": "CombinationLookup",
             "config": {
                 "table": "dim_cliente", "connection": "conn_dwh", "return_field": "sk_cliente",
                 "keys": [{"stream_field": "cliente_id", "table_field": "id_cliente_origen"}],
             }},
        ],
    }
    contracts = [_FakeDimContract("dim_cliente", 2)]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    assert ktr_data["steps"][0]["type"] == "CombinationLookup"  # sin tocar
    assert len(results) == 1
    assert results[0]["tipo"] == "error"
    assert results[0]["campo"] == "dim_cliente"


def test_registered_override_is_respected():
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_pais", "type": "DimensionLookup",
             "config": {"table": "dim_pais", "connection": "conn_dwh", "returnfield": "sk_pais"}},
        ],
    }
    contracts = [_FakeDimContract("dim_pais", 1)]
    validaciones = [{
        "tipo": "info", "campo": "dim_pais",
        "mensaje": f"{OVERRIDE_STEP_PREFIX}DimensionLookup — motivo: hechos huérfanos necesitan fila desconocido.",
    }]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    assert results == []
    assert ktr_data["steps"][0]["type"] == "DimensionLookup"  # respetado, no degradado


def test_override_for_different_table_does_not_apply():
    """El override es por tabla — uno registrado para otra dimensión no exime a esta."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_pais", "type": "DimensionLookup",
             "config": {"table": "dim_pais", "connection": "conn_dwh", "returnfield": "sk_pais"}},
        ],
    }
    contracts = [_FakeDimContract("dim_pais", 1)]
    validaciones = [{"tipo": "info", "campo": "dim_cliente", "mensaje": f"{OVERRIDE_STEP_PREFIX}algo"}]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    assert ktr_data["steps"][0]["type"] == "CombinationLookup"
    assert len(results) == 1


def test_table_not_in_dim_contracts_is_ignored():
    ktr_data = {
        "steps": [
            {"name": "Cargar fact_ventas", "type": "InsertUpdate",
             "config": {"table": "fact_ventas", "connection": "conn_dwh"}},
        ],
    }
    contracts = [_FakeDimContract("dim_cliente", 2)]
    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])
    assert results == []


def test_no_dim_contracts_short_circuits():
    ktr_data = {"steps": [{"name": "x", "type": "DimensionLookup", "config": {"table": "dim_x"}}]}
    assert enforce_dimension_step_policy(ktr_data, [], STEP_TYPE_ALIASES, []) == []
