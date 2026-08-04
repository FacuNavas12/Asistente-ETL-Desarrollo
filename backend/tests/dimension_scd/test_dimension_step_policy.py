"""
Unit tests — Parte 4 (bloque A) de la serie dim_contracts: derivación
determinista del step de dimensión a partir de scd_type, y su síntesis
post-generación. Todo puro/sin LLM — el criterio de aceptación de esta parte
es justamente que la decisión NO dependa del modelo.

D44/D51 (docs/refactor/02-decisiones.md): vocabulario uniforme por rol —
'Dimension lookup/update' para TODO scd_type, loader y fact_lookup difieren
solo en update=Y|N.

O3 (docs/refactor/30-decision-python-llm.md): enforce_dimension_step_policy
(compara lo que el modelo escribió contra lo que el contrato deriva, corrige
si difiere) se reemplaza por apply_dimension_contracts (construye el config
SIEMPRE, incondicional — el modelo ya no escribe update/return_field/
date_from/date_to/version_field/fields[].type). Varios tests de abajo están
reescritos respecto de la versión anterior de este archivo, documentado en
cada uno, no borrados en silencio: la diferencia central es que ya no existe
"config ya venía bien, se deja intacto" — se reconstruye siempre, y solo se
reporta un finding cuando hay algo genuinamente anómalo (mapeo no resoluble,
vocabulario cruzado, verificación imposible).
"""
from __future__ import annotations

from app.services.ktr_builder.dimension_step_policy import (
    OVERRIDE_STEP_PREFIX,
    apply_dimension_contracts,
    build_dimension_lookup_config,
    derive_dimension_loader_step,
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


def test_loader_config_is_rebuilt_even_when_model_already_got_it_right():
    """O3: no existe 'ya venía bien, se deja intacto' — el config se
    reconstruye siempre desde el contrato, incondicional. Acá el modelo trae
    un config que "parece" correcto (DimensionLookup, returnfield propio)
    pero Python lo pisa igual: return_field sale de contract.technical_key,
    nunca de lo que el modelo haya puesto. Sin atributos en el contrato ni
    anomalía que reportar, no hay findings — la reconstrucción es silenciosa
    cuando no hay nada que avisar."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_cliente", "type": "DimensionLookup",
             "config": {"table": "dim_cliente", "connection": "conn_dwh", "returnfield": "sk_cliente"}},
        ],
    }
    contracts = [_FakeDimContract("dim_cliente", 2, technical_key="sk_x")]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["type"] == "DimensionLookup"
    assert step["config"]["update"] == "Y"
    assert step["config"]["return_field"] == "sk_x"  # del contrato, no del 'returnfield' original
    assert step["config"]["fields"] == []  # contrato sin atributos
    assert results == []


def test_combination_lookup_loader_synthesized_to_dimension_lookup():
    """D44/D51: CombinationLookup sale de la derivación por defecto — se
    convierte a DimensionLookup, con 'fields'/'date_from'/'date_to'/
    'version_field' sintetizados desde el contrato, que ya los declara
    completos (V1/V3, prompt_validacion_src.txt). Sin ambigüedad (un único
    candidato, sin hop a otra tabla) y con el único atributo resuelto por
    identidad, no hay nada anómalo que reportar."""
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

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["type"] == "DimensionLookup"
    assert step["config"]["update"] == "Y"
    assert step["config"]["date_from"] == "fecha_inicio"
    assert step["config"]["date_to"] == "fecha_fin"
    assert step["config"]["version_field"] == "version"
    assert step["config"]["keys"] == [{"stream": "pais_id", "lookup": "id_pais_origen"}]  # preservado, no reconstruido
    assert step["config"]["fields"] == [{"stream_field": "nombre", "table_field": "nombre", "type": "Update"}]
    assert results == []  # nada anómalo que reportar


def test_registered_override_keeps_combination_lookup():
    """Con override registrado, la síntesis NO se aplica — el step queda
    como el modelo lo declaró explícitamente. Único gate — antes se
    preguntaba en tres lugares distintos de la función."""
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

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    assert results == []
    assert ktr_data["steps"][0]["type"] == "CombinationLookup"  # respetado, no sintetizado


def test_override_for_different_table_does_not_apply():
    """El override es por tabla — uno registrado para otra dimensión no
    exime a esta. Sin ambigüedad ni atributos, la síntesis es silenciosa."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_pais", "type": "CombinationLookup",
             "config": {"table": "dim_pais", "connection": "conn_dwh", "return_field": "sk_pais"}},
        ],
    }
    contracts = [_FakeDimContract("dim_pais", 1)]
    validaciones = [{"tipo": "info", "campo": "dim_cliente", "mensaje": f"{OVERRIDE_STEP_PREFIX}algo"}]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    assert ktr_data["steps"][0]["type"] == "DimensionLookup"
    assert results == []


