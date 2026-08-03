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
    _synthesize_dimension_lookup_config,
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
    fuerza a DimensionLookup+update=N; el loader queda intacto.

    D57: 'Lookup Dim Producto' llega con `fields` en vocabulario modo Y
    (heredado de la premisa, ahora falsa, de que era el loader) — la policy
    debe limpiarlo, no dejarlo cruzado contra el modo N nuevo (D-1), y
    reportar la limpieza con repaired=True (no silenciosa)."""
    ktr_data = _err1_like_ktr()
    lookup_step = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    lookup_step["config"]["fields"] = [
        {"stream_field": "nombre", "table_field": "nombre", "type": "Update"},
    ]
    contracts = [_FakeDimContract("dim_producto", 2)]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    loader = next(s for s in ktr_data["steps"] if s["name"] == "Cargar Dim Producto")
    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert loader["type"] == "DimensionLookup"
    assert loader["config"].get("update", "Y") != "N"  # loader no tocado
    assert lookup["type"] == "DimensionLookup"
    assert lookup["config"]["update"] == "N"
    assert lookup["config"]["fields"] == []  # D57: vocabulario Y viejo descartado, no cruzado
    assert any(r["tipo"] == "warning" and "solo lectura" in r["mensaje"] for r in results)
    assert any(
        r.get("repaired") is True and "descartado" in r["mensaje"] and "dim_producto" in r["campo"]
        for r in results
    )


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


# ─── H51 — loader (rol) con update=N, corregido a update=Y (ítem 1 del plan) ─

def test_loader_with_update_n_is_repaired_to_update_y():
    """Caso H51: el step resuelve a rol 'loader' (única escritura sobre la
    tabla, ver role_of_dimension_step) pero su config trae update=N — se
    corrige a update=Y y se resintetiza 'fields' desde dim_contracts."""
    ktr_data = {
        "steps": [
            {"name": "Cargar Dim Producto", "type": "DimensionLookup",
             "config": {
                 "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                 "keys": [{"stream": "id_producto", "lookup": "id_producto"}],
                 "update": "N",
             }},
        ],
        "hops": [],
    }
    contracts = [_FakeDimContract(
        "dim_producto", 2,
        technical_key="sk_producto", version_field="version",
        date_from="fecha_inicio", date_to="fecha_fin",
        attributes_scd1=["nombre"], attributes_scd2=["precio"],
    )]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "Y"
    assert step["config"]["date_from"] == "fecha_inicio"
    assert step["config"]["date_to"] == "fecha_fin"
    assert step["config"]["fields"] == [
        {"stream_field": "nombre", "table_field": "nombre", "type": "Update"},
        {"stream_field": "precio", "table_field": "precio", "type": "Insert"},
    ]
    assert len(results) == 1
    assert results[0]["tipo"] == "warning"
    assert results[0]["campo"] == "dim_producto"


def test_loader_with_update_n_and_registered_override_is_left_untouched():
    """Con override registrado (campo == tabla), el loader con update=N
    queda tal como el modelo lo declaró — no se corrige, se anota info."""
    ktr_data = {
        "steps": [
            {"name": "Cargar Dim Producto", "type": "DimensionLookup",
             "config": {
                 "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                 "keys": [{"stream": "id_producto", "lookup": "id_producto"}],
                 "update": "N",
             }},
        ],
        "hops": [],
    }
    contracts = [_FakeDimContract("dim_producto", 2)]
    validaciones = [{
        "tipo": "info", "campo": "dim_producto",
        "mensaje": f"{OVERRIDE_STEP_PREFIX}loader con update=N — motivo: recarga full refresh, no versiona.",
    }]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "N"  # respetado, no reparado
    assert len(results) == 1
    assert results[0]["tipo"] == "info"


# ─── D58 — 1 solo step candidato por tabla ⇒ role=loader sin BFS ────────────

def _cargar_dim_producto_single_step_ktr():
    """Reproduce el step 'Cargar dim_producto' de la corrida real
    (etl-llm-raw-test-01_sonnet_fase4.json, ktr_2): ÚNICO DimensionLookup
    sobre dim_producto, llegado del LLM con update='N' y 'fields' en
    vocabulario modo Y (type='Update') — contradice su propia narración
    ("update=Y y todos los atributos en modo Update"). Alimenta, vía hops,
    'Cargar fact_inventario' (InsertUpdate, tabla distinta) — el mismo
    patrón que el BFS de role_of_dimension_step interpretaba (mal, D58)
    como "lookup de FK del lado del hecho"."""
    return {
        "steps": [
            {"name": "Cargar dim_producto", "type": "DimensionLookup",
             "config": {
                 "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                 "update": "N",
                 "keys": [{"stream_field": "cod_producto", "table_field": "id_producto_origen"}],
                 "fields": [
                     {"stream_field": "nombre_producto", "table_field": "nombre_producto", "type": "Update"},
                     {"stream_field": "precio_unitario", "table_field": "precio_unitario", "type": "Update"},
                 ],
                 "date_from": "fecha_inicio", "date_to": "fecha_fin", "version_field": "version",
             }},
            {"name": "Cargar fact_inventario", "type": "InsertUpdate",
             "config": {"table": "fact_inventario", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Cargar dim_producto", "to": "Cargar fact_inventario", "enabled": True},
        ],
    }


def test_single_dimension_lookup_step_per_table_resolves_loader_not_fact_lookup():
    """D58: antes de este fix, role_of_dimension_step declaraba 'fact_lookup'
    porque el BFS alcanza 'Cargar fact_inventario' (InsertUpdate, tabla
    distinta) — pese a ser el ÚNICO step de dim_producto, sin ambigüedad
    posible. Eso mandaba el step al branch fact_lookup (D57), que limpia
    'fields' pero NUNCA lo corrige a update=Y — el step seguía siendo un
    loader roto. Con D58, 1 solo candidato ⇒ role='loader' sin BFS, y cae
    en el branch H51: se corrige a update=Y y se resintetiza 'fields'."""
    ktr_data = _cargar_dim_producto_single_step_ktr()
    contracts = [_FakeDimContract(
        "dim_producto", 1,
        technical_key="sk_producto", version_field="version",
        date_from="fecha_inicio", date_to="fecha_fin",
        attributes_scd1=["nombre_producto", "precio_unitario"],
    )]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["type"] == "DimensionLookup"
    assert step["config"]["update"] == "Y"
    assert step["config"]["fields"] == [
        {"stream_field": "nombre_producto", "table_field": "nombre_producto", "type": "Update"},
        {"stream_field": "precio_unitario", "table_field": "precio_unitario", "type": "Update"},
    ]
    assert any(r["tipo"] == "warning" and "loader" in r["mensaje"] for r in results)
    assert not any(r["tipo"] == "error" for r in results)


# ─── D58 — already_readonly ya no da por bueno el vocabulario en silencio ───

def test_already_readonly_fact_lookup_with_crossed_vocabulary_is_left_untouched():
    """D58/D60 (Bloque 1, docs/refactor/02-decisiones.md): rol fact_lookup
    genuino (2 steps candidatos para dim_producto, BFS legítimamente
    aplicable) que llega YA en update=N pero con 'fields' heredado en
    vocabulario modo Y — 'already_readonly' corta con `continue` sin tocar
    'fields' (no hay contrato para saber qué hacer con esas columnas) y SIN
    reportar acá: el reporte de vocabulario cruzado es responsabilidad única
    de validators/dimension_lookup_fields.py (canal canónico decidido en D60
    para evitar el mismo problema reportado dos veces con dos redacciones —
    ver test_dimension_lookup_fields.py para la cobertura de ESE chequeo)."""
    ktr_data = _err1_like_ktr()
    lookup_step = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    lookup_step["config"]["update"] = "N"
    lookup_step["config"]["fields"] = [
        {"stream_field": "nombre", "table_field": "nombre", "type": "Update"},
    ]
    contracts = [_FakeDimContract("dim_producto", 2)]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["config"]["fields"] == [
        {"stream_field": "nombre", "table_field": "nombre", "type": "Update"},
    ]  # no reparado
    assert not any(r["campo"] == "dim_producto" and "vocabulario cruzado" in r["mensaje"] for r in results)


# ─── D58 (segunda vuelta) — 1 candidato no basta, tiene que traer los atributos

def test_single_candidate_without_contract_attributes_is_not_forced_to_loader():
    """El riesgo dejado anotado en la primera versión de D58: 1 solo step
    candidato para una tabla declarada en dim_contracts no prueba que sea
    el loader — puede ser un lookup huérfano (el LLM omitió el loader
    real). Acá el step no trae en 'fields' ningún atributo de los que el
    contrato declara (nombre, precio) — no se fuerza update=Y; se reporta
    error y el step queda tal cual, sin tocar."""
    ktr_data = {
        "steps": [
            {"name": "Lookup Huerfano Producto", "type": "DimensionLookup",
             "config": {
                 "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                 "update": "N",
                 "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}],
             }},
            {"name": "Cargar Fact Venta", "type": "InsertUpdate",
             "config": {"table": "fact_venta", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Lookup Huerfano Producto", "to": "Cargar Fact Venta", "enabled": True},
        ],
    }
    contracts = [_FakeDimContract(
        "dim_producto", 1, attributes_scd1=["nombre", "precio"],
    )]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "N"  # NO forzado a Y
    assert "fields" not in step["config"]  # no tocado
    assert any(
        r["tipo"] == "error" and "loader faltante" in r["mensaje"] and r["campo"] == "dim_producto"
        for r in results
    )


def test_single_candidate_with_partial_contract_attributes_is_not_forced_to_loader():
    """Match parcial (trae 'nombre' pero no 'precio', ambos del contrato) es
    tan indistinguible de un lookup con columnas de retorno puntuales
    (P3-1) como de un loader incompleto — se exige el conjunto COMPLETO,
    no 'alguno'. Ante la duda, se reporta, no se fuerza (D5).

    Hop hacia 'Cargar Fact Venta' (tabla distinta) es necesario para que
    role_of_dimension_step resuelva 'fact_lookup' primero — el discriminador
    de D58 solo interviene sobre ese resultado (ver comentario en
    enforce_dimension_step_policy); sin hop, el BFS ya resuelve 'loader'
    sin ambigüedad y este test no ejercitaría el discriminador."""
    ktr_data = {
        "steps": [
            {"name": "Lookup Parcial Producto", "type": "DimensionLookup",
             "config": {
                 "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                 "update": "N",
                 "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}],
                 "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": "String"}],
             }},
            {"name": "Cargar Fact Venta", "type": "InsertUpdate",
             "config": {"table": "fact_venta", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Lookup Parcial Producto", "to": "Cargar Fact Venta", "enabled": True},
        ],
    }
    contracts = [_FakeDimContract("dim_producto", 1, attributes_scd1=["nombre", "precio"])]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "N"
    assert any(r["tipo"] == "error" and "falta(n): precio" in r["mensaje"] for r in results)


def test_single_candidate_with_all_contract_attributes_resolves_loader():
    """Contraparte positiva: si el único candidato SÍ trae, en 'fields',
    todos los atributos que el contrato declara, el discriminador lo deja
    pasar como loader (mismo resultado que
    test_single_dimension_lookup_step_per_table_resolves_loader_not_fact_lookup,
    acotado a solo el chequeo del discriminador, sin hops hacia otra
    tabla)."""
    ktr_data = {
        "steps": [
            {"name": "Cargar Dim Producto", "type": "DimensionLookup",
             "config": {
                 "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                 "update": "N",
                 "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}],
                 "fields": [
                     {"stream_field": "nombre", "table_field": "nombre", "type": "Update"},
                     {"stream_field": "precio", "table_field": "precio", "type": "Update"},
                 ],
             }},
        ],
        "hops": [],
    }
    contracts = [_FakeDimContract("dim_producto", 1, attributes_scd1=["nombre", "precio"])]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "Y"
    assert not any(r["tipo"] == "error" for r in results)


# ─── Hallazgo (01-hallazgos.md) — 'sobra' + marcador 'repairable' ───────────

def _dim_producto_ktr_with_stream():
    """Análogo minimal del corpus real (etl-llm-raw-test-01_sonnet_fase4.json,
    'Cargar dim_producto'): el stream trae 'categoria' (texto crudo), NO
    'nombre_categoria' (columna real del contrato) — y 'fields' del step
    trae 'fk_categoria', que no pertenece a dim_producto (vocabulario de
    fact_inventario). RowGenerator como fuente porque su 'produces' es
    determinístico por config explícito (a diferencia de TableInput, que
    depende de parsear SQL)."""
    return {
        "steps": [
            {"name": "Generar Stream", "type": "RowGenerator", "config": {"fields": [
                {"name": "cod_producto"}, {"name": "nombre_producto"},
                {"name": "categoria"}, {"name": "precio_unitario"}, {"name": "fk_categoria"},
            ]}},
            {"name": "Cargar dim_producto", "type": "DimensionLookup", "config": {
                "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                "update": "N",
                "keys": [{"stream_field": "cod_producto", "table_field": "id_producto_origen"}],
                "fields": [
                    {"stream_field": "nombre_producto", "table_field": "nombre_producto", "type": "Update"},
                    {"stream_field": "fk_categoria", "table_field": "fk_categoria", "type": "Update"},
                    {"stream_field": "precio_unitario", "table_field": "precio_unitario", "type": "Update"},
                ],
                "date_from": "fecha_inicio", "date_to": "fecha_fin", "version_field": "version",
            }},
            {"name": "Cargar fact_inventario", "type": "InsertUpdate",
             "config": {"table": "fact_inventario", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Generar Stream", "to": "Cargar dim_producto", "enabled": True},
            {"from": "Cargar dim_producto", "to": "Cargar fact_inventario", "enabled": True},
        ],
    }


def _dim_producto_contract():
    return _FakeDimContract(
        "dim_producto", 2, technical_key="sk_producto",
        date_from="fecha_inicio", date_to="fecha_fin",
        attributes_scd1=["nombre_producto", "nombre_categoria"],
        attributes_scd2=["precio_unitario"],
    )


def test_discriminator_reports_sobra_and_marks_repairable():
    """Complementa D58 (que solo miraba qué falta): ahora también reporta
    qué 'sobra' (fk_categoria, vocabulario de fact_inventario) y marca la
    finding 'repairable' con la info estructurada que el caller
    (etl_generator._repair_dimension_loader_fields) necesita para intentar
    un repair dirigido, sin re-derivar la condición del discriminador."""
    ktr_data = _dim_producto_ktr_with_stream()
    contracts = [_dim_producto_contract()]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    assert len(results) == 1
    r = results[0]
    assert r["repairable"] is True
    assert r["step_name"] == "Cargar dim_producto"
    assert r["missing"] == ["nombre_categoria"]
    assert r["sobra"] == ["fk_categoria"]
    assert "Sobra" in r["mensaje"] and "fk_categoria" in r["mensaje"]
    # piso: step sin tocar
    step = ktr_data["steps"][1]
    assert step["config"]["update"] == "N"


def test_synthesize_field_mapping_chain_repaired_identity_and_omitted():
    """Los 3 niveles de la cadena en una sola llamada: 'nombre_producto'
    resuelve por identidad, 'nombre_categoria' por el mapeo del repair
    (inferencia real -> finding info), 'campo_inexistente' no tiene ni
    mapeo ni homónimo -> se omite + finding error. Un solo lugar construye
    'fields' (acordado explícitamente: no duplicar esta lógica en el
    caller)."""
    contract = _FakeDimContract(
        "dim_producto", 2,
        attributes_scd1=["nombre_producto", "nombre_categoria", "campo_inexistente"],
        attributes_scd2=["precio_unitario"],
    )
    findings: list[dict] = []

    cfg = _synthesize_dimension_lookup_config(
        {"table": "dim_producto", "connection": "conn_dwh"}, contract, update="Y",
        upstream_fields={"nombre_producto", "categoria", "precio_unitario"},
        repaired_mapping={"nombre_categoria": "categoria"},
        findings=findings, step_name="Cargar dim_producto", table="dim_producto",
    )

    dest_names = {f["table_field"] for f in cfg["fields"]}
    assert dest_names == {"nombre_producto", "nombre_categoria", "precio_unitario"}  # campo_inexistente omitido
    by_dest = {f["table_field"]: f["stream_field"] for f in cfg["fields"]}
    assert by_dest["nombre_producto"] == "nombre_producto"   # identidad
    assert by_dest["nombre_categoria"] == "categoria"         # mapeo del repair
    assert by_dest["precio_unitario"] == "precio_unitario"    # identidad

    infos = [f for f in findings if f["tipo"] == "info"]
    errors = [f for f in findings if f["tipo"] == "error"]
    assert len(infos) == 1 and "categoria" in infos[0]["mensaje"] and "nombre_categoria" in infos[0]["mensaje"]
    assert len(errors) == 1 and "campo_inexistente" in errors[0]["mensaje"]


def test_synthesize_rejects_repaired_mapping_not_present_in_upstream():
    """El repair también puede alucinar — un stream_field propuesto que no
    existe de verdad en upstream_fields NO se confía a ciegas; cae al mismo
    chequeo de identidad (que tampoco aplica acá) y termina omitido+error,
    igual que si no hubiera repaired_mapping."""
    contract = _FakeDimContract("dim_producto", 1, attributes_scd1=["nombre_categoria"])
    findings: list[dict] = []

    cfg = _synthesize_dimension_lookup_config(
        {}, contract, update="Y",
        upstream_fields={"categoria"},
        repaired_mapping={"nombre_categoria": "campo_alucinado"},
        findings=findings, step_name="X", table="dim_producto",
    )

    assert cfg["fields"] == []
    assert any(f["tipo"] == "error" and "nombre_categoria" in f["mensaje"] for f in findings)
    assert not any(f["tipo"] == "info" for f in findings)
