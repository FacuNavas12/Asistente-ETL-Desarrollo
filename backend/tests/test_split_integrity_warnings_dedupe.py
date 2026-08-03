"""
Unit test — E-20 (docs/refactor/errores.md), dedupe en _split_integrity_warnings.

PRE_EMIT_PASSES corre dos veces sobre el mismo step: una vez en
_recover_table_keys() (etl_generator.py) sobre ktr_data completo antes de
compute_cut(), otra vez dentro de build_ktr() (build.py:187) sobre el
sub-dict ya partido. Un finding insensible al corte (ej.
check_dimension_lookup_fields) llega al merge de warnings dos veces, byte
a byte — confirmado con el corpus real de E-01 (D64, 02-decisiones.md):
6 findings de vocabulario cruzado aparecían 12 veces. _split_integrity_warnings
es el punto donde las listas de ambas pasadas convergen (líneas 1099 y 1237),
así que ahí se descarta el duplicado exacto.
"""
from __future__ import annotations

from app.services.etl_generator import _split_integrity_warnings
from app.services.ktr_builder.validators.base import PRE_EMIT_ERROR_PREFIX


def test_exact_duplicate_pre_emit_error_collapses_to_one():
    msg = f"{PRE_EMIT_ERROR_PREFIX}Step 'Cargar dim_producto': campo 'stock' fuera de vocabulario"
    plain, integridad = _split_integrity_warnings([msg, msg])
    assert plain == []
    assert len(integridad) == 1
    assert integridad[0].mensaje == msg[len(PRE_EMIT_ERROR_PREFIX):]


def test_two_different_pre_emit_errors_both_survive():
    msg_a = f"{PRE_EMIT_ERROR_PREFIX}campo 'stock' fuera de vocabulario"
    msg_b = f"{PRE_EMIT_ERROR_PREFIX}campo 'fk_categoria' fuera de vocabulario"
    plain, integridad = _split_integrity_warnings([msg_a, msg_b])
    assert plain == []
    assert {v.mensaje for v in integridad} == {
        msg_a[len(PRE_EMIT_ERROR_PREFIX):], msg_b[len(PRE_EMIT_ERROR_PREFIX):],
    }


def test_duplicate_cosmetic_warning_also_collapses():
    plain, integridad = _split_integrity_warnings(["mismo warning cosmético", "mismo warning cosmético"])
    assert plain == ["mismo warning cosmético"]
    assert integridad == []


def test_six_findings_duplicated_to_twelve_collapse_to_six():
    findings = [
        f"{PRE_EMIT_ERROR_PREFIX}atributo '{attr}': type='Update' fuera de vocabulario"
        for attr in (
            "nombre_producto", "fk_categoria", "precio_lista",
            "precio_unitario", "stock", "bk_producto_calculado",
        )
    ]
    doubled = [*findings, *findings]
    assert len(doubled) == 12
    _, integridad = _split_integrity_warnings(doubled)
    assert len(integridad) == 6
