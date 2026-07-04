"""
Tests del lint post-generación (app.services.ktr_xml_validator) y su wiring en
ktr_builder.build_ktr(). Cubre los dos defectos sistemáticos reportados:

  1. Conexión GENERIC sin CUSTOM_DRIVER_CLASS/CUSTOM_URL -> KtrXmlValidationError
     (y confirma que build_ktr() ahora los emite siempre, evitando el error).
  2. GetSystemInfo sin <fields> -> KtrXmlValidationError (y confirma que
     build_ktr() ahora agrega un field por defecto, evitando el error).

Más el chequeo genérico de hops huérfanos sobre el XML ya serializado.
"""
from __future__ import annotations

import pytest

from app.services.ktr_builder import build_ktr
from app.services.ktr_xml_validator import KtrXmlValidationError, validate_ktr_xml

_VALID_XML = """<?xml version="1.0" encoding="UTF-8"?>
<transformation>
  <connection>
    <name>conn_origen</name>
    <type>POSTGRESQL</type>
    <attributes/>
  </connection>
  <order>
    <hop><from>A</from><to>B</to><enabled>Y</enabled></hop>
  </order>
  <step><name>A</name><type>TableInput</type></step>
  <step><name>B</name><type>TableOutput</type></step>
</transformation>
"""


def test_valid_xml_passes():
    validate_ktr_xml(_VALID_XML)  # no debe levantar


def test_generic_connection_without_attributes_rejected():
    xml = _VALID_XML.replace(
        "<type>POSTGRESQL</type>",
        "<type>GENERIC</type>",
    )
    with pytest.raises(KtrXmlValidationError) as exc:
        validate_ktr_xml(xml)
    assert "CUSTOM_DRIVER_CLASS" in str(exc.value)
    assert "CUSTOM_URL" in str(exc.value)


def test_generic_connection_with_only_driver_still_rejected_missing_url():
    xml = _VALID_XML.replace(
        "<type>POSTGRESQL</type>",
        "<type>GENERIC</type>",
    ).replace(
        "<attributes/>",
        "<attributes><attribute><code>CUSTOM_DRIVER_CLASS</code>"
        "<attribute>org.postgresql.Driver</attribute></attribute></attributes>",
    )
    with pytest.raises(KtrXmlValidationError) as exc:
        validate_ktr_xml(xml)
    assert "CUSTOM_URL" in str(exc.value)
    assert "CUSTOM_DRIVER_CLASS" not in str(exc.value)


def test_generic_connection_with_both_attributes_passes():
    xml = _VALID_XML.replace(
        "<type>POSTGRESQL</type>",
        "<type>GENERIC</type>",
    ).replace(
        "<attributes/>",
        "<attributes>"
        "<attribute><code>CUSTOM_DRIVER_CLASS</code><attribute>org.postgresql.Driver</attribute></attribute>"
        "<attribute><code>CUSTOM_URL</code><attribute>jdbc:postgresql://${H}:${P}/${D}</attribute></attribute>"
        "</attributes>",
    )
    validate_ktr_xml(xml)  # no debe levantar


def test_get_system_info_without_fields_rejected():
    xml = _VALID_XML.replace(
        "<step><name>B</name><type>TableOutput</type></step>",
        "<step><name>B</name><type>GetSystemInfo</type><fields/></step>",
    )
    with pytest.raises(KtrXmlValidationError) as exc:
        validate_ktr_xml(xml)
    assert "GetSystemInfo" in str(exc.value)


def test_get_system_info_with_fields_passes():
    xml = _VALID_XML.replace(
        "<step><name>B</name><type>TableOutput</type></step>",
        "<step><name>B</name><type>GetSystemInfo</type>"
        "<fields><field><name>fecha_carga</name><type>system date (fixed)</type></field></fields></step>",
    )
    validate_ktr_xml(xml)  # no debe levantar


def test_hop_referencing_missing_step_rejected():
    xml = _VALID_XML.replace("<to>B</to>", "<to>NoExiste</to>")
    with pytest.raises(KtrXmlValidationError) as exc:
        validate_ktr_xml(xml)
    assert "NoExiste" in str(exc.value)


# ─── Integración con build_ktr() ──────────────────────────────────────────────

def _base_ktr_data(step_overrides=None):
    return {
        "name": "test_proc",
        "description": "",
        "connections": [
            {"name": "conn_dwh", "type": "GENERIC", "host": "PLACEHOLDER_HOST",
             "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"}
        ],
        "steps": [
            {"name": "Leer", "type": "TableInput", "config": {"connection": "conn_dwh", "sql": "SELECT 1"}},
            *(step_overrides or []),
            {"name": "Escribir", "type": "TableOutput", "config": {"connection": "conn_dwh", "table": "dim_x"}},
        ],
        "hops": [{"from": "Leer", "to": "Escribir", "enabled": True}],
    }


def test_build_ktr_generic_connection_without_real_data_gets_driver_attributes():
    xml, _, warnings = build_ktr(_base_ktr_data())
    assert "<code>CUSTOM_DRIVER_CLASS</code>" in xml
    assert "org.postgresql.Driver" in xml
    assert "<code>CUSTOM_URL</code>" in xml
    assert "jdbc:postgresql://" in xml


def test_build_ktr_get_system_info_without_fields_gets_default_field():
    data = _base_ktr_data([
        {"name": "Fecha Sistema", "type": "GetSystemInfo", "config": {}},
    ])
    data["hops"] = [
        {"from": "Leer", "to": "Fecha Sistema", "enabled": True},
        {"from": "Fecha Sistema", "to": "Escribir", "enabled": True},
    ]
    xml, _, warnings = build_ktr(data)
    assert "<type>system date (fixed)</type>" in xml
    assert "fecha_carga" in xml