def test_table_not_in_dim_contracts_is_ignored():
    ktr_data = {
        "steps": [
            {"name": "Cargar fact_ventas", "type": "InsertUpdate",
             "config": {"table": "fact_ventas", "connection": "conn_dwh"}},
        ],
    }
    contracts = [_FakeDimContract("dim_cliente", 2)]
    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])
    assert results == []


def test_no_dim_contracts_short_circuits():
    ktr_data = {"steps": [{"name": "x", "type": "DimensionLookup", "config": {"table": "dim_x"}}]}
    assert apply_dimension_contracts(ktr_data, [], STEP_TYPE_ALIASES, []) == []


def test_step_type_outside_dimension_vocabulary_is_reported_not_fixed():
    """Un tipo totalmente ajeno (ni DimensionLookup ni CombinationLookup)
    sobre una tabla de dim_contracts sigue sin corrección automática — es
    topología (el modelo eligió el step equivocado), no config; no hay
    contrato del cual sintetizar un tipo distinto (D60)."""
    ktr_data = {
        "steps": [
            {"name": "Cargar dim_pais", "type": "InsertUpdate",
             "config": {"table": "dim_pais", "connection": "conn_dwh"}},
        ],
    }
    contracts = [_FakeDimContract("dim_pais", 1)]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    assert ktr_data["steps"][0]["type"] == "InsertUpdate"  # sin tocar
    assert len(results) == 1
    assert results[0]["tipo"] == "error"


# ─── D16 — role_of_dimension_step + rol decide `update` ─────────────────────

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


def test_apply_dimension_contracts_forces_readonly_on_fact_lookup_scd2():
    """D16: el step 'Lookup Dim Producto' (rol fact_lookup, 2 candidatos —
    sin forzar por D58) se sintetiza con update=N; el loader queda con
    update=Y (rol propio, no forzado).

    'Lookup Dim Producto' llega con `fields` en vocabulario modo Y (heredado
    de la premisa, ahora falsa, de que era el loader) — la síntesis los
    descarta (D57) y lo reporta (D60: nunca en silencio, tipo=info)."""
    ktr_data = _err1_like_ktr()
    lookup_step = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    lookup_step["config"]["fields"] = [
        {"stream_field": "nombre", "table_field": "nombre", "type": "Update"},
    ]
    contracts = [_FakeDimContract("dim_producto", 2)]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    loader = next(s for s in ktr_data["steps"] if s["name"] == "Cargar Dim Producto")
    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert loader["type"] == "DimensionLookup"
    assert loader["config"]["update"] == "Y"  # rol propio (loader), no forzado
    assert lookup["type"] == "DimensionLookup"
    assert lookup["config"]["update"] == "N"
    assert "fields" not in lookup["config"]  # D57: vocabulario Y viejo descartado, no cruzado
    assert any(
        r["tipo"] == "info" and "descartado" in r["mensaje"] and r["campo"] == "dim_producto"
        for r in results
    )


def test_apply_dimension_contracts_rebuilds_config_even_if_already_readonly():
    """O3: no existe 'ya venía bien' — un step que llega YA en update=N se
    reconstruye igual (return_field sale del contrato, no de lo que traía).
    Sin 'fields' de origen, no hay nada que descartar ni reportar: el rol
    (fact_lookup, 2 candidatos legítimos) no cambia, y la reconstrucción es
    silenciosa."""
    ktr_data = _err1_like_ktr()
    for step in ktr_data["steps"]:
        if step["name"] == "Lookup Dim Producto":
            step["config"]["update"] = "N"
    contracts = [_FakeDimContract("dim_producto", 2, technical_key="sk_x")]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["config"]["update"] == "N"  # rol no cambió
    assert lookup["config"]["return_field"] == "sk_x"  # reconstruido desde el contrato, no "sk_producto"
    assert results == []


def test_apply_dimension_contracts_forces_readonly_scd1():
    """R-K2 (rango [date_from, date_to) resuelve bien incluso sin historial
    real): scd_type=1 se sintetiza con update=N igual que scd_type=2 — D44,
    vocabulario uniforme por rol, no por tipo."""
    ktr_data = _err1_like_ktr()
    contracts = [_FakeDimContract("dim_producto", 1)]  # SCD1 -> igual DimensionLookup (D44)

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["type"] == "DimensionLookup"
    assert lookup["config"]["update"] == "N"
    assert not any(r["tipo"] == "error" for r in results)


