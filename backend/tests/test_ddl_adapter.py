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

    def test_no_raw_data_in_response(self):
        resp = client.post("/api/schema/from-ddl", json={"ddl": DDL_BASIC, "dialect": "postgres"})
        body_str = str(resp.json())
        # No actual row values should appear
        assert "Alice" not in body_str
        assert "profile" in str(resp.json()[0])   # profile key exists but is null
