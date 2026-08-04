"""
error_catalog_checks.py no tenia ningun test dedicado (auditado 2026-07-25) --
este archivo cubre el cambio puntual hecho en esa sesion: MONEY_FIELD_HINTS
extendido (impuesto/iva/descuento/saldo/comision/recargo/tipo_cambio/arancel/
cuota) para que v11 alcance las mismas palabras que la regla de prompt B17
(docs/refactor/01-hallazgos.md H9, system_etl.txt) promete cubrir -- sin este
alcance, la regla de prompt seria inverificable para esos nombres de campo.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from app.services.ktr_builder.error_catalog_checks import (
    v4_select_values_sin_entradas,
    v5_dimension_lookup_columnas_tecnicas,
    v6_insert_update_mapeos,
    v7_fact_table_output_sin_clave,
    v8_truncate_sin_transaccional,
    v11_monetario_sin_bignumber,
    v13_lookup_key_incompleta,
)

GOLDEN_DIR = Path(__file__).parent.parent.parent / "fixtures" / "golden_run_base_01"

# Columnas reales que los dos .ktr referencian para dim_producto/dim_categoria/
# fact_inventario (V5/V6) -- no hay DDL completo adjunto a este golden run,
# así que esta lista es deliberadamente el subconjunto que aparece en los
# steps DimensionLookup/InsertUpdate de los fixtures, no el DDL entero de
# Base_01. Alcanza para el gate S-1: confirmar que V5/V6 no objetan columnas
# que el propio artefacto ya declara como reales.
GOLDEN_DDL_COLUMNS = {
    "dim_producto": {
        "id_producto_origen", "fecha_inicio", "fecha_fin",
        "nombre_producto", "precio_lista", "precio_unitario",
        "sk_producto", "version",
    },
    "dim_categoria": {
        "id_categoria_origen", "fecha_inicio", "fecha_fin",
        "sk_categoria", "version",
    },
    "fact_inventario": {
        "id_inventario_origen", "fk_categoria", "fk_producto",
        "stock", "precio_unitario", "valor_inventario",
    },
}


def _golden_roots() -> list[ET.Element]:
    return [
        ET.parse(GOLDEN_DIR / "ktr_1_origen_a_staging.ktr").getroot(),
        ET.parse(GOLDEN_DIR / "ktr_2_stg_a_dwh.ktr").getroot(),
    ]


@pytest.mark.parametrize("root", _golden_roots(), ids=["ktr_1_origen_a_staging", "ktr_2_stg_a_dwh"])
def test_golden_run_base_01_zero_findings(root):
    """S-1/S-3 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md):
    los .ktr de una corrida real contra Base_01, verificada con Fix 1 (condición
    AND completa en el FilterRows de saneamiento) y Fix 2 (reglas de negocio
    solo en Staging→DWH) ya aplicados (fixes_flujo_completo_stg_dwh.md), tienen
    que producir CERO findings de V4-V13 -- si alguno dispara acá, el checker
    tiene un falso positivo contra un artefacto que ejecutó limpio, y no se le
    puede cablear severidad "error" hasta corregirlo."""
    findings = [
        *v4_select_values_sin_entradas(root),
        *v5_dimension_lookup_columnas_tecnicas(root, GOLDEN_DDL_COLUMNS),
        *v6_insert_update_mapeos(root, GOLDEN_DDL_COLUMNS),
        *v7_fact_table_output_sin_clave(root),
        *v8_truncate_sin_transaccional(root),
        *v11_monetario_sin_bignumber(root),
        *v13_lookup_key_incompleta(root),
    ]
    assert findings == []


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
