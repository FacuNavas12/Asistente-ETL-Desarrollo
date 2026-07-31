"""F3 — algoritmo de corte puro (build_rw_matrix + compute_cut), validado
contra la forma de err1.ktr/err2.ktr (H21/D7). Solo el algoritmo — el wiring
a etl_generator.py/_build_job_plan/stitch_lineage queda pendiente (ver nota
de estado al pie de fragmentation.py)."""
from __future__ import annotations

from app.services.ktr_builder.fragmentation import (
    build_rw_matrix, compute_cut, split_ktr_by_cut, validate_stage_contract,
)
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES
from app.services.ktr_builder.validators.base import Finding


def _err1_like_ktr():
    return {
        "steps": [
            {"name": "Leer Staging Productos", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Cargar Dim Producto", "type": "DimensionLookup",
             "config": {"table": "dim_producto", "connection": "conn_dwh", "returnfield": "sk_producto",
                        "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}]}},
            {"name": "Leer Staging Ventas", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Lookup Dim Producto", "type": "DimensionLookup",
             "config": {"table": "dim_producto", "connection": "conn_dwh", "returnfield": "sk_producto",
                        "update": "N",  # ya forzado por dimension_step_policy (D16, Paso 4)
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


def test_build_rw_matrix_classifies_roles():
    """D45 punto 2: clave (conexión, tabla) — 'conn_dwh' viene declarado
    explícito en la fixture (dim_producto/fact_venta), no inferido."""
    matrix, findings = build_rw_matrix(_err1_like_ktr(), STEP_TYPE_ALIASES)
    assert findings == []
    assert matrix[("conn_dwh", "dim_producto")]["Cargar Dim Producto"] == "RW"
    assert matrix[("conn_dwh", "dim_producto")]["Lookup Dim Producto"] == "R"  # update=N (D16)
    assert matrix[("conn_dwh", "fact_venta")]["Cargar Fact Venta"] == "W"
    # TableInput sin resolver inyectado: invisible, comportamiento previo a D45.
    assert not any("Leer Staging" in roles for roles in matrix.values())


def test_compute_cut_splits_loader_from_fact_branch_err1_err2():
    """dim_producto dispara C1 (RW + R en steps distintos, ya en componentes
    de hop distintos desde el vamos) -> 2 grupos, loader antes que el que
    lo consume. Coincide con la partición validada en 03-plan.md contra
    err1.ktr/err2.ktr."""
    result = compute_cut(_err1_like_ktr(), STEP_TYPE_ALIASES)
    groups = result["groups"]
    assert len(groups) == 2
    assert result["notifications"] == []

    loader_group = next(g for g in groups if "Cargar Dim Producto" in g)
    fact_group = next(g for g in groups if "Cargar Fact Venta" in g)
    assert set(loader_group) == {"Leer Staging Productos", "Cargar Dim Producto"}
    assert set(fact_group) == {"Leer Staging Ventas", "Lookup Dim Producto", "Cargar Fact Venta"}
    assert groups.index(loader_group) < groups.index(fact_group)  # loader antes que su lector


def test_compute_cut_no_trigger_single_ktr():
    """ETL simple sin W+R ni doble-escritor cruzado -> 1 solo grupo (D6-bis:
    sin señal estructural, no se parte)."""
    ktr_data = {
        "steps": [
            {"name": "Leer", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Cargar", "type": "TableOutput", "config": {"table": "stg_x", "connection": "c"}},
        ],
        "hops": [{"from": "Leer", "to": "Cargar", "enabled": True}],
    }
    result = compute_cut(ktr_data, STEP_TYPE_ALIASES)
    assert len(result["groups"]) == 1
    assert result["notifications"] == []


def _self_lookup_ktr_data() -> dict:
    return {
        "steps": [
            {"name": "Leer Staging", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Existe?", "type": "DBLookup",
             "config": {"table": "dim_pais", "connection": "conn_dwh",
                        "keys": [{"stream_field": "pais", "lookup_field": "pais"}],
                        "return_fields": [{"name": "sk_pais", "rename": "sk_pais"}]}},
            {"name": "Filtrar Nuevos", "type": "FilterRows", "config": {"field": "sk_pais", "operator": "IS NULL"}},
            {"name": "Insertar Dim Pais", "type": "TableOutput",
             "config": {"table": "dim_pais", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Leer Staging", "to": "Existe?", "enabled": True},
            {"from": "Existe?", "to": "Filtrar Nuevos", "enabled": True},
            {"from": "Filtrar Nuevos", "to": "Insertar Dim Pais", "enabled": True},
        ],
    }


def test_compute_cut_self_lookup_now_splits_via_materialization():
    """D48: 'Existe?' es ancestro directo de 'Insertar Dim Pais' (único
    writer) — patrón evidenciado en el corpus (err1.ktr/err2.ktr), el
    componente se parte: 'Insertar Dim Pais' pasa a un grupo posterior, el
    resto (incluido 'Existe?') queda en uno anterior, con Finding info (no
    error) señalando la materialización. Tercera inversión de este caso:
    D16 (excepción por camino dirigido, no partía) -> D45 punto 4 (excepción
    eliminada, siempre reportaba error, nunca partía) -> D48 (patrón
    reconocido, parte con materialización)."""
    result = compute_cut(_self_lookup_ktr_data(), STEP_TYPE_ALIASES)
    assert len(result["groups"]) == 2
    assert result["materialize_hops"] == [("Filtrar Nuevos", "Insertar Dim Pais")]
    errors = [f for f in result["notifications"] if f.severity == "error"]
    assert errors == []
    info = [f for f in result["notifications"] if f.severity == "info"]
    assert any("dim_pais" in f.message for f in info)

    before_group = next(g for g in result["groups"] if "Existe?" in g)
    after_group = next(g for g in result["groups"] if "Insertar Dim Pais" in g)
    assert before_group == ["Leer Staging", "Existe?", "Filtrar Nuevos"]
    assert after_group == ["Insertar Dim Pais"]
    assert result["groups"].index(before_group) < result["groups"].index(after_group)


def test_compute_cut_same_component_two_writers_still_reports_race():
    """D48 solo cubre un único writer — C1-bis (dos escritores) dentro del
    mismo componente sigue sin forma segura de decidir orden, se mantiene el
    comportamiento de D45 punto 4 (siempre notifica, nunca parte)."""
    ktr_data = {
        "steps": [
            {"name": "Leer Staging", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Insertar Dim Pais A", "type": "TableOutput",
             "config": {"table": "dim_pais", "connection": "conn_dwh"}},
            {"name": "Insertar Dim Pais B", "type": "TableOutput",
             "config": {"table": "dim_pais", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Leer Staging", "to": "Insertar Dim Pais A", "enabled": True},
            {"from": "Insertar Dim Pais A", "to": "Insertar Dim Pais B", "enabled": True},
        ],
    }
    result = compute_cut(ktr_data, STEP_TYPE_ALIASES)
    assert len(result["groups"]) == 1
    assert result["materialize_hops"] == []
    errors = [f for f in result["notifications"] if f.severity == "error"]
    assert len(errors) == 1
    assert "dim_pais" in errors[0].message


def test_compute_cut_same_component_reader_not_ancestor_still_reports_race():
    """D48 exige que TODOS los readers sean ancestros del writer — acá
    'Lee Otra Cosa' lee dim_pais pero no tiene camino hacia el writer, orden
    real ambiguo, se mantiene 'revisar a mano'."""
    ktr_data = {
        "steps": [
            {"name": "Leer Staging", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Insertar Dim Pais", "type": "TableOutput",
             "config": {"table": "dim_pais", "connection": "conn_dwh"}},
            {"name": "Lee Otra Cosa", "type": "DBLookup",
             "config": {"table": "dim_pais", "connection": "conn_dwh",
                        "keys": [{"stream_field": "pais", "lookup_field": "pais"}],
                        "return_fields": [{"name": "sk_pais", "rename": "sk_pais"}]}},
        ],
        "hops": [
            {"from": "Leer Staging", "to": "Insertar Dim Pais", "enabled": True},
            {"from": "Insertar Dim Pais", "to": "Lee Otra Cosa", "enabled": True},
        ],
    }
    result = compute_cut(ktr_data, STEP_TYPE_ALIASES)
    assert len(result["groups"]) == 1
    assert result["materialize_hops"] == []
    errors = [f for f in result["notifications"] if f.severity == "error"]
    assert len(errors) == 1


def test_compute_cut_rw_only_loader_does_not_trigger():
    """D45 punto 3: un step RW que es su propio único lector/escritor (loader
    de dimensión normal, update=Y) no dispara C1 por serlo — la carrera es
    entre steps DISTINTOS, no dentro del mismo step."""
    ktr_data = {
        "steps": [
            {"name": "Leer Staging", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Cargar Dim Pais", "type": "DimensionLookup",
             "config": {"table": "dim_pais", "connection": "conn_dwh", "returnfield": "sk_pais",
                        "keys": [{"stream_field": "pais", "table_field": "pais"}]}},
        ],
        "hops": [{"from": "Leer Staging", "to": "Cargar Dim Pais", "enabled": True}],
    }
    result = compute_cut(ktr_data, STEP_TYPE_ALIASES)
    assert len(result["groups"]) == 1
    assert result["notifications"] == []


def test_connected_components_ignores_disabled_hops():
    """D45 punto 4: un hop enabled=False no transporta filas — no conecta sus
    extremos. Antes de D45 solo `_reaches` (borrado) respetaba `enabled`;
    `_connected_components` lo ignoraba, así que 'Leer B' y 'Lookup A
    Disabled' habrían quedado unidos por ese hop pese a estar deshabilitado.
    Con D45, 'Leer B' queda aislado (ningún hop habilitado lo conecta) — su
    propio componente, sin tabla-disparadora -> untouched, grupo aparte."""
    ktr_data = {
        "steps": [
            {"name": "Leer A", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Cargar A", "type": "DimensionLookup",
             "config": {"table": "dim_a", "connection": "conn_dwh", "returnfield": "sk_a",
                        "keys": [{"stream_field": "a", "table_field": "a"}]}},
            {"name": "Leer B", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Lookup A Disabled", "type": "DimensionLookup",
             "config": {"table": "dim_a", "connection": "conn_dwh", "returnfield": "sk_a", "update": "N",
                        "keys": [{"stream_field": "a", "table_field": "a"}]}},
        ],
        "hops": [
            {"from": "Leer A", "to": "Cargar A", "enabled": True},
            {"from": "Leer B", "to": "Lookup A Disabled", "enabled": False},
        ],
    }
    result = compute_cut(ktr_data, STEP_TYPE_ALIASES)
    # dim_a: writer "Cargar A" y reader "Lookup A Disabled" -> C1 dispara.
    # Sin el hop deshabilitado uniéndolos, "Leer B" es su propio componente
    # sin tabla-disparadora -> 3 grupos (untouched [Leer B] + 2 disparados),
    # sin Finding de mismo-componente (los disparadores ya cayeron distintos).
    groups = result["groups"]
    assert len(groups) == 3
    assert [f for f in result["notifications"] if f.severity == "error"] == []
    assert {"Leer B"} in (set(g) for g in groups)
    loader_group = next(g for g in groups if "Cargar A" in g)
    lookup_group = next(g for g in groups if "Lookup A Disabled" in g)
    assert groups.index(loader_group) < groups.index(lookup_group)


def test_compute_cut_untouched_comps_inventory_only_when_real_cut():
    """D45 punto 7: rama sin ninguna tabla-disparadora (independiente de las
    tablas que sí disparan C1) genera Finding info SOLO cuando hay corte real
    — sin corte, D6-bis ya no parte nada y no hay 'quedó junto' que explicar."""
    triggering = _err1_like_ktr()
    untouched_steps = [
        {"name": "Leer Otro", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
        {"name": "Cargar Otro", "type": "TableOutput", "config": {"table": "stg_otro", "connection": "c"}},
    ]
    ktr_data = {
        "steps": [*triggering["steps"], *untouched_steps],
        "hops": [*triggering["hops"], {"from": "Leer Otro", "to": "Cargar Otro", "enabled": True}],
    }
    result = compute_cut(ktr_data, STEP_TYPE_ALIASES)
    assert len(result["groups"]) == 3  # untouched + 2 grupos disparados

    info_findings = [f for f in result["notifications"] if f.severity == "info"]
    assert len(info_findings) == 1
    assert "Leer Otro" in info_findings[0].message
    assert "Cargar Otro" in info_findings[0].message

    # Caso control: sin ningún trigger (test_compute_cut_no_trigger_single_ktr
    # ya lo cubre con notifications == []), no hay info que emitir.


def test_split_ktr_by_cut_cross_group_hop_reports_error():
    """D45 punto 5: un hop habilitado cuyo destino queda en OTRO grupo del
    corte (acá, un hop hacia un step inexistente — el único caso alcanzable
    con el algoritmo actual, ver nota en fragmentation.py) se reportaba
    perdido en silencio; ahora es Finding severity='error'."""
    ktr_data = _err1_like_ktr()
    ktr_data["hops"].append({"from": "Cargar Dim Producto", "to": "Step Inexistente", "enabled": True})

    sub_dicts, notifications = split_ktr_by_cut(ktr_data, STEP_TYPE_ALIASES)
    assert len(sub_dicts) == 2
    errors = [f for f in notifications if f.severity == "error"]
    assert any("Step Inexistente" in f.message for f in errors)


def test_split_ktr_by_cut_materializes_self_lookup_via_staging_table():
    """D48 end-to-end: split_ktr_by_cut, no solo compute_cut — el hop
    'Filtrar Nuevos' -> 'Insertar Dim Pais' queda cortado por el split y se
    materializa como TableOutput/TableInput contra una tabla de staging
    efímera, en vez de perderse o reportarse como error."""
    sub_dicts, notifications = split_ktr_by_cut(_self_lookup_ktr_data(), STEP_TYPE_ALIASES)
    assert len(sub_dicts) == 2

    errors = [f for f in notifications if f.severity == "error"]
    assert errors == []
    info_messages = " ".join(f.message for f in notifications if f.severity == "info")
    assert "etl_corte_1" in info_messages

    before, after = sub_dicts
    before_names = {s["name"] for s in before["steps"]}
    after_names = {s["name"] for s in after["steps"]}
    assert before_names == {"Leer Staging", "Existe?", "Filtrar Nuevos", "Escribir etl_corte_1"}
    assert after_names == {"Leer etl_corte_1", "Insertar Dim Pais"}

    output_step = next(s for s in before["steps"] if s["name"] == "Escribir etl_corte_1")
    assert output_step["type"] == "TableOutput"
    assert output_step["config"]["table"] == "etl_corte_1"
    assert output_step["config"]["connection"] == "conn_staging"
    assert output_step["config"]["truncate"] is True
    assert {"from": "Filtrar Nuevos", "to": "Escribir etl_corte_1", "enabled": True} in before["hops"]

    input_step = next(s for s in after["steps"] if s["name"] == "Leer etl_corte_1")
    assert input_step["type"] == "TableInput"
    assert input_step["config"]["sql"] == "SELECT * FROM etl_corte_1"
    assert input_step["config"]["connection"] == "conn_staging"
    assert {"from": "Leer etl_corte_1", "to": "Insertar Dim Pais", "enabled": True} in after["hops"]

    # La tabla efímera no matchea prefijo de staging/dwh a propósito (evita
    # falso positivo en guard_staging_layer, Fase 2-ter) — ver docstring de
    # _materialize_cut_hop.
    from app.domain.table_layer import infer_table_layer
    assert infer_table_layer("etl_corte_1") is None


def test_enforce_dimension_step_policy_then_compute_cut_splits_scd1_case_set_a():
    """Regresión de D7/D44/D51 (docs/refactor/03c-investigacion-vocabulario-
    dimension-kettle.md): caso Set A real — antes de D44, una dimensión
    scd_type=1 (sin historial) derivaba CombinationLookup como loader
    (siempre RW, inmune a C1 con un solo writer) y el lookup de FK del hecho
    era TableInput+StreamLookup, invisible a la matriz R/W — el corte NUNCA
    disparaba pese a la carrera real de lectura/escritura sobre la
    dimensión. Con el vocabulario uniforme (D44: DimensionLookup para todo
    scd_type) las dos ramas quedan visibles, y C1 dispara: groups == 2."""
    from app.services.ktr_builder.dimension_step_policy import enforce_dimension_step_policy

    ktr_data = {
        "steps": [
            {"name": "Leer Staging Categorias", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Cargar Dim Categoria", "type": "CombinationLookup",
             "config": {"table": "dim_categoria", "connection": "conn_dwh", "return_field": "sk_categoria",
                        "keys": [{"stream": "categoria_id", "lookup": "id_categoria_origen"}]}},
            {"name": "Leer Staging Productos", "type": "TableInput", "config": {"connection": "c", "sql": "SELECT 1"}},
            {"name": "Lookup Dim Categoria", "type": "CombinationLookup",
             "config": {"table": "dim_categoria", "connection": "conn_dwh", "return_field": "sk_categoria",
                        "keys": [{"stream": "categoria_id", "lookup": "id_categoria_origen"}]}},
            {"name": "Cargar Fact Producto", "type": "InsertUpdate",
             "config": {"table": "fact_producto", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Leer Staging Categorias", "to": "Cargar Dim Categoria", "enabled": True},
            {"from": "Leer Staging Productos", "to": "Lookup Dim Categoria", "enabled": True},
            {"from": "Lookup Dim Categoria", "to": "Cargar Fact Producto", "enabled": True},
        ],
    }

    class _FakeDimContract:
        table = "dim_categoria"
        scd_type = 1
        technical_key = "sk_categoria"
        version_field = "version"
        date_from = "fecha_inicio"
        date_to = "fecha_fin"
        attributes_scd1: list[str] = []
        attributes_scd2: list[str] = []

    policy_results = enforce_dimension_step_policy(ktr_data, [_FakeDimContract()], STEP_TYPE_ALIASES, [])
    assert any(r["tipo"] == "warning" for r in policy_results)  # loader Y lookup, ambos reparados

    loader = next(s for s in ktr_data["steps"] if s["name"] == "Cargar Dim Categoria")
    lookup = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Categoria")
    assert loader["type"] == "DimensionLookup" and loader["config"]["update"] == "Y"
    assert lookup["type"] == "DimensionLookup" and lookup["config"]["update"] == "N"

    result = compute_cut(ktr_data, STEP_TYPE_ALIASES)
    assert len(result["groups"]) == 2


# ─── validate_stage_contract (D45 punto 6, S-13) ────────────────────────────

def test_validate_stage_contract_single_fragment_is_noop():
    assert validate_stage_contract([_err1_like_ktr()], STEP_TYPE_ALIASES) == []


def test_validate_stage_contract_writer_before_reader_is_fine():
    """Orden normal (loader de dimensión primero, hecho después) -> sin findings."""
    loader = {
        "steps": [{"name": "Cargar Dim", "type": "DimensionLookup",
                   "config": {"table": "dim_x", "connection": "conn_dwh", "returnfield": "sk_x",
                              "keys": [{"stream_field": "x", "table_field": "x"}]}}],
        "hops": [],
    }
    fact = {
        "steps": [{"name": "Lookup Dim", "type": "DimensionLookup",
                   "config": {"table": "dim_x", "connection": "conn_dwh", "returnfield": "sk_x",
                              "update": "N",
                              "keys": [{"stream_field": "x", "table_field": "x"}]}}],
        "hops": [],
    }
    assert validate_stage_contract([loader, fact], STEP_TYPE_ALIASES) == []


def test_validate_stage_contract_reader_before_writer_is_error():
    """S-13: el fragmento 1 (índice 0, primero en el orden del .kjb) lee
    dim_x, pero es el fragmento 2 (índice 1, posterior) el que la escribe —
    el .kjb ejecutaría la lectura antes de que la fila exista."""
    reader_first = {
        "steps": [{"name": "Lookup Dim", "type": "DimensionLookup",
                   "config": {"table": "dim_x", "connection": "conn_dwh", "returnfield": "sk_x",
                              "update": "N",
                              "keys": [{"stream_field": "x", "table_field": "x"}]}}],
        "hops": [],
    }
    writer_second = {
        "steps": [{"name": "Cargar Dim", "type": "DimensionLookup",
                   "config": {"table": "dim_x", "connection": "conn_dwh", "returnfield": "sk_x",
                              "keys": [{"stream_field": "x", "table_field": "x"}]}}],
        "hops": [],
    }
    findings = validate_stage_contract([reader_first, writer_second], STEP_TYPE_ALIASES)
    assert len(findings) == 1
    assert findings[0].severity == "error"
    assert "dim_x" in findings[0].message
    assert "fragmento 1" in findings[0].message and "fragmento 2" in findings[0].message
