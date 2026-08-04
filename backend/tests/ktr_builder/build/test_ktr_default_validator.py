"""
Tests del validador post-generación (app.services.ktr_default_validator) y su
wiring en ktr_builder.build_ktr(). Cubre los tres casos del bug confirmado:

  1. Default de función (NOW()) en un Constant Timestamp -> se quita del step y
     de cualquier mapeo de TableOutput/InsertUpdate que lo referencie.
  2. Default literal ('ACTIVO') -> se conserva intacto, sin warnings.
  3. NOT NULL sin default -> se reporta si falta el mapeo de origen.

Todo con nombres de tabla/columna genéricos — nada atado a un esquema puntual.
"""
from __future__ import annotations

from app.services.ktr_builder import STEP_TYPE_ALIASES, build_ktr
from app.services.ktr_default_validator import (
    check_missing_required_fields,
    scrub_function_default_constants,
)


def _ktr_with_constant_and_output(constant_value: str, constant_type: str = "Timestamp"):
    return {
        "name": "Test_Transform",
        "connections": [{"name": "conn_staging", "host": "h", "port": 5432, "database": "d", "username": "u"}],
        "steps": [
            {
                "name": "K1", "type": "WriteToLog",
                "config": {"message": "Test_Transform"},
            },
            {
                "name": "Agregar Constantes", "type": "Constant",
                "config": {"fields": [
                    {"name": "stg_fecha_carga", "type": constant_type, "format": "yyyy-MM-dd HH:mm:ss", "value": constant_value},
                    {"name": "stg_estado", "type": "String", "format": "", "value": "ACTIVO"},
                ]},
            },
            {
                "name": "Cargar Staging", "type": "TableOutput",
                "config": {
                    "connection": "conn_staging", "table": "stg_ejemplo", "truncate": True,
                    "fields": [
                        {"stream_name": "stg_fecha_carga", "column_name": "fecha_carga"},
                        {"stream_name": "stg_estado", "column_name": "estado"},
                    ],
                },
            },
        ],
        "hops": [
            {"from": "K1", "to": "Agregar Constantes", "enabled": True},
            {"from": "Agregar Constantes", "to": "Cargar Staging", "enabled": True},
        ],
    }


class TestScrubFunctionDefaultConstants:
    def test_function_default_is_removed_from_constant(self):
        ktr = _ktr_with_constant_and_output("NOW()")
        warnings = scrub_function_default_constants(ktr, STEP_TYPE_ALIASES)

        assert len(warnings) >= 1
        constant_step = next(s for s in ktr["steps"] if s["name"] == "Agregar Constantes")
        field_names = [f["name"] for f in constant_step["config"]["fields"]]
        assert "stg_fecha_carga" not in field_names
        assert "stg_estado" in field_names  # el literal no se toca

    def test_function_default_mapping_removed_from_table_output(self):
        ktr = _ktr_with_constant_and_output("CURRENT_TIMESTAMP")
        scrub_function_default_constants(ktr, STEP_TYPE_ALIASES)

        output_step = next(s for s in ktr["steps"] if s["name"] == "Cargar Staging")
        mapped_sources = [f["stream_name"] for f in output_step["config"]["fields"]]
        assert "stg_fecha_carga" not in mapped_sources
        assert "stg_estado" in mapped_sources

    def test_literal_default_is_untouched(self):
        ktr = _ktr_with_constant_and_output("'2026-01-01 00:00:00'")
        # Un valor literal de fecha entre comillas no matchea patrón de función.
        warnings = scrub_function_default_constants(ktr, STEP_TYPE_ALIASES)
        assert warnings == []
        constant_step = next(s for s in ktr["steps"] if s["name"] == "Agregar Constantes")
        field_names = [f["name"] for f in constant_step["config"]["fields"]]
        assert "stg_fecha_carga" in field_names

    def test_string_type_field_is_never_touched_even_with_function_like_value(self):
        # El chequeo solo aplica a Date/Timestamp — un campo String con texto
        # parecido a función no es el bug que se está previniendo.
        ktr = _ktr_with_constant_and_output("NOW()", constant_type="String")
        warnings = scrub_function_default_constants(ktr, STEP_TYPE_ALIASES)
        assert warnings == []

    def test_no_constant_steps_returns_no_warnings(self):
        ktr = {"steps": [{"name": "Dummy1", "type": "Dummy", "config": {}}], "hops": []}
        assert scrub_function_default_constants(ktr, STEP_TYPE_ALIASES) == []


class TestCheckMissingRequiredFields:
    def _ktr_output_step(self, mapped_columns: list[str]):
        return {
            "steps": [
                {
                    "name": "Cargar Staging", "type": "TableOutput",
                    "config": {
                        "connection": "conn_staging", "table": "stg_ejemplo",
                        "fields": [{"stream_name": c, "column_name": c} for c in mapped_columns],
                    },
                },
            ],
            "hops": [],
        }

    def test_missing_required_column_is_reported(self):
        ktr = self._ktr_output_step(["cliente_id"])
        required = {"stg_ejemplo": ["cliente_id", "monto"]}
        warnings = check_missing_required_fields(ktr, STEP_TYPE_ALIASES, required)
        assert len(warnings) == 1
        assert "monto" in warnings[0]

    def test_all_required_columns_mapped_no_warnings(self):
        ktr = self._ktr_output_step(["cliente_id", "monto"])
        required = {"stg_ejemplo": ["cliente_id", "monto"]}
        assert check_missing_required_fields(ktr, STEP_TYPE_ALIASES, required) == []

    def test_none_or_empty_required_columns_is_noop(self):
        ktr = self._ktr_output_step(["cliente_id"])
        assert check_missing_required_fields(ktr, STEP_TYPE_ALIASES, None) == []
        assert check_missing_required_fields(ktr, STEP_TYPE_ALIASES, {}) == []

    def test_table_not_in_required_map_is_ignored(self):
        ktr = self._ktr_output_step(["cliente_id"])
        required = {"otra_tabla": ["col_x"]}
        assert check_missing_required_fields(ktr, STEP_TYPE_ALIASES, required) == []


class TestBuildKtrIntegration:
    def test_build_ktr_strips_function_default_and_warns(self):
        ktr_data = _ktr_with_constant_and_output("NOW()")
        xml, filename, warnings = build_ktr(ktr_data, "Test_Transform")
        assert "NOW()" not in xml
        assert any("función" in w or "funci" in w for w in warnings)

    def test_build_ktr_reports_missing_required_column(self):
        ktr_data = _ktr_with_constant_and_output("'ACTIVO'", constant_type="String")
        xml, filename, warnings = build_ktr(
            ktr_data, "Test_Transform",
            required_columns_by_table={"stg_ejemplo": ["columna_obligatoria_faltante"]},
        )
        assert any("columna_obligatoria_faltante" in w for w in warnings)

    def test_build_ktr_marks_transformation_transactional_by_default(self):
        ktr_data = _ktr_with_constant_and_output("'ACTIVO'", constant_type="String")
        xml, filename, warnings = build_ktr(ktr_data, "Test_Transform")
        assert "<unique_connections>Y</unique_connections>" in xml
