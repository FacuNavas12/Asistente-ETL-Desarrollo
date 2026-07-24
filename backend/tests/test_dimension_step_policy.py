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
    role_of_dimension_step,
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


# ─── D16 — role_of_dimension_step + Paso 4 (loader vs. fact-lookup) ─────────

def _err1_like_ktr():
    """Reproduce la forma de err1.ktr/err2.ktr (H21): 'Cargar Dim Producto'
    (DimensionLookup, rama muerta sin hop de salida) + 'Lookup Dim Producto'
    (DimensionLookup, alimenta 'Cargar Fact Venta') — mismo doble-escritor
    sobre dim_producto que dispara C1-bis."""
    return {
        "steps": [
            {"name": "Leer Staging Productos", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Cargar Dim Producto", "type": "DimensionLookup",
             "config": {"table": "dim_producto", "connection": "conn_dwh", "returnfield": "sk_producto",
                        "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}]}},
            {"name": "Leer Staging Ventas", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Lookup Dim Producto", "type": "DimensionLookup",
             "config": {"table": "dim_producto", "connection": "conn_dwh", "returnfield": "sk_producto",
                        "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}]}},
            {"name": "Cargar Fact Venta", "type": "InsertUpdate",
             "config": {"table": "fact_venta", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Leer Staging Productos", "to": "Cargar Dim Producto", "enabled": True},
            {"from": "Leer Staging Ventas", "to": "Lookup Dim Producto", "enabled": True},
            {"from": "Lookup Dim Producto", "to": "Cargar Fact Venta", "enabled": True},
        ],
    }


def test_role_of_dimension_step_classifies_loader_vs_fact_lookup():
    ktr_data = _err1_like_ktr()
    assert role_of_dimension_step("Cargar Dim Producto", "dim_producto", ktr_data, STEP_TYPE_ALIASES) == "loader"
    assert role_of_dimension_step("Lookup Dim Producto", "dim_producto", ktr_data, STEP_TYPE_ALIASES) == "fact_lookup"


def test_loader_with_checkpoint_writelog_stays_loader():
    """Un loader que además loguea un checkpoint (WriteToLog) no debe
    clasificar como fact_lookup — WriteToLog no es 'escritor de tabla'."""
    ktr_data = _err1_like_ktr()
    ktr_data["steps"].append({"name": "Log Carga Producto", "type": "WriteToLog", "config": {"message": "ok"}})
    ktr_data["hops"].append({"from": "Cargar Dim Producto", "to": "Log Carga Producto", "enabled": True})
    assert role_of_dimension_step("Cargar Dim Producto", "dim_producto", ktr_data, STEP_TYPE_ALIASES) == "loader"


def test_enforce_dimension_step_policy_forces_readonly_on_fact_lookup_scd2():
    """Paso 4 (D16): el step 'Lookup Dim Producto' (rol fact_lookup) se
    fuerza a DimensionLookup+update=N; el loader queda intacto."""
    ktr_data = _err1_like_ktr()
    contracts = [_FakeDimContract("dim_producto", 2)]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    loader = next(s for s in ktr_data["steps"] if s["name"] == "Cargar Dim Producto")
    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert loader["type"] == "DimensionLookup"
    assert loader["config"].get("update", "Y") != "N"  # loader no tocado
    assert lookup["type"] == "DimensionLookup"
    assert lookup["config"]["update"] == "N"
    assert any(r["tipo"] == "warning" and "solo lectura" in r["mensaje"] for r in results)


def test_enforce_dimension_step_policy_already_readonly_is_left_untouched():
    ktr_data = _err1_like_ktr()
    for step in ktr_data["steps"]:
        if step["name"] == "Lookup Dim Producto":
            step["config"]["update"] = "N"
    contracts = [_FakeDimContract("dim_producto", 2)]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    assert results == []


def test_enforce_dimension_step_policy_reports_not_repairs_fact_lookup_scd1():
    """scd_type sin versionar: no hay date_from/date_to seguras para forzar
    DimensionLookup+update=N — se reporta (no se repara), D16 residual."""
    ktr_data = _err1_like_ktr()
    contracts = [_FakeDimContract("dim_producto", 1)]  # SCD1 -> CombinationLookup esperado

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["type"] == "DimensionLookup"  # sin tocar — no repara
    fact_lookup_errors = [r for r in results if r["tipo"] == "error" and "lookup de FK" in r["mensaje"]]
    assert len(fact_lookup_errors) == 1
    # El mensaje apunta al fix concreto (TableInput+StreamLookup, ver system_etl.txt),
    # no a "revisar a mano" genérico — residual cerrado del lado de guía, D16.
    assert "TableInput" in fact_lookup_errors[0]["mensaje"]
    assert "StreamLookup" in fact_lookup_errors[0]["mensaje"]


def test_enforce_dimension_step_policy_respects_override_for_fact_lookup_role():
    ktr_data = _err1_like_ktr()
    contracts = [_FakeDimContract("dim_producto", 2)]
    validaciones = [{
        "tipo": "info", "campo": "dim_producto",
        "mensaje": f"{OVERRIDE_STEP_PREFIX}DimensionLookup update=Y — motivo: necesita insertar fila unknown en el mismo step.",
    }]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["config"].get("update", "Y") != "N"  # override respetado, no forzado a solo-lectura
    assert results == []