def test_apply_dimension_contracts_synthesizes_combination_lookup_fact_lookup_role():
    """El rol fact_lookup con CombinationLookup (que nunca tuvo modo
    solo-lectura) también se sintetiza igual — DimensionLookup(update=N)
    desde el contrato."""
    ktr_data = _err1_like_ktr()
    for step in ktr_data["steps"]:
        if step["name"] == "Lookup Dim Producto":
            step["type"] = "CombinationLookup"
            step["config"] = {
                "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                "keys": [{"stream": "id_producto", "lookup": "id_producto"}],
            }
    contracts = [_FakeDimContract("dim_producto", 1, technical_key="sk_producto")]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["type"] == "DimensionLookup"
    assert lookup["config"]["update"] == "N"
    assert "fields" not in lookup["config"]  # solo-lectura: no hace falta modo por atributo
    assert lookup["config"]["date_from"] == "fecha_inicio"
    assert lookup["config"]["date_to"] == "fecha_fin"
    assert results == []


def test_apply_dimension_contracts_respects_override_for_fact_lookup_role():
    ktr_data = _err1_like_ktr()
    contracts = [_FakeDimContract("dim_producto", 2)]
    validaciones = [{
        "tipo": "info", "campo": "dim_producto",
        "mensaje": f"{OVERRIDE_STEP_PREFIX}DimensionLookup update=Y — motivo: necesita insertar fila unknown en el mismo step.",
    }]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["config"].get("update", "Y") != "N"  # override respetado, no forzado a solo-lectura
    assert results == []


# ─── loader (rol) con update=N en origen — se sintetiza igual a update=Y ────

def test_loader_config_synthesized_regardless_of_original_update_value():
    """El step resuelve a rol 'loader' (única escritura sobre la tabla, ver
    role_of_dimension_step) — el 'update=N' que trajo el modelo no importa,
    la síntesis siempre usa el que deriva el rol."""
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

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "Y"
    assert step["config"]["date_from"] == "fecha_inicio"
    assert step["config"]["date_to"] == "fecha_fin"
    assert step["config"]["fields"] == [
        {"stream_field": "nombre", "table_field": "nombre", "type": "Update"},
        {"stream_field": "precio", "table_field": "precio", "type": "Insert"},
    ]
    assert results == []  # sin grafo (hops=[]) identidad se asume sin verificar, pero el rol nunca se forzó


def test_loader_with_update_n_and_registered_override_is_left_untouched():
    """Con override registrado (campo == tabla), el loader con update=N
    queda tal como el modelo lo declaró — no se sintetiza, se anota info."""
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

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, validaciones)

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "N"  # respetado, no sintetizado
    assert results == []


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
    """D58: role_of_dimension_step declara 'fact_lookup' porque el BFS
    alcanza 'Cargar fact_inventario' (InsertUpdate, tabla distinta) — pese a
    ser el ÚNICO step de dim_producto, sin ambigüedad posible (D16: si no es
    el loader, nadie más carga la dimensión). Con un solo candidato,
    apply_dimension_contracts fuerza a loader.

    Este step no tiene predecesor (sin hop de entrada) — el grafo no es
    resoluble desde acá, así que el mapeo de 'fields' se asume por identidad
    SIN VERIFICAR, y eso se reporta (warning) porque el rol se forzó."""
    ktr_data = _cargar_dim_producto_single_step_ktr()
    contracts = [_FakeDimContract(
        "dim_producto", 1,
        technical_key="sk_producto", version_field="version",
        date_from="fecha_inicio", date_to="fecha_fin",
        attributes_scd1=["nombre_producto", "precio_unitario"],
    )]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["type"] == "DimensionLookup"
    assert step["config"]["update"] == "Y"
    assert step["config"]["fields"] == [
        {"stream_field": "nombre_producto", "table_field": "nombre_producto", "type": "Update"},
        {"stream_field": "precio_unitario", "table_field": "precio_unitario", "type": "Update"},
    ]
    assert any(r["tipo"] == "warning" and "loader" in r["mensaje"] for r in results)
    assert not any(r["tipo"] == "error" for r in results)


