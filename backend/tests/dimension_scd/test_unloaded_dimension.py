"""docs/refactor/02-decisiones.md, D-pendiente "toda dimensión con FK tiene
loader": ninguna pieza existente cruza dim_contracts × ktr_data × DDL para
confirmar que toda dimensión referenciada por FK tiene un step que la carga.
_dims_with_inferred_member (ver test_inferred_member.py) ve DDL+contratos
pero nunca ktr_data; apply_dimension_contracts (ver test_dimension_step_policy.py)
ve ktr_data+contratos pero nunca DDL, e itera steps YA EXISTENTES — una
dimensión sin ningún step nunca entra a ese loop. find_unloaded_dimensions
cierra el círculo, corriendo DESPUÉS de apply_dimension_contracts.

Máxima que gobierna estos tests: nunca abortar, nunca degradar en silencio.
Los casos 6/7 (DDL ausente/inválido) anclan la segunda mitad — divergen a
propósito de la convención best-effort del resto de ddl_checks.py."""
from __future__ import annotations

from app.schemas.etl_schemas import DimContract
from app.services.ddl_checks import UNVERIFIED_DIMENSION_COVERAGE_FIELD, find_unloaded_dimensions
from app.services.ktr_builder.dimension_step_policy import (
    OVERRIDE_STEP_PREFIX,
    apply_dimension_contracts,
)
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES


def _dim_producto_contract() -> DimContract:
    return DimContract(
        table="dim_producto", scd_type=1, technical_key="sk_producto",
        version_field="", date_from="", date_to="",
        natural_keys=["id_producto"], unknown_key_value=0,
    )


_DWH_DDL_FK_NOT_NULL = """
CREATE TABLE dim_producto (
  sk_producto SERIAL PRIMARY KEY,
  id_producto INTEGER NOT NULL,
  nombre VARCHAR(255)
);
CREATE TABLE fact_venta (
  sk_venta SERIAL PRIMARY KEY,
  fk_producto INTEGER NOT NULL,
  total NUMERIC(12,2),
  FOREIGN KEY (fk_producto) REFERENCES dim_producto (sk_producto)
);
"""

_DWH_DDL_NO_FK = """
CREATE TABLE dim_producto (
  sk_producto SERIAL PRIMARY KEY,
  id_producto INTEGER NOT NULL,
  nombre VARCHAR(255)
);
"""


class TestDimensionSinNingunStep:
    def test_fk_not_null_sin_step_es_error(self):
        """Caso central del diagnóstico: la dimensión no tiene NI loader NI
        lookup — ni siquiera un step huérfano. Sin find_unloaded_dimensions
        esto pasaba en silencio total (apply_dimension_contracts nunca ve la
        tabla porque itera steps existentes, no dim_contracts)."""
        ktr_data = {"steps": []}
        result = find_unloaded_dimensions(
            ktr_data, [_dim_producto_contract()], _DWH_DDL_FK_NOT_NULL, STEP_TYPE_ALIASES,
        )
        assert len(result) == 1
        assert result[0]["tipo"] == "error"
        assert result[0]["campo"] == "dim_producto"
        assert "fact_venta.fk_producto" in result[0]["mensaje"]

    def test_sin_fk_confirmada_es_warning(self):
        """Sin FK NOT NULL que la referencie, no se puede asumir 'error' —
        podría ser una dimensión legítimamente precargada por fuera del ETL."""
        ktr_data = {"steps": []}
        result = find_unloaded_dimensions(
            ktr_data, [_dim_producto_contract()], _DWH_DDL_NO_FK, STEP_TYPE_ALIASES,
        )
        assert len(result) == 1
        assert result[0]["tipo"] == "warning"
        assert result[0]["campo"] == "dim_producto"


class TestDimensionConLoader:
    def test_loader_presente_no_dispara(self):
        """Camino sano: update='Y' ya sintetizado (como lo deja
        apply_dimension_contracts) — sin falso positivo."""
        ktr_data = {
            "steps": [
                {"name": "Cargar dim_producto", "type": "DimensionLookup",
                 "config": {"table": "dim_producto", "connection": "conn_dwh",
                            "return_field": "sk_producto", "update": "Y"}},
            ],
        }
        result = find_unloaded_dimensions(
            ktr_data, [_dim_producto_contract()], _DWH_DDL_FK_NOT_NULL, STEP_TYPE_ALIASES,
        )
        assert result == []

    def test_solo_fact_lookup_update_n_sigue_siendo_error(self):
        """Existe un step sobre la tabla, pero es de solo-lectura
        (update='N', rol fact_lookup, D16) — ninguno la CARGA. Este es el
        caso que 'lookup huérfano' (test_dimension_step_policy.py) no
        distingue del ambiguo: acá SÍ hay contrato con FK NOT NULL, así que
        el hueco real (loader nunca escrito) tiene que salir como error."""
        ktr_data = {
            "steps": [
                {"name": "Buscar FK dim_producto", "type": "DimensionLookup",
                 "config": {"table": "dim_producto", "connection": "conn_dwh",
                            "return_field": "sk_producto", "update": "N"}},
                {"name": "Cargar Fact Venta", "type": "TableOutput",
                 "config": {"table": "fact_venta", "connection": "conn_dwh",
                            "fields": [{"column_name": "fk_producto", "dest": "fk_producto"}]}},
            ],
        }
        result = find_unloaded_dimensions(
            ktr_data, [_dim_producto_contract()], _DWH_DDL_FK_NOT_NULL, STEP_TYPE_ALIASES,
        )
        assert len(result) == 1
        assert result[0]["tipo"] == "error"
        assert result[0]["campo"] == "dim_producto"


