"""
Tests unitarios para app/services/lineage_builder.py.
Tres escenarios: caso feliz, hop roto, step aislado.
"""
import logging

import pytest

from app.services.lineage_builder import build_lineage


# ─── Fixtures ────────────────────────────────────────────────────────────────

KTR_HAPPY = {
    "name": "Test ETL",
    "steps": [
        {"name": "Leer Clientes", "type": "TableInput",  "config": {"sql": "SELECT * FROM clientes", "connection": "src"}},
        {"name": "Limpiar Nulos", "type": "SelectValues", "config": {"select": []}},
        {"name": "Escribir STG",  "type": "TableOutput",  "config": {"table": "STG_CLIENTES", "connection": "dwh"}},
    ],
    "hops": [
        {"from": "Leer Clientes", "to": "Limpiar Nulos"},
        {"from": "Limpiar Nulos", "to": "Escribir STG"},
    ],
}

KTR_BROKEN_HOP = {
    "name": "Hop roto",
    "steps": [
        {"name": "Entrada", "type": "TableInput",  "config": {"sql": "SELECT 1", "connection": "src"}},
        {"name": "Salida",  "type": "TableOutput", "config": {"table": "DIM_PRODUCTO", "connection": "dwh"}},
    ],
    "hops": [
        {"from": "Entrada",          "to": "Salida"},
        {"from": "STEP_INEXISTENTE", "to": "Salida"},
        {"from": "Entrada",          "to": "OTRO_INEXISTENTE"},
    ],
}

KTR_ISOLATED = {
    "name": "Step aislado",
    "steps": [
        {"name": "Solo", "type": "Dummy", "config": {}},
    ],
    "hops": [],
}

KTR_DWH_NAMING = {
    "name": "DWH naming",
    "steps": [
        {"name": "Src",    "type": "TableInput",  "config": {"sql": "SELECT * FROM ventas", "connection": "src"}},
        {"name": "Filter", "type": "FilterRows",  "config": {"field": "activo", "operator": "=", "value": "1"}},
        {"name": "DimOut", "type": "TableOutput", "config": {"table": "DIM_PRODUCTO", "connection": "dwh"}},
        {"name": "FactOut","type": "InsertUpdate","config": {"table": "FACT_VENTAS",  "connection": "dwh"}},
    ],
    "hops": [
        {"from": "Src",    "to": "Filter"},
        {"from": "Filter", "to": "DimOut"},
        {"from": "Filter", "to": "FactOut"},
    ],
}


# ─── Caso feliz ───────────────────────────────────────────────────────────────

def test_happy_path_node_count():
    lineage = build_lineage(KTR_HAPPY)
    assert len(lineage.nodes) == 3


def test_happy_path_edge_count():
    lineage = build_lineage(KTR_HAPPY)
    assert len(lineage.edges) == 2


def test_happy_path_layers():
    lineage = build_lineage(KTR_HAPPY)
    by_name = {n.step_name: n for n in lineage.nodes}

    assert by_name["Leer Clientes"].capa == "origen"
    assert by_name["Limpiar Nulos"].capa == "staging"
    # La tabla STG_CLIENTES tiene prefijo STG_ → staging, aunque out_deg==0
    assert by_name["Escribir STG"].capa == "staging"


def test_happy_path_tabla_extraction():
    lineage = build_lineage(KTR_HAPPY)
    by_name = {n.step_name: n for n in lineage.nodes}

    # TableInput extrae tabla del SQL via regex
    assert by_name["Leer Clientes"].tabla == "clientes"
    # TableOutput extrae del campo "table"
    assert by_name["Escribir STG"].tabla == "STG_CLIENTES"
    # SelectValues no tiene tabla
    assert by_name["Limpiar Nulos"].tabla is None


def test_happy_path_tipo_canonico():
    lineage = build_lineage(KTR_HAPPY)
    by_name = {n.step_name: n for n in lineage.nodes}
    assert by_name["Leer Clientes"].tipo_step == "TableInput"
    assert by_name["Limpiar Nulos"].tipo_step == "SelectValues"
    assert by_name["Escribir STG"].tipo_step == "TableOutput"


# ─── Hop roto ────────────────────────────────────────────────────────────────

def test_broken_hop_does_not_raise():
    lineage = build_lineage(KTR_BROKEN_HOP)
    assert lineage is not None


def test_broken_hop_skipped(caplog):
    with caplog.at_level(logging.WARNING, logger="app.services.lineage_builder"):
        lineage = build_lineage(KTR_BROKEN_HOP)

    warning_texts = caplog.text
    assert "STEP_INEXISTENTE" in warning_texts
    assert "OTRO_INEXISTENTE" in warning_texts


def test_broken_hop_valid_edge_kept():
    lineage = build_lineage(KTR_BROKEN_HOP)
    # Solo el hop válido (Entrada → Salida) debe quedar
    assert len(lineage.edges) == 1
    assert lineage.edges[0].from_step == "Entrada"
    assert lineage.edges[0].to_step == "Salida"


def test_broken_hop_nodes_intact():
    lineage = build_lineage(KTR_BROKEN_HOP)
    names = {n.step_name for n in lineage.nodes}
    assert names == {"Entrada", "Salida"}


# ─── Step aislado ─────────────────────────────────────────────────────────────

def test_isolated_step_has_node():
    lineage = build_lineage(KTR_ISOLATED)
    assert len(lineage.nodes) == 1


def test_isolated_step_no_edges():
    lineage = build_lineage(KTR_ISOLATED)
    assert len(lineage.edges) == 0


def test_isolated_step_is_origen():
    lineage = build_lineage(KTR_ISOLATED)
    # in_deg == 0 → "origen" por defecto
    assert lineage.nodes[0].capa == "origen"


# ─── Clasificación por nombre de tabla (DIM_ / FACT_) ────────────────────────

def test_dwh_naming_dim():
    lineage = build_lineage(KTR_DWH_NAMING)
    by_name = {n.step_name: n for n in lineage.nodes}
    assert by_name["DimOut"].capa == "dwh"


def test_dwh_naming_fact():
    lineage = build_lineage(KTR_DWH_NAMING)
    by_name = {n.step_name: n for n in lineage.nodes}
    assert by_name["FactOut"].capa == "dwh"


def test_dwh_naming_intermediate_is_staging():
    lineage = build_lineage(KTR_DWH_NAMING)
    by_name = {n.step_name: n for n in lineage.nodes}
    assert by_name["Filter"].capa == "staging"


# ─── KTR vacío ───────────────────────────────────────────────────────────────

def test_empty_ktr():
    lineage = build_lineage({})
    assert lineage.nodes == []
    assert lineage.edges == []
