"""
Tests: ddl_adapter.parse_ddl debe clasificar el DEFAULT de cada columna en
"function" (NOW(), gen_random_uuid(), nextval(...)) o "literal" ('ACTIVO', 0,
TRUE), y dejar default_kind=None cuando no hay DEFAULT declarado — sin importar
el nombre de tabla/columna (chequeo general, no atado a un caso puntual).
"""
from __future__ import annotations

from app.services.adapters.ddl_adapter import parse_ddl

DDL_DEFAULTS = """
CREATE TABLE stg_ejemplo (
    id              SERIAL PRIMARY KEY,
    fecha_carga     TIMESTAMP DEFAULT NOW(),
    fecha_carga_kw  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    uuid_col        UUID DEFAULT gen_random_uuid(),
    secuencia       BIGINT DEFAULT nextval('alguna_seq'),
    estado          VARCHAR(20) DEFAULT 'ACTIVO',
    activo          BOOLEAN DEFAULT TRUE,
    cantidad        INTEGER DEFAULT 0,
    obligatorio_sin_default INTEGER NOT NULL,
    opcional_sin_default    VARCHAR(50)
);
"""


def _field(schema, name):
    return next(f for f in schema.fields if f.name == name)


class TestDdlAdapterDefaults:
    def test_function_default_now(self):
        schema = parse_ddl(DDL_DEFAULTS, "postgres")[0]
        f = _field(schema, "fecha_carga")
        assert f.default_kind == "function"
        assert f.default_expr is not None

    def test_function_default_keyword_current_timestamp(self):
        schema = parse_ddl(DDL_DEFAULTS, "postgres")[0]
        f = _field(schema, "fecha_carga_kw")
        assert f.default_kind == "function"

    def test_function_default_gen_random_uuid(self):
        schema = parse_ddl(DDL_DEFAULTS, "postgres")[0]
        f = _field(schema, "uuid_col")
        assert f.default_kind == "function"

    def test_function_default_nextval(self):
        schema = parse_ddl(DDL_DEFAULTS, "postgres")[0]
        f = _field(schema, "secuencia")
        assert f.default_kind == "function"

    def test_literal_default_string(self):
        schema = parse_ddl(DDL_DEFAULTS, "postgres")[0]
        f = _field(schema, "estado")
        assert f.default_kind == "literal"

    def test_literal_default_boolean(self):
        schema = parse_ddl(DDL_DEFAULTS, "postgres")[0]
        f = _field(schema, "activo")
        assert f.default_kind == "literal"

    def test_literal_default_numeric(self):
        schema = parse_ddl(DDL_DEFAULTS, "postgres")[0]
        f = _field(schema, "cantidad")
        assert f.default_kind == "literal"

    def test_not_null_without_default_flagged_required_no_default_kind(self):
        schema = parse_ddl(DDL_DEFAULTS, "postgres")[0]
        f = _field(schema, "obligatorio_sin_default")
        assert f.constraints.required is True
        assert f.default_kind is None

    def test_nullable_without_default_not_required(self):
        schema = parse_ddl(DDL_DEFAULTS, "postgres")[0]
        f = _field(schema, "opcional_sin_default")
        assert f.constraints.required is False
        assert f.default_kind is None
