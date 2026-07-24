"""F3 — algoritmo de corte puro (build_rw_matrix + compute_cut), validado
contra la forma de err1.ktr/err2.ktr (H21/D7). Solo el algoritmo — el wiring
a etl_generator.py/_build_job_plan/stitch_lineage queda pendiente (ver nota
de estado al pie de fragmentation.py)."""
from __future__ import annotations

from app.services.ktr_builder.fragmentation import build_rw_matrix, compute_cut
from app.services.ktr_builder.registry import STEP_TYPE_ALIASES


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
    matrix = build_rw_matrix(_err1_like_ktr(), STEP_TYPE_ALIASES)
    assert matrix["dim_producto"]["Cargar Dim Producto"] == "RW"
    assert matrix["dim_producto"]["Lookup Dim Producto"] == "R"  # update=N (D16)
    assert matrix["fact_venta"]["Cargar Fact Venta"] == "W"
    assert "dim_producto" not in {k for k in matrix if "Leer Staging" in matrix.get(k, {})}


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


def test_compute_cut_self_lookup_insert_new_only_exception_does_not_split():
    """Idioma 'existe? -> filtra -> inserta' (self-lookup) dentro del MISMO
    componente: lectura con camino dirigido hacia la escritura -> no dispara
    corte (excepción del algoritmo, ver 03-plan.md)."""
    ktr_data = {
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
    result = compute_cut(ktr_data, STEP_TYPE_ALIASES)
    assert len(result["groups"]) == 1
    assert result["notifications"] == []
