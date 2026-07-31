"""
Unit tests — Parte 4 (bloque A) de la serie dim_contracts: derivación
determinista del step de dimensión a partir de scd_type, y su enforcement
post-generación. Todo puro/sin LLM — el criterio de aceptación de esta parte
es justamente que la decisión NO dependa del modelo.

D44/D51 (docs/refactor/02-decisiones.md): vocabulario uniforme por rol —
'Dimension lookup/update' para TODO scd_type, loader y fact_lookup difieren
solo en update=Y|N. La única rama de auto-fix segura se invirtió: antes era
DimensionLookup -> CombinationLookup (downgrade); ahora es CombinationLookup
-> DimensionLookup (sintetizando fields/date_from/date_to/version_field desde
el contrato). Varios tests de abajo están invertidos respecto de la versión
anterior de este archivo — documentado en cada uno, no borrados en silencio.
"""
from __future__ import annotations

from app.services.ktr_builder.dimension_step_policy import (
    OVERRIDE_STEP_PREFIX,
    derive_dimension_loader_step,
    enforce_dimension_step_policy,
    role_of_dimension_step,
)
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES


class _FakeDimContract:
    def __init__(
        self,
        table: str,
        scd_type: int,
        *,
        technical_key: str = "sk_x",
        version_field: str = "version",
        date_from: str = "fecha_inicio",
        date_to: str = "fecha_fin",
        attributes_scd1: list[str] | None = None,
        attributes_scd2: list[str] | None = None,
    ):
        self.table = table
        self.scd_type = scd_type
        self.technical_key = technical_key
        self.version_field = version_field
        self.date_from = date_from
        self.date_to = date_to
        self.attributes_scd1 = attributes_scd1 or []
        self.attributes_scd2 = attributes_scd2 or []


def test_loader_step_is_dimension_lookup_for_every_scd_type():
    """R-K7: scd_type==0 no tiene semántica propia en Kettle — colapsa a 1."""
    assert derive_dimension_loader_step(0) == "DimensionLookup"
    assert derive_dimension_loader_step(1) == "DimensionLookup"
    assert derive_dimension_loader_step(2) == "DimensionLookup"


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


def test_combination_lookup_loader_repaired_to_dimension_lookup():
    """INVERTIDO (D44/D51): antes esta dirección (DimensionLookup ->
    CombinationLookup) era el downgrade seguro; ahora es al revés —
    CombinationLookup se repara a DimensionLookup sintetizando fields (con
    modo por atributo)/date_from/date_to/version_field desde el contrato,
    que ya los declara completos (V1/V3, prompt_validacion_src.txt)."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_pais", "type": "CombinationLookup",
             "config": {
                 "table": "dim_pais", "connection": "conn_dwh", "return_field": "sk_pais",
                 "keys": [{"stream": "pais_id", "lookup": "id_pais_origen"}],
             }},
        ],
    }
    contracts = [_FakeDimContract(
        "dim_pais", 1,
        technical_key="sk_pais", version_field="version",
        date_from="fecha_inicio", date_to="fecha_fin",
        attributes_scd1=["nombre"], attributes_scd2=[],
    )]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["type"] == "DimensionLookup"
    assert step["config"]["update"] == "Y"
    assert step["config"]["date_from"] == "fecha_inicio"
    assert step["config"]["date_to"] == "fecha_fin"
    assert step["config"]["version_field"] == "version"
    assert step["config"]["keys"] == [{"stream": "pais_id", "lookup": "id_pais_origen"}]  # preservado, no reconstruido
    assert step["config"]["fields"] == [{"stream_field": "nombre", "table_field": "nombre", "type": "Update"}]
    assert len(results) == 1
    assert results[0]["tipo"] == "warning"
    assert results[0]["campo"] == "dim_pais"


def test_registered_override_keeps_combination_lookup():
    """Con override registrado, el auto-fix NO se aplica — el step queda
    como el modelo lo declaró explícitamente."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_pais", "type": "CombinationLookup",
             "config": {"table": "dim_pais", "connection": "conn_dwh", "return_field": "sk_pais"}},
        ],
    }
    contracts = [_FakeDimContract("dim_pais", 1)]
    validaciones = [{
        "tipo": "info", "campo": "dim_pais",
        "mensaje": f"{OVERRIDE_STEP_PREFIX}CombinationLookup — motivo: dimensión junk, no mantiene atributos a propósito.",
    }]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    assert results == []
    assert ktr_data["steps"][0]["type"] == "CombinationLookup"  # respetado, no reparado


