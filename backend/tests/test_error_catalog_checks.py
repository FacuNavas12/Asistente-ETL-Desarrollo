"""
error_catalog_checks.py no tenia ningun test dedicado (auditado 2026-07-25) --
este archivo cubre el cambio puntual hecho en esa sesion: MONEY_FIELD_HINTS
extendido (impuesto/iva/descuento/saldo/comision/recargo/tipo_cambio/arancel/
cuota) para que v11 alcance las mismas palabras que la regla de prompt B17
(docs/refactor/01-hallazgos.md H9, system_etl.txt) promete cubrir -- sin este
alcance, la regla de prompt seria inverificable para esos nombres de campo.
"""
from xml.etree import ElementTree as ET

import pytest

from app.services.ktr_builder.error_catalog_checks import v11_monetario_sin_bignumber


def _calculator_xml(field_name: str, value_type: str) -> str:
    return (
        "<transformation><step><name>Calc</name><type>Calculator</type>"
        f"<calculation><field_name>{field_name}</field_name>"
        f"<value_type>{value_type}</value_type></calculation>"
        "</step></transformation>"
    )


@pytest.mark.parametrize("field_name", [
    "monto_iva", "saldo_cliente", "tipo_cambio_venta", "descuento_total",
    "comision_venta", "recargo_mora", "arancel_importacion", "cuota_mensual", "importe_impuesto",
])
def test_v11_flags_extended_money_hints_when_number(field_name):
    root = ET.fromstring(_calculator_xml(field_name, "Number"))
    findings = v11_monetario_sin_bignumber(root)
    assert len(findings) == 1
    assert findings[0].rule == "V11"
    assert findings[0].error == "E14"


@pytest.mark.parametrize("field_name", ["monto_iva", "saldo_cliente", "tipo_cambio_venta"])
def test_v11_accepts_bignumber_for_extended_money_hints(field_name):
    root = ET.fromstring(_calculator_xml(field_name, "BigNumber"))
    assert v11_monetario_sin_bignumber(root) == []


def test_v11_ignores_non_money_field_typed_number():
    root = ET.fromstring(_calculator_xml("anio_venta", "Number"))
    assert v11_monetario_sin_bignumber(root) == []
