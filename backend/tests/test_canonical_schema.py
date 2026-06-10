"""
Tests de Fase 0: modelo canónico, type_mappings y db_adapter.

Criterio de aceptación de Fase 0 (Ajuste 4):
  La misma tabla descrita por los tres caminos (conexión BD, su DDL, y un export a CSV)
  debe converger al mismo CanonicalSchema, salvo lo que cada origen genuinamente no
  puede saber.

En esta fase solo existe el adaptador de BD. Los caminos DDL y CSV se representan
mediante fixtures estáticas que simulan lo que esos adaptadores producirán en Fase 2/3.
El test de convergencia valida que los campos que todos los caminos DEBEN conocer
coincidan, y que los que CSV no puede conocer (precision, scale, length) sean None.
"""
import pytest

from app.schemas.canonical import (
    CanonicalField,
    CanonicalSchema,
    CanonicalType,
    ColumnRole,
    ColumnSemantics,
    DwhIntent,
    FieldConstraints,
    ForeignKeyRef,
    TableSemantics,
)
from app.schemas.connection import ColumnInfo
from app.services import adapters
from app.services.adapters import db_adapter
from app.services.adapters.schema_to_context import (
    _field_to_minimal_profile,
    canonical_to_model_context,
)
from app.services.type_mappings import map_sql_type


# ── Fixtures ──────────────────────────────────────────────────────────────────

# Represents the "orders" table as db_connector.get_columns() would return it.
ORDERS_COL_INFOS: list[ColumnInfo] = [
    ColumnInfo(name="id",          type="integer",       nullable=False, primary_key=True),
    ColumnInfo(name="customer_id", type="integer",       nullable=False, primary_key=False),
    ColumnInfo(name="amount",      type="numeric(10,2)", nullable=True,  primary_key=False),
    ColumnInfo(name="status",      type="varchar(20)",   nullable=True,  primary_key=False),
    ColumnInfo(name="active",      type="boolean",       nullable=False, primary_key=False),
    ColumnInfo(name="created_at",  type="date",          nullable=True,  primary_key=False),
]

ORDERS_FK_REFS: list[ForeignKeyRef] = [
    ForeignKeyRef(
        fields=["customer_id"],
        reference_resource="public.customers",
        reference_fields=["id"],
    )
]

# What a DDL-path adapter (Fase 3) would produce for the same table.
# precision/scale/length ARE available from DDL.
ORDERS_DDL_FIELDS: list[tuple] = [
    # (name, type, is_pk, precision, scale, length)
    ("id",          CanonicalType.INTEGER, True,  None, None, None),
    ("customer_id", CanonicalType.INTEGER, False, None, None, None),
    ("amount",      CanonicalType.NUMBER,  False, 10,   2,    None),
    ("status",      CanonicalType.STRING,  False, None, None, 20),
    ("active",      CanonicalType.BOOLEAN, False, None, None, None),
    ("created_at",  CanonicalType.DATE,    False, None, None, None),
]

# What a Frictionless adapter (Fase 2) would produce from a CSV export.
# No precision/scale/length — CSV cannot know them.
ORDERS_CSV_FIELDS: list[tuple] = [
    # (name, type, is_pk)  — precision/scale/length always None from CSV
    ("id",          CanonicalType.INTEGER, True),
    ("customer_id", CanonicalType.INTEGER, False),
    ("amount",      CanonicalType.NUMBER,  False),
    ("status",      CanonicalType.STRING,  False),
    ("active",      CanonicalType.BOOLEAN, False),
    ("created_at",  CanonicalType.DATE,    False),
]


# ── Canonical model tests ─────────────────────────────────────────────────────

class TestCanonicalModels:
    def test_schema_version_default(self):
        schema = CanonicalSchema(
            source_name="t", source_type="database", fields=[]
        )
        assert schema.schema_version == "1.0"

    def test_field_defaults(self):
        f = CanonicalField(name="col")
        assert f.type == CanonicalType.UNKNOWN
        assert f.format == "default"
        assert f.precision is None
        assert f.scale is None
        assert f.length is None
        assert f.is_primary_key is False
        assert f.is_foreign_key is False
        assert f.references is None
        assert f.inferred_by == "user"

    def test_semantic_fields_null_by_default(self):
        f = CanonicalField(name="col")
        assert f.semantics.role is None
        assert f.semantics.semantic_type is None
        assert f.semantics.scd_type is None

    def test_table_semantics_null_by_default(self):
        schema = CanonicalSchema(
            source_name="t", source_type="database", fields=[]
        )
        assert schema.semantics.grain is None
        assert schema.semantics.business_description is None
        assert schema.semantics.dwh_intent is None

    def test_dwh_intent_shape_reserved(self):
        intent = DwhIntent(table_type="fact", scd_type="2")
        assert intent.table_type == "fact"
        assert intent.scd_type == "2"

    def test_foreign_key_ref_round_trip(self):
        fk = ForeignKeyRef(
            fields=["customer_id"],
            reference_resource="public.customers",
            reference_fields=["id"],
        )
        assert fk.fields == ["customer_id"]
        assert fk.reference_resource == "public.customers"

    def test_constraints_required_false_by_default(self):
        c = FieldConstraints()
        assert c.required is False

    def test_column_role_values(self):
        assert ColumnRole.MEASURE == "measure"
        assert ColumnRole.DIMENSION_ATTRIBUTE == "dimension_attribute"

    def test_canonical_type_values(self):
        assert CanonicalType.STRING == "string"
        assert CanonicalType.UNKNOWN == "unknown"