def test_override_for_different_table_does_not_apply():
    """El override es por tabla — uno registrado para otra dimensión no exime a esta."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_pais", "type": "CombinationLookup",
             "config": {"table": "dim_pais", "connection": "conn_dwh", "return_field": "sk_pais"}},
        ],
    }
    contracts = [_FakeDimContract("dim_pais", 1)]
    validaciones = [{"tipo": "info", "campo": "dim_cliente", "mensaje": f"{OVERRIDE_STEP_PREFIX}algo"}]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    assert ktr_data["steps"][0]["type"] == "DimensionLookup"
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


def test_step_type_outside_dimension_vocabulary_is_reported_not_fixed():
    """Un tipo totalmente ajeno (ni DimensionLookup ni CombinationLookup)
    sobre una tabla de dim_contracts sigue sin corrección automática."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_pais", "type": "InsertUpdate",
             "config": {"table": "dim_pais", "connection": "conn_dwh"}},
        ],
    }
    contracts = [_FakeDimContract("dim_pais", 1)]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    assert ktr_data["steps"][0]["type"] == "InsertUpdate"  # sin tocar
    assert len(results) == 1
    assert results[0]["tipo"] == "error"


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


def test_enforce_dimension_step_policy_repairs_fact_lookup_scd1():
    """INVERTIDO (D44/D51/R-K2): antes (D16 residual) esto se reportaba sin
    reparar porque CombinationLookup no tenía modo solo-lectura y
    DimensionLookup+update=N se consideraba inseguro sin historial real.
    R-K2 (rango [date_from, date_to) resuelve bien incluso sin historial)
    cierra ese residual — ahora se repara igual que scd_type==2."""
    ktr_data = _err1_like_ktr()
    contracts = [_FakeDimContract("dim_producto", 1)]  # SCD1 -> igual DimensionLookup (D44)

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["type"] == "DimensionLookup"
    assert lookup["config"]["update"] == "N"  # reparado, no solo reportado
    assert any(r["tipo"] == "warning" and "solo lectura" in r["mensaje"] for r in results)
    assert not any(r["tipo"] == "error" for r in results)


def test_enforce_dimension_step_policy_repairs_combination_lookup_fact_lookup_role():
    """Caso nuevo (D44/D51): el rol fact_lookup con CombinationLookup (que
    nunca tuvo modo solo-lectura) también se repara, sintetizando el
    DimensionLookup(update=N) equivalente desde el contrato — antes esta
    combinación no estaba cubierta en absoluto (D16 residual la excluía)."""
    ktr_data = _err1_like_ktr()
    for step in ktr_data["steps"]:
        if step["name"] == "Lookup Dim Producto":
            step["type"] = "CombinationLookup"
            step["config"] = {
                "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                "keys": [{"stream": "id_producto", "lookup": "id_producto"}],
            }
    contracts = [_FakeDimContract("dim_producto", 1, technical_key="sk_producto")]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["type"] == "DimensionLookup"
    assert lookup["config"]["update"] == "N"
    assert "fields" not in lookup["config"]  # solo-lectura: no hace falta modo por atributo
    assert lookup["config"]["date_from"] == "fecha_inicio"
    assert lookup["config"]["date_to"] == "fecha_fin"
    assert len(results) == 1
    assert results[0]["tipo"] == "warning"


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