class TestOverrideRegistrado:
    def test_override_registrado_cuenta_como_cubierto(self):
        """Mismo gate que apply_dimension_contracts (has_registered_override,
        ex-_has_registered_override): una decisión explícita del modelo no es
        un hueco, aunque el step no haya quedado con update='Y'."""
        ktr_data = {
            "steps": [
                {"name": "Cargar dim_producto (override)", "type": "CombinationLookup",
                 "config": {"table": "dim_producto", "connection": "conn_dwh",
                            "return_field": "sk_producto"}},
            ],
        }
        validaciones_modelo = [{
            "tipo": "info", "campo": "dim_producto",
            "mensaje": f"{OVERRIDE_STEP_PREFIX}override manual registrado por el modelo",
        }]
        result = find_unloaded_dimensions(
            ktr_data, [_dim_producto_contract()], _DWH_DDL_FK_NOT_NULL, STEP_TYPE_ALIASES,
            validaciones_modelo,
        )
        assert result == []


class TestDegradacionSinDDL:
    """Ancla de la máxima 'nunca crear sin notificar' — DDL ausente/inválido
    no puede degradar a [] en silencio, a diferencia del resto de este
    módulo (ver docstring de find_unloaded_dimensions)."""

    def test_ddl_none_notifica_degradacion_y_reporta_warning(self):
        ktr_data = {"steps": []}
        result = find_unloaded_dimensions(
            ktr_data, [_dim_producto_contract()], None, STEP_TYPE_ALIASES,
        )
        assert len(result) == 2
        campos = {r["campo"] for r in result}
        assert UNVERIFIED_DIMENSION_COVERAGE_FIELD in campos
        assert "dim_producto" in campos
        degradacion = next(r for r in result if r["campo"] == UNVERIFIED_DIMENSION_COVERAGE_FIELD)
        assert degradacion["tipo"] == "warning"
        dim_finding = next(r for r in result if r["campo"] == "dim_producto")
        assert dim_finding["tipo"] == "warning"  # nunca error sin poder confirmar la FK

    def test_ddl_invalido_mismo_resultado_que_ausente(self):
        ktr_data = {"steps": []}
        result = find_unloaded_dimensions(
            ktr_data, [_dim_producto_contract()], "no es SQL válido {{{", STEP_TYPE_ALIASES,
        )
        assert len(result) == 2
        assert any(r["campo"] == UNVERIFIED_DIMENSION_COVERAGE_FIELD for r in result)


class TestSinDimContracts:
    def test_dim_contracts_vacio_no_reporta_nada(self):
        """Ese hueco ('dim_contracts se perdió del todo') ya lo cubre
        _dim_contracts_anomaly_warning — no duplicar."""
        ktr_data = {"steps": []}
        assert find_unloaded_dimensions(ktr_data, [], _DWH_DDL_FK_NOT_NULL, STEP_TYPE_ALIASES) == []


class TestIntegracionConApplyDimensionContracts:
    def test_orden_loader_sintetizado_no_es_falso_positivo(self):
        """Protege el acoplamiento de orden: find_unloaded_dimensions tiene
        que correr DESPUÉS de apply_dimension_contracts. Acá un
        CombinationLookup (único candidato, sin hop a otra tabla) se
        convierte en DimensionLookup + update='Y' — si find_unloaded_dimensions
        corriera ANTES o sobre una copia sin mutar, o si alguien invierte el
        orden de las dos llamadas, esto rompe."""
        ktr_data = {
            "steps": [
                {"name": "Cargar dim_producto", "type": "CombinationLookup",
                 "config": {
                     "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                     "keys": [{"stream": "producto_id", "lookup": "id_producto"}],
                 }},
            ],
        }
        contract = _dim_producto_contract()

        apply_dimension_contracts(ktr_data, [contract], STEP_TYPE_ALIASES, [])
        assert ktr_data["steps"][0]["type"] == "DimensionLookup"
        assert ktr_data["steps"][0]["config"]["update"] == "Y"

        result = find_unloaded_dimensions(ktr_data, [contract], None, STEP_TYPE_ALIASES)
        assert result == []  # nada faltante -> ni siquiera se llega a evaluar el DDL