# ── type_mappings tests ───────────────────────────────────────────────────────

class TestMapSqlType:
    def _call(self, type_str):
        canonical, precision, scale, length, fmt = map_sql_type(type_str)
        return canonical, precision, scale, length, fmt

    # Integers
    @pytest.mark.parametrize("raw", [
        "integer", "int", "bigint", "smallint", "tinyint",
        "serial", "bigserial",
    ])
    def test_integer_variants(self, raw):
        t, *_ = self._call(raw)
        assert t == CanonicalType.INTEGER

    # Numbers
    def test_numeric_with_precision_scale(self):
        t, p, s, l, _ = self._call("numeric(10,2)")
        assert t == CanonicalType.NUMBER
        assert p == 10
        assert s == 2
        assert l is None

    def test_decimal_with_precision_scale(self):
        t, p, s, l, _ = self._call("decimal(18,4)")
        assert t == CanonicalType.NUMBER
        assert p == 18
        assert s == 4

    def test_float_no_args(self):
        t, p, s, l, _ = self._call("float")
        assert t == CanonicalType.NUMBER
        assert p is None and s is None and l is None

    def test_double_precision(self):
        t, *_ = self._call("double precision")
        assert t == CanonicalType.NUMBER

    # Strings
    def test_varchar_with_length(self):
        t, p, s, l, _ = self._call("varchar(255)")
        assert t == CanonicalType.STRING
        assert l == 255
        assert p is None and s is None

    def test_character_varying_with_length(self):
        t, p, s, l, _ = self._call("character varying(100)")
        assert t == CanonicalType.STRING
        assert l == 100

    def test_text_no_length(self):
        t, p, s, l, _ = self._call("text")
        assert t == CanonicalType.STRING
        assert l is None

    def test_nvarchar_sqlserver(self):
        t, p, s, l, _ = self._call("nvarchar(50)")
        assert t == CanonicalType.STRING
        assert l == 50

    # UUID — format flag
    def test_uuid_postgres(self):
        t, _, _, _, fmt = self._call("uuid")
        assert t == CanonicalType.STRING
        assert fmt == "uuid"

    def test_uniqueidentifier_sqlserver(self):
        t, _, _, _, fmt = self._call("uniqueidentifier")
        assert t == CanonicalType.STRING
        assert fmt == "uuid"

    # Booleans
    @pytest.mark.parametrize("raw", ["boolean", "bool", "bit"])
    def test_boolean_variants(self, raw):
        t, *_ = self._call(raw)
        assert t == CanonicalType.BOOLEAN

    # Dates / times
    def test_date(self):
        assert self._call("date")[0] == CanonicalType.DATE

    def test_time_variants(self):
        for raw in ("time", "time without time zone", "time with time zone"):
            assert self._call(raw)[0] == CanonicalType.TIME

    def test_datetime_variants(self):
        for raw in (
            "timestamp", "timestamp without time zone", "timestamp with time zone",
            "datetime", "datetime2", "smalldatetime", "datetimeoffset",
        ):
            assert self._call(raw)[0] == CanonicalType.DATETIME, f"failed for: {raw}"

    # Object / binary
    def test_json(self):
        assert self._call("json")[0] == CanonicalType.OBJECT

    def test_jsonb(self):
        assert self._call("jsonb")[0] == CanonicalType.OBJECT

    def test_bytea(self):
        assert self._call("bytea")[0] == CanonicalType.BINARY

    def test_varbinary(self):
        assert self._call("varbinary")[0] == CanonicalType.BINARY

    # Unknown
    def test_unknown_exotic_type(self):
        t, *_ = self._call("some_exotic_type")
        assert t == CanonicalType.UNKNOWN

    def test_default_format_for_non_uuid(self):
        _, _, _, _, fmt = self._call("integer")
        assert fmt == "default"


# ── db_adapter tests ──────────────────────────────────────────────────────────