def test_already_readonly_fact_lookup_gets_crossed_fields_cleared_and_reported():
    """O3 supersede D58/D60 Bloque 1: antes 'already_readonly' cortaba con
    continue sin tocar 'fields' — dejaba vocabulario cruzado (modo Y en un
    step ahora en modo N) sobrevivir hasta el XML, y el único chequeo era el
    validador aparte (validators/dimension_lookup_fields.py). Ahora la
    síntesis reconstruye el config siempre: 'fields' no aplica en modo N
    (D16) y se descarta, reportado (D60: nunca en silencio) en el mismo
    lugar que lo generó."""
    ktr_data = _err1_like_ktr()
    lookup_step = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    lookup_step["config"]["update"] = "N"
    lookup_step["config"]["fields"] = [
        {"stream_field": "nombre", "table_field": "nombre", "type": "Update"},
    ]
    contracts = [_FakeDimContract("dim_producto", 2)]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup["config"]["update"] == "N"
    assert "fields" not in lookup["config"]  # descartado, no sobrevive vocabulario cruzado
    assert any(r["tipo"] == "info" and "descartado" in r["mensaje"] for r in results)


# ─── D58 (segunda vuelta) — 1 candidato forzado a loader con grafo no resoluble

def test_orphan_lookup_single_candidate_forced_to_loader_warns_unverified():
    """O3 supersede el discriminador original de D58 (que inspeccionaba si
    'fields' del modelo ya traía el contrato completo, y si no, reportaba
    error sin tocar el step): esa evidencia dependía del config que el
    modelo escribía, y el modelo ya no escribe 'fields' con esa función —
    ya no prueba intención, es apenas una pista de mapeo.

    Con un solo candidato no puede haber doble escritor (D16) sin importar
    el rol que resuelva el BFS, así que se fuerza a loader igual. Acá el
    step no tiene predecesor (sin hop de entrada): el grafo no es resoluble,
    así que 'fields' se arma por identidad SIN VERIFICAR — y eso se reporta,
    D60, porque no hay ninguna otra señal de que este step sea de verdad el
    loader (podría ser un lookup huérfano real, con el loader faltante)."""
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

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "Y"  # forzado — único candidato, D16
    assert step["config"]["fields"] == [
        {"stream_field": "nombre", "table_field": "nombre", "type": "Update"},
        {"stream_field": "precio", "table_field": "precio", "type": "Update"},
    ]
    assert any(
        r["tipo"] == "warning" and "sin verificar" in r["mensaje"].lower() and r["campo"] == "dim_producto"
        for r in results
    )


def test_single_candidate_with_partial_fields_still_forced_when_graph_unresolvable():
    """Mismo mecanismo que el test anterior — que el modelo haya traído un
    mapeo parcial en 'fields' ('nombre' pero no 'precio') ya no cambia el
    resultado: sin grafo resoluble, ninguno de los dos atributos se puede
    verificar contra el stream real, así que ambos resuelven por identidad
    sin verificar, y el aviso es el mismo que con 'fields' vacío."""
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

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "Y"
    assert {f["table_field"] for f in step["config"]["fields"]} == {"nombre", "precio"}
    assert any(r["tipo"] == "warning" and "sin verificar" in r["mensaje"].lower() for r in results)


def test_single_candidate_with_all_contract_attributes_resolves_loader_no_hop():
    """Sin ningún hop (ni siquiera hacia otra tabla), el BFS resuelve
    'loader' directo, sin pasar por la rama de forzado — no hay warning de
    'sin verificar' porque el rol nunca se forzó, aunque el grafo tampoco
    sea resoluble acá (mismo piso de siempre: identidad sin verificar,
    silenciosa cuando el rol es genuino)."""
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

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][0]
    assert step["config"]["update"] == "Y"
    assert not any(r["tipo"] == "error" for r in results)
    assert results == []  # rol nunca forzado (nunca fue fact_lookup) -> sin aviso de verificación


# ─── Corpus real (etl-llm-raw-test-01_sonnet_fase4.json) — resuelto sin repair

def _dim_producto_ktr_with_stream():
    """Análogo minimal del corpus real: el stream trae 'categoria' (texto
    crudo), NO 'nombre_categoria' (columna real del contrato) — y 'fields'
    del step trae 'fk_categoria', que no pertenece a dim_producto
    (vocabulario de fact_inventario). RowGenerator como fuente porque su
    'produces' es determinístico por config explícito (a diferencia de
    TableInput, que depende de parsear SQL) — el grafo SÍ es resoluble acá,
    a diferencia de los tests D58 de arriba."""
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


