"""D21 (02-decisiones.md) / R5-b-R11 (03-plan.md, F4): dimensiones referenciadas
por una FK NOT NULL de una tabla de hechos necesitan el patrón anti-join+Union
hacia el loader único (miembro inferido). Dos tests por D13: uno de lo que esta
pieza trabaja (_dims_with_inferred_member), uno del contrato que expone hacia
el prompt (_format_inferred_member_dims / _build_prompt_from_inference)."""
from __future__ import annotations

from app.schemas.etl_schemas import DimContract
from app.services.ddl_checks import _dims_with_inferred_member
from app.services.etl_generator import (
    _build_prompt_from_inference,
    _format_inferred_member_dims,
    _inferred_member_notifications,
)


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

_DWH_DDL_FK_NULLABLE = """
CREATE TABLE dim_producto (
  sk_producto SERIAL PRIMARY KEY,
  id_producto INTEGER NOT NULL,
  nombre VARCHAR(255)
);
CREATE TABLE fact_venta (
  sk_venta SERIAL PRIMARY KEY,
  fk_producto INTEGER,
  total NUMERIC(12,2),
  FOREIGN KEY (fk_producto) REFERENCES dim_producto (sk_producto)
);
"""

_DWH_DDL_FK_OUTSIDE_CONTRACT = """
CREATE TABLE dim_sucursal (
  sk_sucursal SERIAL PRIMARY KEY,
  id_sucursal INTEGER NOT NULL
);
CREATE TABLE fact_venta (
  sk_venta SERIAL PRIMARY KEY,
  fk_sucursal INTEGER NOT NULL,
  FOREIGN KEY (fk_sucursal) REFERENCES dim_sucursal (sk_sucursal)
);
"""


class TestDimsWithInferredMember:
    def test_fk_not_null_hacia_dimension_del_contrato_dispara(self):
        result = _dims_with_inferred_member(_DWH_DDL_FK_NOT_NULL, [_dim_producto_contract()])
        assert result == [{
            "dimension": "dim_producto",
            "fact_table": "fact_venta",
            "fk_column": "fk_producto",
            "natural_keys": ["id_producto"],
        }]

    def test_fk_nullable_no_dispara(self):
        assert _dims_with_inferred_member(_DWH_DDL_FK_NULLABLE, [_dim_producto_contract()]) == []

    def test_fk_hacia_tabla_fuera_de_dim_contracts_no_dispara(self):
        assert _dims_with_inferred_member(_DWH_DDL_FK_OUTSIDE_CONTRACT, [_dim_producto_contract()]) == []

    def test_sin_dim_contracts_no_dispara(self):
        assert _dims_with_inferred_member(_DWH_DDL_FK_NOT_NULL, []) == []

    def test_ddl_vacio_no_dispara(self):
        assert _dims_with_inferred_member("", [_dim_producto_contract()]) == []

    def test_ddl_invalido_no_rompe(self):
        assert _dims_with_inferred_member("no es SQL válido {{{", [_dim_producto_contract()]) == []


class TestFormatAndNotifications:
    def test_sin_dimensiones_no_agrega_nada_al_prompt(self):
        assert _format_inferred_member_dims([]) == ""

    def test_con_dimensiones_declara_tabla_fk_y_natural_keys(self):
        dims = _dims_with_inferred_member(_DWH_DDL_FK_NOT_NULL, [_dim_producto_contract()])
        text = _format_inferred_member_dims(dims)
        assert "DIMENSIONES CON MIEMBRO INFERIDO OBLIGATORIO" in text
        assert "dim_producto" in text
        assert "fact_venta.fk_producto" in text
        assert "id_producto" in text

    def test_sin_dimensiones_no_genera_notificaciones(self):
        assert _inferred_member_notifications([]) == []

    def test_con_dimensiones_genera_una_notificacion_accionable_por_dimension(self):
        dims = _dims_with_inferred_member(_DWH_DDL_FK_NOT_NULL, [_dim_producto_contract()])
        notifications = _inferred_member_notifications(dims)
        assert len(notifications) == 1
        assert "dim_producto" in notifications[0]
        assert "fact_venta.fk_producto" in notifications[0]


class TestPromptContract:
    """Contrato que esta pieza expone hacia el prompt STG→DWH (D13, punto 1)."""

    def _make_req(self, dwh_model: str, dim_contracts: list[DimContract]):
        from app.schemas.etl_schemas import ETLFromInferenceRequest
        return ETLFromInferenceRequest(
            descripcionObjetivo="Cargar ventas",
            origenTables=[],
            stg_definition="CREATE TABLE staging_ventas (id_producto INTEGER);",
            dwh_model=dwh_model,
            reglasNegocio="",
            dim_contracts=dim_contracts,
        )

    def test_prompt_stg_dwh_incluye_seccion_cuando_hay_fk_not_null(self):
        req = self._make_req(_DWH_DDL_FK_NOT_NULL, [_dim_producto_contract()])
        prompt = _build_prompt_from_inference(req, "", mode="stg_dwh", dwh_ddl=_DWH_DDL_FK_NOT_NULL)
        assert "DIMENSIONES CON MIEMBRO INFERIDO OBLIGATORIO" in prompt
        assert "dim_producto" in prompt

    def test_prompt_stg_dwh_no_incluye_seccion_sin_fk_not_null(self):
        req = self._make_req(_DWH_DDL_FK_NULLABLE, [_dim_producto_contract()])
        prompt = _build_prompt_from_inference(req, "", mode="stg_dwh", dwh_ddl=_DWH_DDL_FK_NULLABLE)
        assert "DIMENSIONES CON MIEMBRO INFERIDO OBLIGATORIO" not in prompt

    def test_prompt_origen_stg_nunca_incluye_seccion(self):
        req = self._make_req(_DWH_DDL_FK_NOT_NULL, [_dim_producto_contract()])
        prompt = _build_prompt_from_inference(req, "", mode="origen_stg", staging_tables=["staging_ventas"])
        assert "MIEMBRO INFERIDO" not in prompt