class TestDbAdapter:
    def test_source_type_and_version(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        assert schema.source_type == "database"
        assert schema.schema_version == "1.0"
        assert schema.source_name == "public.orders"

    def test_field_count(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        assert len(schema.fields) == len(ORDERS_COL_INFOS)

    def test_field_names_order_preserved(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        names = [f.name for f in schema.fields]
        assert names == [ci.name for ci in ORDERS_COL_INFOS]

    def test_primary_key_detection(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        id_field = next(f for f in schema.fields if f.name == "id")
        assert id_field.is_primary_key is True
        assert "id" in schema.primary_key

    def test_non_pk_not_marked(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        amount_field = next(f for f in schema.fields if f.name == "amount")
        assert amount_field.is_primary_key is False

    def test_required_from_nullable(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        id_field   = next(f for f in schema.fields if f.name == "id")
        name_field = next(f for f in schema.fields if f.name == "amount")
        assert id_field.constraints.required is True    # nullable=False
        assert name_field.constraints.required is False # nullable=True

    def test_numeric_precision_scale(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        amount = next(f for f in schema.fields if f.name == "amount")
        assert amount.type == CanonicalType.NUMBER
        assert amount.precision == 10
        assert amount.scale == 2
        assert amount.length is None

    def test_varchar_length(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        status = next(f for f in schema.fields if f.name == "status")
        assert status.type == CanonicalType.STRING
        assert status.length == 20
        assert status.precision is None

    def test_boolean_type(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        active = next(f for f in schema.fields if f.name == "active")
        assert active.type == CanonicalType.BOOLEAN

    def test_date_type(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        created = next(f for f in schema.fields if f.name == "created_at")
        assert created.type == CanonicalType.DATE

    def test_inferred_by_database(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        for f in schema.fields:
            assert f.inferred_by == "database"

    def test_no_fk_by_default(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        assert schema.foreign_keys == []
        for f in schema.fields:
            assert f.is_foreign_key is False
            assert f.references is None

    def test_fk_populated(self):
        schema = db_adapter.build(
            ORDERS_COL_INFOS, "public.orders", fk_refs=ORDERS_FK_REFS
        )
        cust_field = next(f for f in schema.fields if f.name == "customer_id")
        assert cust_field.is_foreign_key is True
        assert cust_field.references is not None
        assert cust_field.references.reference_resource == "public.customers"
        assert schema.foreign_keys == ORDERS_FK_REFS

    def test_non_fk_columns_unaffected(self):
        schema = db_adapter.build(
            ORDERS_COL_INFOS, "public.orders", fk_refs=ORDERS_FK_REFS
        )
        id_field = next(f for f in schema.fields if f.name == "id")
        assert id_field.is_foreign_key is False

    def test_semantics_empty_by_default(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        assert schema.semantics.grain is None
        for f in schema.fields:
            assert f.semantics.role is None

    def test_profile_none_by_default(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        assert schema.profile is None

    def test_empty_table(self):
        schema = db_adapter.build([], "empty_table")
        assert schema.fields == []
        assert schema.primary_key == []
        assert schema.foreign_keys == []


# ── schema_to_context tests ───────────────────────────────────────────────────

class TestSchemaToContext:
    def test_returns_model_context(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        ctx = canonical_to_model_context([schema])
        assert len(ctx.source_tables) == 1
        assert ctx.source_tables[0].table_name == "public.orders"

    def test_field_count_in_context(self):
        schema = db_adapter.build(ORDERS_COL_INFOS, "public.orders")
        ctx = canonical_to_model_context([schema])
        assert len(ctx.source_tables[0].columns) == len(ORDERS_COL_INFOS)

    def test_minimal_profile_type_mapping(self):
        f = CanonicalField(name="amount", type=CanonicalType.NUMBER)
        profile = _field_to_minimal_profile(f)
        assert profile.inferred_type == "float"
        assert profile.name == "amount"

    def test_minimal_profile_format_hint_for_numeric(self):
        f = CanonicalField(
            name="price",
            type=CanonicalType.NUMBER,
            precision=10,
            scale=2,
        )
        profile = _field_to_minimal_profile(f)
        assert profile.format_hint == "numeric(10,2)"

    def test_minimal_profile_format_hint_for_uuid(self):
        f = CanonicalField(name="uid", type=CanonicalType.STRING, format="uuid")
        profile = _field_to_minimal_profile(f)
        assert profile.format_hint == "uuid"

    def test_multiple_schemas(self):
        s1 = db_adapter.build(ORDERS_COL_INFOS, "orders")
        s2 = db_adapter.build(ORDERS_COL_INFOS[:2], "customers")
        ctx = canonical_to_model_context([s1, s2])
        assert len(ctx.source_tables) == 2
        assert ctx.source_tables[1].table_name == "customers"


# ── Test de convergencia (criterio de aceptación de Fase 0) ──────────────────

class TestConvergence:
    """
    The same logical table described by three paths must converge to the same
    CanonicalSchema for the fields that all paths can know.

    Fields that EVERY path must agree on:
      - name, type, is_primary_key

    Fields that CSV genuinely cannot know (must be None from that path):
      - precision, scale, length

    Fields that only DB knows exactly (DDL knows statically; CSV infers):
      - type  (may differ if inference is uncertain, but for the fixture it's clear)
    """

    def _build_db_schema(self) -> CanonicalSchema:
        return db_adapter.build(ORDERS_COL_INFOS, "public.orders", fk_refs=ORDERS_FK_REFS)

    def _build_ddl_schema(self) -> CanonicalSchema:
        """Simulate what the DDL adapter (Fase 3) would produce for the same table."""
        fields = [
            CanonicalField(
                name=name,
                type=ctype,
                is_primary_key=is_pk,
                precision=prec,
                scale=sc,
                length=lng,
                inferred_by="ddl",
            )
            for name, ctype, is_pk, prec, sc, lng in ORDERS_DDL_FIELDS
        ]
        return CanonicalSchema(
            source_name="public.orders",
            source_type="ddl",
            fields=fields,
            primary_key=["id"],
            foreign_keys=ORDERS_FK_REFS,
        )

    def _build_csv_schema(self) -> CanonicalSchema:
        """Simulate what the Frictionless adapter (Fase 2) would produce from a CSV export."""
        fields = [
            CanonicalField(
                name=name,
                type=ctype,
                is_primary_key=is_pk,
                precision=None,
                scale=None,
                length=None,
                inferred_by="frictionless",
            )
            for name, ctype, is_pk in ORDERS_CSV_FIELDS
        ]
        return CanonicalSchema(
            source_name="public.orders",
            source_type="csv",
            fields=fields,
            primary_key=["id"],
        )

    def test_field_names_converge(self):
        db_s  = self._build_db_schema()
        ddl_s = self._build_ddl_schema()
        csv_s = self._build_csv_schema()
        expected_names = [ci.name for ci in ORDERS_COL_INFOS]
        for schema in (db_s, ddl_s, csv_s):
            assert [f.name for f in schema.fields] == expected_names

    def test_types_converge_across_all_paths(self):
        db_s  = self._build_db_schema()
        ddl_s = self._build_ddl_schema()
        csv_s = self._build_csv_schema()
        for db_f, ddl_f, csv_f in zip(db_s.fields, ddl_s.fields, csv_s.fields):
            assert db_f.type == ddl_f.type == csv_f.type, (
                f"type mismatch on column '{db_f.name}': "
                f"db={db_f.type} ddl={ddl_f.type} csv={csv_f.type}"
            )

    def test_primary_key_converges(self):
        db_s  = self._build_db_schema()
        ddl_s = self._build_ddl_schema()
        csv_s = self._build_csv_schema()
        for schema in (db_s, ddl_s, csv_s):
            pk_fields = [f for f in schema.fields if f.is_primary_key]
            assert len(pk_fields) == 1
            assert pk_fields[0].name == "id"

    def test_csv_has_no_precision_scale_length(self):
        csv_s = self._build_csv_schema()
        for f in csv_s.fields:
            assert f.precision is None, f"CSV field '{f.name}' should not have precision"
            assert f.scale is None,     f"CSV field '{f.name}' should not have scale"
            assert f.length is None,    f"CSV field '{f.name}' should not have length"

    def test_db_preserves_precision_scale(self):
        db_s = self._build_db_schema()
        amount = next(f for f in db_s.fields if f.name == "amount")
        assert amount.precision == 10
        assert amount.scale == 2

    def test_db_preserves_length(self):
        db_s = self._build_db_schema()
        status = next(f for f in db_s.fields if f.name == "status")
        assert status.length == 20

    def test_schema_version_1_0_on_all_paths(self):
        for schema in (
            self._build_db_schema(),
            self._build_ddl_schema(),
            self._build_csv_schema(),
        ):
            assert schema.schema_version == "1.0"

    def test_db_and_ddl_agree_on_precision_scale(self):
        db_s  = self._build_db_schema()
        ddl_s = self._build_ddl_schema()
        for db_f, ddl_f in zip(db_s.fields, ddl_s.fields):
            assert db_f.precision == ddl_f.precision, (
                f"precision mismatch on '{db_f.name}'"
            )
            assert db_f.scale == ddl_f.scale, (
                f"scale mismatch on '{db_f.name}'"
            )
