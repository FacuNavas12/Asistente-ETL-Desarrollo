"""
Unit tests — Fase 2-bis, mitigaciones 1 y 2
(docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md:168-176).

Mitigación 1 (_scd_consequence_findings): un finding por dimensión con la
consecuencia concreta del scd_type elegido — convierte una decisión invisible
en revisable, sin lo cual la Fase 2 (D44) cambia un artefacto visiblemente
roto por uno impecable y silenciosamente equivocado (H44).

Mitigación 2 (_monetary_scd2_guard): una columna de importe/monto no puede
versionarse como atributo de dimensión (B-7) — reusa MONEY_FIELD_HINTS de
error_catalog_checks.py, aplicada al contrato antes de emitir.
"""
from __future__ import annotations

from app.schemas.etl_schemas import DimContract
from app.services.etl_generator import _monetary_scd2_guard, _scd_consequence_findings
from app.services.ktr_builder.validators.base import PRE_EMIT_ERROR_PREFIX


def _contract(
    table: str, scd_type: int, *,
    attributes_scd1: list[str] | None = None,
    attributes_scd2: list[str] | None = None,
) -> DimContract:
    return DimContract(
        table=table, scd_type=scd_type, technical_key="sk_x",
        version_field="version", date_from="fecha_inicio", date_to="fecha_fin",
        natural_keys=["id_x"], unknown_key_value=0,
        attributes_scd1=attributes_scd1 or [],
        attributes_scd2=attributes_scd2 or [],
    )


# ─── _scd_consequence_findings ────────────────────────────────────────────

def test_scd2_finding_names_table_and_attributes():
    contracts = [_contract("dim_producto", 2, attributes_scd2=["nombre", "categoria"])]
    findings = _scd_consequence_findings(contracts)
    assert len(findings) == 1
    assert "dim_producto" in findings[0]
    assert "SCD2" in findings[0]
    assert "nombre, categoria" in findings[0]


def test_scd1_finding_names_table_and_attributes():
    contracts = [_contract("dim_cliente", 1, attributes_scd1=["telefono", "email"])]
    findings = _scd_consequence_findings(contracts)
    assert len(findings) == 1
    assert "dim_cliente" in findings[0]
    assert "SCD1" in findings[0]
    assert "telefono, email" in findings[0]


def test_scd_zero_produces_no_consequence_finding():
    contracts = [_contract("dim_fecha", 0)]
    assert _scd_consequence_findings(contracts) == []


def test_scd2_with_no_attributes_declared_still_reports():
    contracts = [_contract("dim_x", 2, attributes_scd2=[])]
    findings = _scd_consequence_findings(contracts)
    assert len(findings) == 1
    assert "ninguno declarado" in findings[0]


def test_findings_are_never_error_prefixed():
    contracts = [
        _contract("dim_a", 1, attributes_scd1=["x"]),
        _contract("dim_b", 2, attributes_scd2=["y"]),
    ]
    findings = _scd_consequence_findings(contracts)
    assert len(findings) == 2
    assert all(not f.startswith(PRE_EMIT_ERROR_PREFIX) for f in findings)


def test_empty_dim_contracts_short_circuits():
    assert _scd_consequence_findings([]) == []


# ─── _monetary_scd2_guard ──────────────────────────────────────────────────

def test_monetary_attribute_in_scd2_is_error():
    contracts = [_contract("dim_producto", 2, attributes_scd2=["nombre", "precio_lista"])]
    findings = _monetary_scd2_guard(contracts)
    assert len(findings) == 1
    assert findings[0].startswith(PRE_EMIT_ERROR_PREFIX)
    assert "dim_producto" in findings[0]
    assert "precio_lista" in findings[0]


def test_non_monetary_scd2_attributes_pass_silently():
    contracts = [_contract("dim_producto", 2, attributes_scd2=["nombre", "categoria"])]
    assert _monetary_scd2_guard(contracts) == []


def test_monetary_attribute_in_scd1_is_not_checked():
    """attributes_scd1 se sobrescribe, no se versiona -- B-7 es específico de
    versionar un monto, no de tenerlo como atributo de dimensión en general."""
    contracts = [_contract("dim_producto", 1, attributes_scd1=["precio_lista"])]
    assert _monetary_scd2_guard(contracts) == []


def test_multiple_monetary_hits_listed_together():
    contracts = [_contract("dim_x", 2, attributes_scd2=["monto_total", "descuento", "nombre"])]
    findings = _monetary_scd2_guard(contracts)
    assert len(findings) == 1
    assert "monto_total" in findings[0]
    assert "descuento" in findings[0]
    assert "nombre" not in findings[0].split("attributes_scd2")[1].split(")")[0]


def test_empty_dim_contracts_short_circuits_guard():
    assert _monetary_scd2_guard([]) == []