def test_prefix_step_resolves_corpus_case_without_repair():
    """El caso real que motivó E-21/E-23: 'nombre_categoria' no tiene
    homónimo en el stream (que trae 'categoria', sin el prefijo
    descriptivo) — bajo el diseño viejo esto requería una LLAMADA APARTE al
    LLM (_repair_dimension_loader_fields, ya borrada). Acá se resuelve en la
    MISMA pasada: paso 3 de la escalera de build_dimension_lookup_config
    (prefijo 'nombre_'), sin ninguna llamada a un modelo — cierra E-21/E-23
    por construcción, no por un fix puntual.

    'fk_categoria' (vocabulario de fact_inventario, no de esta dimensión) se
    ignora con un finding info, no error — el atributo del contrato
    correspondiente se resuelve igual por su propio camino."""
    ktr_data = _dim_producto_ktr_with_stream()
    contracts = [_dim_producto_contract()]

    results = apply_dimension_contracts(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step = ktr_data["steps"][1]
    assert step["config"]["update"] == "Y"
    by_dest = {f["table_field"]: f["stream_field"] for f in step["config"]["fields"]}
    assert by_dest == {
        "nombre_producto": "nombre_producto",  # identidad
        "nombre_categoria": "categoria",       # paso 3: prefijo 'nombre_' despojado
        "precio_unitario": "precio_unitario",  # identidad
    }
    assert not any(r["tipo"] == "error" for r in results)
    assert any(r["tipo"] == "info" and "fk_categoria" in r["mensaje"] for r in results)  # sobra, ignorado
    assert any(
        r["tipo"] == "info" and "categoria" in r["mensaje"] and "nombre_categoria" in r["mensaje"]
        for r in results
    )  # mapeo inferido, visible


# ─── build_dimension_lookup_config — unidad, sin pasar por apply_dimension_contracts

def test_build_config_field_mapping_chain_proposed_identity_and_omitted():
    """Los 3 primeros pasos de la escalera en una sola llamada:
    'nombre_producto' resuelve por identidad, 'nombre_categoria' por el
    mapeo que el MODELO propuso en model_config['fields'] (revalidado contra
    upstream_fields, nunca a ciegas -> finding info porque el nombre difiere
    del atributo), 'campo_inexistente' no tiene ni mapeo propuesto ni
    homónimo ni prefijo -> se omite + finding error."""
    contract = _FakeDimContract(
        "dim_producto", 2,
        attributes_scd1=["nombre_producto", "nombre_categoria", "campo_inexistente"],
        attributes_scd2=["precio_unitario"],
    )

    cfg, findings = build_dimension_lookup_config(
        contract, update="Y",
        model_config={
            "table": "dim_producto", "connection": "conn_dwh",
            "fields": [{"stream_field": "categoria", "table_field": "nombre_categoria"}],
        },
        upstream_fields={"nombre_producto", "categoria", "precio_unitario"},
        step_name="Cargar dim_producto", table="dim_producto",
    )

    dest_names = {f["table_field"] for f in cfg["fields"]}
    assert dest_names == {"nombre_producto", "nombre_categoria", "precio_unitario"}  # campo_inexistente omitido
    by_dest = {f["table_field"]: f["stream_field"] for f in cfg["fields"]}
    assert by_dest["nombre_producto"] == "nombre_producto"   # identidad
    assert by_dest["nombre_categoria"] == "categoria"         # mapeo propuesto por el modelo
    assert by_dest["precio_unitario"] == "precio_unitario"    # identidad

    infos = [f for f in findings if f["tipo"] == "info"]
    errors = [f for f in findings if f["tipo"] == "error"]
    assert len(infos) == 1 and "categoria" in infos[0]["mensaje"] and "nombre_categoria" in infos[0]["mensaje"]
    assert len(errors) == 1 and "campo_inexistente" in errors[0]["mensaje"]


def test_build_config_rejects_proposed_mapping_not_present_in_upstream():
    """El modelo también puede alucinar el mapeo — un stream_field propuesto
    que no existe de verdad en upstream_fields NO se confía a ciegas; si
    identidad y prefijo tampoco resuelven (nombres sin relación), el
    atributo se omite + error, igual que si el modelo no hubiera propuesto
    nada."""
    contract = _FakeDimContract("dim_producto", 1, attributes_scd1=["categoria_especial"])

    cfg, findings = build_dimension_lookup_config(
        contract, update="Y",
        model_config={"fields": [{"stream_field": "campo_alucinado", "table_field": "categoria_especial"}]},
        upstream_fields={"otro_campo"},
        step_name="X", table="dim_producto",
    )

    assert cfg["fields"] == []
    assert any(f["tipo"] == "error" and "categoria_especial" in f["mensaje"] for f in findings)
    assert not any(f["tipo"] == "info" for f in findings)
