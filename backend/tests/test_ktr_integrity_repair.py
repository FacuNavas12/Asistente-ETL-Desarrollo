"""repair_integrity_gaps: segunda pasada de reparación para Constant con config
vacío que un TableOutput/InsertUpdate/DimensionLookup aguas abajo necesita.
Cubre:
  1. {"fields": []} se trata igual que {} (missing_required_keys usa falsy,
     no solo ausencia de clave) — el caso que motivó el fix de contracts.py.
  2. El fallback determinístico es branch-aware: con dos ramas independientes
     (categorías / productos), cada Constant recibe el stg_origen de SU
     propia rama, no el de la otra.
  3. El mensaje de integridad, una vez el contrato de Constant declara
     required_keys, atribuye el hueco al Constant culpable (no al TableInput
     más cercano) — reconcilia el ejemplo del prompt con el comportamiento real.
"""
from __future__ import annotations

import asyncio

from app.services.ktr_builder import build_ktr
from app.services.ktr_builder.contracts import missing_required_keys
from app.services.ktr_builder.fields_validate import validate_field_resolution
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES
from app.services.ktr_builder.repair import repair_integrity_gaps


def _run(coro):
    return asyncio.run(coro)


def _branch(entity: str, table: str) -> tuple[list[dict], list[dict]]:
    """Un TableInput -> Constant (vacío) -> TableOutput, aislado de cualquier
    otra rama (sin hops compartidos)."""
    steps = [
        {"name": f"Leer {entity}", "type": "TableInput",
         "config": {"sql": f"SELECT id, nombre FROM {table}"}},
        {"name": f"Agregar Constantes {entity}", "type": "Constant", "config": {"fields": []}},
        {"name": f"Cargar stg_{table}", "type": "TableOutput",
         "config": {"connection": "conn_staging", "table": f"stg_{table}", "fields": [
             {"stream_name": "id"}, {"stream_name": "nombre"},
             {"stream_name": "stg_origen"}, {"stream_name": "stg_estado"},
         ]}},
    ]
    hops = [
        {"from": f"Leer {entity}", "to": f"Agregar Constantes {entity}"},
        {"from": f"Agregar Constantes {entity}", "to": f"Cargar stg_{table}"},
    ]
    return steps, hops


def _two_branch_ktr() -> dict:
    steps_a, hops_a = _branch("Categorias", "categorias")
    steps_b, hops_b = _branch("Productos", "productos")
    return {
        "name": "Test", "description": "",
        "connections": [{"name": "conn_staging", "host": "h", "type": "postgresql", "database": "d", "port": 5432, "username": "u"}],
        "steps": [*steps_a, *steps_b],
        "hops": [*hops_a, *hops_b],
    }


def test_empty_fields_list_flagged_same_as_missing_key():
    assert missing_required_keys("Constant", {"fields": []}) == missing_required_keys("Constant", {})
    assert missing_required_keys("Constant", {"fields": [{"name": "x", "type": "String", "value": "y"}]}) == []


def test_integrity_error_attributes_gap_to_constant_not_table_input():
    ktr = _two_branch_ktr()
    errors = validate_field_resolution(ktr, STEP_TYPE_ALIASES)
    assert errors  # dos ramas rotas -> hay huecos
    for e in errors:
        assert "no se produce" in e
        assert "Agregar Constantes" in e  # atribuido al Constant culpable...
        assert "Leer Categorias" not in e and "Leer Productos" not in e  # ...no al TableInput más cercano


def test_deterministic_fallback_is_branch_aware():
    ktr = _two_branch_ktr()

    fixed, warnings = _run(repair_integrity_gaps(ktr, llm=None, context_text=""))

    assert len(warnings) == 4  # stg_origen + stg_estado, por cada una de las 2 ramas

    def _fields(step_name: str) -> dict[str, str]:
        step = next(s for s in fixed["steps"] if s["name"] == step_name)
        return {f["name"]: f["value"] for f in step["config"]["fields"]}

    cat_fields = _fields("Agregar Constantes Categorias")
    prod_fields = _fields("Agregar Constantes Productos")

    assert cat_fields["stg_origen"] == "categorias"
    assert prod_fields["stg_origen"] == "productos"
    assert cat_fields["stg_origen"] != prod_fields["stg_origen"]  # no cross-contamination
    assert cat_fields["stg_estado"] == "ACTIVO"
    assert prod_fields["stg_estado"] == "ACTIVO"

    # el .ktr ya no debe abortar por integridad de campos
    build_ktr(fixed)
