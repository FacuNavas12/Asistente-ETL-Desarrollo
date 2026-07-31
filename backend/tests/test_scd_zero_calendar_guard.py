"""
Unit tests — R-K7 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md,
D51): _scd_zero_calendar_guard. El colapso scd_type=0 -> 1 (D44 derive_dimension_
loader_step) solo es seguro cuando la dimensión es de calendario (el ETL nunca la
carga, K18) — este guard reporta severidad error para cualquier scd_type=0 que
NO matchee is_calendar_dimension(), sin abortar el build (D15).
"""
from __future__ import annotations

from app.schemas.etl_schemas import DimContract
from app.services.etl_generator import _scd_zero_calendar_guard
from app.services.ktr_builder.validators.base import PRE_EMIT_ERROR_PREFIX

_DWH_DDL = """
CREATE TABLE dim_fecha (
  sk_fecha SERIAL PRIMARY KEY,
  fecha DATE NOT NULL,
  anio INTEGER
);
CREATE TABLE dim_producto (
  sk_producto SERIAL PRIMARY KEY,
  id_producto INTEGER NOT NULL,
  nombre VARCHAR(255)
);
"""


def _contract(table: str, scd_type: int, natural_keys: list[str]) -> DimContract:
    return DimContract(
        table=table, scd_type=scd_type, technical_key="sk_x",
        version_field="version", date_from="fecha_inicio", date_to="fecha_fin",
        natural_keys=natural_keys, unknown_key_value=0,
    )


def test_calendar_dimension_scd_zero_passes_silently():
    contracts = [_contract("dim_fecha", 0, ["fecha"])]
    assert _scd_zero_calendar_guard(_DWH_DDL, contracts) == []


def test_non_calendar_dimension_scd_zero_is_error():
    contracts = [_contract("dim_producto", 0, ["id_producto"])]
    findings = _scd_zero_calendar_guard(_DWH_DDL, contracts)
    assert len(findings) == 1
    assert findings[0].startswith(PRE_EMIT_ERROR_PREFIX)
    assert "dim_producto" in findings[0]
    assert "scd_type=1" in findings[0]


def test_scd_type_1_and_2_are_never_checked():
    contracts = [_contract("dim_producto", 1, ["id_producto"]), _contract("dim_fecha", 2, ["fecha"])]
    assert _scd_zero_calendar_guard(_DWH_DDL, contracts) == []


def test_empty_ddl_is_best_effort_no_findings():
    contracts = [_contract("dim_producto", 0, ["id_producto"])]
    assert _scd_zero_calendar_guard("", contracts) == []


def test_table_missing_from_ddl_is_best_effort_no_findings():
    contracts = [_contract("dim_inexistente", 0, ["id_x"])]
    assert _scd_zero_calendar_guard(_DWH_DDL, contracts) == []


def test_invalid_ddl_does_not_raise():
    contracts = [_contract("dim_producto", 0, ["id_producto"])]
    assert _scd_zero_calendar_guard("no es SQL válido {{{", contracts) == []


def test_no_scd_zero_contracts_short_circuits():
    contracts = [_contract("dim_producto", 1, ["id_producto"])]
    assert _scd_zero_calendar_guard(_DWH_DDL, contracts) == []
