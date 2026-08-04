"""
Tests de Fase 3: ddl_adapter.parse_ddl y endpoint POST /api/schema/from-ddl.
No requieren BD ni frictionless — solo sqlglot + el app en modo TestClient.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.canonical import CanonicalType
from app.services.adapters.ddl_adapter import parse_ddl

client = TestClient(app)


# ── DDL fixtures ──────────────────────────────────────────────────────────────

DDL_BASIC = """
CREATE TABLE public.orders (
    id          SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL,
    amount      DECIMAL(10,2),
    status      VARCHAR(20),
    active      BOOLEAN DEFAULT TRUE,
    created_at  DATE
);
"""

DDL_TWO_TABLES = """
CREATE TABLE customers (id INT PRIMARY KEY, name TEXT);
CREATE TABLE items     (item_id INT PRIMARY KEY, label VARCHAR(100));
"""

DDL_TABLE_LEVEL_PK_FK = """
CREATE TABLE orders (
    order_id    INT,
    customer_id INT,
    amount      DECIMAL(10,2),
    PRIMARY KEY (order_id),
    FOREIGN KEY (customer_id) REFERENCES customers(id)
);
"""

DDL_TSQL = """
CREATE TABLE dbo.products (
    product_id   INT IDENTITY(1,1) PRIMARY KEY,
    product_name NVARCHAR(200) NOT NULL,
    price        MONEY,
    created_at   DATETIME2
);
"""

DDL_UNKNOWN_TYPE = """
CREATE TABLE t (
    id   INT PRIMARY KEY,
    geom GEOGRAPHY
);
"""

# H38 — CHECK constraints y PK/FK con CONSTRAINT nombrado (docs/refactor/01-hallazgos.md)

DDL_NAMED_CONSTRAINTS = """
CREATE TABLE padre (
    id INT,
    CONSTRAINT pk_padre PRIMARY KEY (id)
);
CREATE TABLE hijo (
    id INT,
    padre_id INT,
    CONSTRAINT pk_hijo PRIMARY KEY (id),
    CONSTRAINT fk_hijo_padre FOREIGN KEY (padre_id) REFERENCES padre (id)
);
"""

DDL_CHECK_TABLE_LEVEL_AND = """
CREATE TABLE producto (
    precio_lista DECIMAL(10,2),
    precio_unitario DECIMAL(10,2),
    stock INT,
    CONSTRAINT ck_producto CHECK (precio_lista >= 0 AND precio_unitario >= 0 AND stock >= 0)
);
"""

DDL_CHECK_COLUMN_LEVEL = "CREATE TABLE t (precio DECIMAL(10,2) CHECK (precio >= 0));"
DDL_CHECK_BETWEEN = "CREATE TABLE t (edad INT CHECK (edad BETWEEN 0 AND 120));"
DDL_CHECK_IN = "CREATE TABLE t (estado VARCHAR(10) CHECK (estado IN ('A', 'B', 'C')));"
DDL_CHECK_REVERSED = "CREATE TABLE t (precio DECIMAL(10,2) CHECK (0 <= precio));"
DDL_CHECK_OR = "CREATE TABLE t (x INT CHECK (x < 0 OR x > 100));"
DDL_CHECK_FUNCTION = "CREATE TABLE t (nombre VARCHAR(50) CHECK (LENGTH(nombre) > 0));"
DDL_CHECK_STRICT_INT_GT = "CREATE TABLE t (cantidad INT CHECK (cantidad > 0));"
DDL_CHECK_STRICT_INT_LT = "CREATE TABLE t (nivel INT CHECK (nivel < 10));"
DDL_CHECK_STRICT_NUMBER = "CREATE TABLE t (precio DECIMAL(10,2) CHECK (precio > 0));"


# ── parse_ddl unit tests ──────────────────────────────────────────────────────

class TestParseDDL:
    def test_single_table_returns_one_schema(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        assert len(schemas) == 1

    def test_source_name_with_schema(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        assert schemas[0].source_name == "public.orders"

    def test_source_type_is_ddl(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        assert schemas[0].source_type == "ddl"

    def test_schema_version_1_0(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        assert schemas[0].schema_version == "1.0"

    def test_field_count(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        assert len(schemas[0].fields) == 6

    def test_serial_maps_to_integer(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        id_field = next(f for f in schemas[0].fields if f.name == "id")
        assert id_field.type == CanonicalType.INTEGER

    def test_decimal_precision_scale(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        amount = next(f for f in schemas[0].fields if f.name == "amount")
        assert amount.type == CanonicalType.NUMBER
        assert amount.precision == 10
        assert amount.scale == 2

    def test_varchar_length(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        status = next(f for f in schemas[0].fields if f.name == "status")
        assert status.type == CanonicalType.STRING
        assert status.length == 20

    def test_boolean_type(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        active = next(f for f in schemas[0].fields if f.name == "active")
        assert active.type == CanonicalType.BOOLEAN

    def test_date_type(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        created = next(f for f in schemas[0].fields if f.name == "created_at")
        assert created.type == CanonicalType.DATE

    def test_inline_pk_detected(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        id_field = next(f for f in schemas[0].fields if f.name == "id")
        assert id_field.is_primary_key is True
        assert "id" in schemas[0].primary_key

    def test_not_null_sets_required(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        cust = next(f for f in schemas[0].fields if f.name == "customer_id")
        assert cust.constraints.required is True

    def test_nullable_not_required(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        amount = next(f for f in schemas[0].fields if f.name == "amount")
        assert amount.constraints.required is False

    def test_multiple_tables(self):
        schemas = parse_ddl(DDL_TWO_TABLES, None)
        assert len(schemas) == 2
        names = {s.source_name for s in schemas}
        assert "customers" in names
        assert "items" in names

    def test_table_level_pk(self):
        schemas = parse_ddl(DDL_TABLE_LEVEL_PK_FK, None)
        order_id = next(f for f in schemas[0].fields if f.name == "order_id")
        assert order_id.is_primary_key is True

    def test_table_level_fk(self):
        schemas = parse_ddl(DDL_TABLE_LEVEL_PK_FK, None)
        cust_id = next(f for f in schemas[0].fields if f.name == "customer_id")
        assert cust_id.is_foreign_key is True
        assert cust_id.references is not None
        assert cust_id.references.reference_resource == "customers"
        assert len(schemas[0].foreign_keys) == 1

    def test_tsql_dialect_nvarchar(self):
        schemas = parse_ddl(DDL_TSQL, "tsql")
        assert len(schemas) == 1
        name_field = next(f for f in schemas[0].fields if f.name == "product_name")
        assert name_field.type == CanonicalType.STRING
        assert name_field.length == 200

    def test_tsql_money_type(self):
        schemas = parse_ddl(DDL_TSQL, "tsql")
        price = next(f for f in schemas[0].fields if f.name == "price")
        assert price.type == CanonicalType.NUMBER

    def test_tsql_datetime2_type(self):
        schemas = parse_ddl(DDL_TSQL, "tsql")
        created = next(f for f in schemas[0].fields if f.name == "created_at")
        assert created.type == CanonicalType.DATETIME

    def test_unknown_type_maps_to_unknown(self):
        schemas = parse_ddl(DDL_UNKNOWN_TYPE, "postgres")
        geom = next(f for f in schemas[0].fields if f.name == "geom")
        assert geom.type == CanonicalType.UNKNOWN

    def test_unknown_type_does_not_raise(self):
        schemas = parse_ddl(DDL_UNKNOWN_TYPE, "postgres")
        assert len(schemas) == 1   # table still parsed, only geom is UNKNOWN

    def test_inferred_by_ddl(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        for field in schemas[0].fields:
            assert field.inferred_by == "ddl"

    def test_no_profile_attached(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        assert schemas[0].profile is None

    def test_empty_ddl_returns_empty_list(self):
        schemas = parse_ddl("-- just a comment", None)
        assert schemas == []

    def test_source_name_without_schema(self):
        schemas = parse_ddl("CREATE TABLE items (id INT);", None)
        assert schemas[0].source_name == "items"

    def test_no_fk_by_default(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        assert schemas[0].foreign_keys == []

    def test_precision_none_for_integer(self):
        schemas = parse_ddl(DDL_BASIC, "postgres")
        cust_id = next(f for f in schemas[0].fields if f.name == "customer_id")
        assert cust_id.precision is None
        assert cust_id.scale is None
        assert cust_id.length is None


# ── H38: PK/FK con CONSTRAINT nombrado ────────────────────────────────────────
# Confirmado contra DDL real de DWH que TODOS los constraints salen nombrados
# (CONSTRAINT pk_x / fk_x) — sin desenvolver exp.Constraint, ni PK ni FK se
# detectaban (docs/arquitectura-objetivo-candidatos.md, C1).

class TestNamedConstraints:
    def test_named_table_level_pk_detected(self):
        schemas = parse_ddl(DDL_NAMED_CONSTRAINTS, "postgres")
        padre = next(s for s in schemas if s.source_name == "padre")
        assert padre.primary_key == ["id"]
        assert next(f for f in padre.fields if f.name == "id").is_primary_key is True

    def test_named_table_level_fk_detected(self):
        schemas = parse_ddl(DDL_NAMED_CONSTRAINTS, "postgres")
        hijo = next(s for s in schemas if s.source_name == "hijo")
        assert len(hijo.foreign_keys) == 1
        assert hijo.foreign_keys[0].reference_resource == "padre"
        padre_id = next(f for f in hijo.fields if f.name == "padre_id")
        assert padre_id.is_foreign_key is True
        assert padre_id.references.reference_resource == "padre"

    def test_named_pk_does_not_break_own_table(self):
        schemas = parse_ddl(DDL_NAMED_CONSTRAINTS, "postgres")
        hijo = next(s for s in schemas if s.source_name == "hijo")
        assert hijo.primary_key == ["id"]


# ── H38: CHECK constraints → minimum/maximum/enum ────────────────────────────

class TestCheckConstraints:
    def test_table_level_named_check_multi_column(self):
        schemas = parse_ddl(DDL_CHECK_TABLE_LEVEL_AND, "postgres")
        fields = {f.name: f for f in schemas[0].fields}
        assert fields["precio_lista"].constraints.minimum == "0"
        assert fields["precio_unitario"].constraints.minimum == "0"
        assert fields["stock"].constraints.minimum == "0"

    def test_column_level_inline_check(self):
        schemas = parse_ddl(DDL_CHECK_COLUMN_LEVEL, "postgres")
        assert schemas[0].fields[0].constraints.minimum == "0"

    def test_between_maps_to_minimum_and_maximum(self):
        schemas = parse_ddl(DDL_CHECK_BETWEEN, "postgres")
        edad = schemas[0].fields[0]
        assert edad.constraints.minimum == "0"
        assert edad.constraints.maximum == "120"

    def test_in_maps_to_enum(self):
        schemas = parse_ddl(DDL_CHECK_IN, "postgres")
        assert schemas[0].fields[0].constraints.enum == ["A", "B", "C"]

    def test_reversed_operand_order(self):
        schemas = parse_ddl(DDL_CHECK_REVERSED, "postgres")
        assert schemas[0].fields[0].constraints.minimum == "0"

    def test_or_condition_is_discarded_not_raised(self):
        schemas = parse_ddl(DDL_CHECK_OR, "postgres")
        x = schemas[0].fields[0]
        assert x.constraints.minimum is None
        assert x.constraints.maximum is None

    def test_function_in_condition_is_discarded(self):
        schemas = parse_ddl(DDL_CHECK_FUNCTION, "postgres")
        assert schemas[0].fields[0].constraints.minimum is None

    def test_strict_gt_on_integer_adds_one(self):
        schemas = parse_ddl(DDL_CHECK_STRICT_INT_GT, "postgres")
        assert schemas[0].fields[0].constraints.minimum == "1"

    def test_strict_lt_on_integer_subtracts_one(self):
        schemas = parse_ddl(DDL_CHECK_STRICT_INT_LT, "postgres")
        assert schemas[0].fields[0].constraints.maximum == "9"

    def test_strict_gt_on_number_is_discarded(self):
        """NUMBER sin escala fija diferido — ver docs/refactor/01-hallazgos.md H38."""
        schemas = parse_ddl(DDL_CHECK_STRICT_NUMBER, "postgres")
        assert schemas[0].fields[0].constraints.minimum is None

    @pytest.mark.parametrize("dialect", ["postgres", "tsql"])
    def test_check_extraction_identical_across_dialects(self, dialect):
        schemas = parse_ddl(DDL_CHECK_TABLE_LEVEL_AND, dialect)
        fields = {f.name: f for f in schemas[0].fields}
        assert fields["precio_lista"].constraints.minimum == "0"
        assert fields["stock"].constraints.minimum == "0"


# ── /api/schema/from-ddl endpoint tests ──────────────────────────────────────

class TestFromDDLEndpoint:
    def test_basic_ddl_returns_schemas(self):
        resp = client.post(
            "/api/schema/from-ddl",
            json={"ddl": DDL_BASIC, "dialect": "postgres"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert isinstance(body, list)
        assert len(body) == 1

    def test_schema_version_in_response(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_BASIC, "dialect": "postgres"})
        assert resp.json()[0]["schema_version"] == "1.0"

    def test_source_type_is_ddl(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_BASIC, "dialect": "postgres"})
        assert resp.json()[0]["source_type"] == "ddl"

    def test_fields_returned(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_BASIC, "dialect": "postgres"})
        assert len(resp.json()[0]["fields"]) == 6

    def test_pk_in_response(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_BASIC, "dialect": "postgres"})
        body = resp.json()[0]
        id_field = next(f for f in body["fields"] if f["name"] == "id")
        assert id_field["is_primary_key"] is True
        assert "id" in body["primary_key"]

    def test_decimal_precision_in_response(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_BASIC, "dialect": "postgres"})
        amount = next(f for f in resp.json()[0]["fields"] if f["name"] == "amount")
        assert amount["precision"] == 10
        assert amount["scale"] == 2

    def test_two_tables(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_TWO_TABLES, "dialect": "ansi"})
        assert resp.status_code == 200
        assert len(resp.json()) == 2

    def test_empty_ddl_returns_422(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": "", "dialect": "ansi"})
        assert resp.status_code == 422

    def test_no_create_table_returns_422(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": "SELECT 1;", "dialect": "ansi"})
        assert resp.status_code == 422

    def test_tsql_dialect(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_TSQL, "dialect": "tsql"})
        assert resp.status_code == 200
        assert resp.json()[0]["source_name"] == "dbo.products"

    def test_unknown_type_in_response(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_UNKNOWN_TYPE, "dialect": "postgres"})
        assert resp.status_code == 200
        geom = next(f for f in resp.json()[0]["fields"] if f["name"] == "geom")
        assert geom["type"] == "unknown"

    def test_fk_in_response(self):
        resp = client.post(
            "/api/schema/from-ddl",
            json={"ddl": DDL_TABLE_LEVEL_PK_FK, "dialect": "ansi"},
        )
        body = resp.json()[0]
        assert len(body["foreign_keys"]) == 1
        assert body["foreign_keys"][0]["reference_resource"] == "customers"

    def test_default_dialect_is_ansi(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": "CREATE TABLE t (id INT);"})
        assert resp.status_code == 200

    def test_named_pk_fk_in_response(self):
        resp = client.post(
            "/api/schema/from-ddl",
            json={"ddl": DDL_NAMED_CONSTRAINTS, "dialect": "postgres"},
        )
        assert resp.status_code == 200, resp.text
        hijo = next(s for s in resp.json() if s["source_name"] == "hijo")
        assert hijo["primary_key"] == ["id"]
        assert len(hijo["foreign_keys"]) == 1

    def test_check_minimum_in_response(self):
        resp = client.post(
            "/api/schema/from-ddl",
            json={"ddl": DDL_CHECK_COLUMN_LEVEL, "dialect": "postgres"},
        )
        assert resp.status_code == 200, resp.text
        precio = resp.json()[0]["fields"][0]
        assert precio["constraints"]["minimum"] == "0"

    def test_no_raw_data_in_response(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_BASIC, "dialect": "postgres"})
        body_str = str(resp.json())
        # No actual row values should appear
        assert "Alice" not in body_str
        assert "profile" in str(resp.json()[0])   # profile key exists but is null
