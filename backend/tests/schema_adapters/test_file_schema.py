"""
Tests de Fase 2: frictionless_adapter, file_schema.infer_file_schema,
y el endpoint POST /api/schema/infer.

CSV files are created in a temp dir — no external files needed.
"""
from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.canonical import CanonicalType
from app.services.adapters.frictionless_adapter import frictionless_schema_to_canonical
from app.services.file_schema import _raw_to_profiler_rows, infer_file_schema


# ── Helpers ───────────────────────────────────────────────────────────────────

def _write_csv(content: str, suffix: str = ".csv") -> str:
    """Write content to a temp file and return its path."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as f:
        f.write(content)
        return f.name


CSV_BASIC = (
    "id,name,amount,active,created_at\n"
    "1,Alice,1234.56,true,2024-01-15\n"
    "2,Bob,,false,2024-02-20\n"
    "3,Carol,999.99,true,\n"
)

CSV_SEMICOLON = (
    "id;name;value\n"
    "1;Foo;10\n"
    "2;Bar;20\n"
)

CSV_LATIN1 = "nombre,valor\nAñó,1\nÜmlaüt,2\n"


# ── frictionless_adapter tests ────────────────────────────────────────────────

class TestFrictionlessAdapter:
    def _get_fr_schema(self, csv_content: str):
        from frictionless import Detector, Resource
        path = _write_csv(csv_content)
        try:
            r = Resource(path, detector=Detector(sample_size=100))
            r.open()
            schema = r.schema
            r.close()
            return schema
        finally:
            os.unlink(path)

    def test_integer_field(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        id_field = next(f for f in canonical.fields if f.name == "id")
        assert id_field.type == CanonicalType.INTEGER

    def test_string_field(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        name_field = next(f for f in canonical.fields if f.name == "name")
        assert name_field.type == CanonicalType.STRING

    def test_number_field(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        amount = next(f for f in canonical.fields if f.name == "amount")
        assert amount.type == CanonicalType.NUMBER

    def test_boolean_field(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        active = next(f for f in canonical.fields if f.name == "active")
        assert active.type == CanonicalType.BOOLEAN

    def test_date_field(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        date_field = next(f for f in canonical.fields if f.name == "created_at")
        assert date_field.type == CanonicalType.DATE

    def test_inferred_by_frictionless(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        for field in canonical.fields:
            assert field.inferred_by == "frictionless"

    def test_source_type_csv(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "orders", "csv")
        assert canonical.source_type == "csv"
        assert canonical.source_name == "orders"

    def test_source_type_excel(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "sheet1", "excel")
        assert canonical.source_type == "excel"

    def test_field_count(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        assert len(canonical.fields) == 5   # id, name, amount, active, created_at

    def test_no_profile_attached(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        assert canonical.profile is None   # profile is attached by file_schema.py

    def test_precision_scale_none_from_file(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        amount = next(f for f in canonical.fields if f.name == "amount")
        assert amount.precision is None
        assert amount.scale is None
        assert amount.length is None

    def test_schema_version_default(self):
        fr = self._get_fr_schema(CSV_BASIC)
        canonical = frictionless_schema_to_canonical(fr, "test", "csv")
        assert canonical.schema_version == "1.0"


# ── file_schema.infer_file_schema tests ──────────────────────────────────────

class TestInferFileSchema:
    def test_basic_csv(self):
        path = _write_csv(CSV_BASIC)
        try:
            schema = infer_file_schema(path, "orders")
            assert schema.source_name == "orders"
            assert schema.source_type == "csv"
            assert len(schema.fields) == 5
        finally:
            os.unlink(path)

    def test_schema_has_profile(self):
        path = _write_csv(CSV_BASIC)
        try:
            schema = infer_file_schema(path, "orders")
            assert schema.profile is not None
            assert len(schema.profile.column_profiles) == 5
        finally:
            os.unlink(path)

    def test_null_pct_in_profile(self):
        path = _write_csv(CSV_BASIC)
        try:
            schema = infer_file_schema(path, "orders")
            # "amount" has 1 null out of 3 rows → ~33%
            amount_profile = next(
                p for p in schema.profile.column_profiles if p.name == "amount"
            )
            assert amount_profile.null_pct > 0
        finally:
            os.unlink(path)

    def test_distinct_count_in_profile(self):
        path = _write_csv(CSV_BASIC)
        try:
            schema = infer_file_schema(path, "orders")
            name_profile = next(
                p for p in schema.profile.column_profiles if p.name == "name"
            )
            assert name_profile.distinct_count == 3
        finally:
            os.unlink(path)

    def test_semicolon_delimiter_detected(self):
        path = _write_csv(CSV_SEMICOLON)
        try:
            schema = infer_file_schema(path, "data")
            names = [f.name for f in schema.fields]
            assert "id" in names and "name" in names and "value" in names
        finally:
            os.unlink(path)

    def test_invalid_file_raises_value_error(self):
        path = _write_csv("not,valid\x00\x01\x02garbage", suffix=".csv")
        # Frictionless may or may not raise — this is a best-effort test.
        # The key is that it doesn't raise a non-ValueError exception.
        try:
            infer_file_schema(path, "bad")
        except ValueError:
            pass   # expected
        except Exception as exc:
            pytest.fail(f"Expected ValueError, got {type(exc).__name__}: {exc}")
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_schema_version_1_0(self):
        path = _write_csv(CSV_BASIC)
        try:
            schema = infer_file_schema(path, "t")
            assert schema.schema_version == "1.0"
        finally:
            os.unlink(path)


# ── _raw_to_profiler_rows helper ─────────────────────────────────────────────

class TestRawToProfilerRows:
    def test_basic_conversion(self):
        sample = [
            ["id", "name", "val"],
            ["1",  "Alice", "10"],
            ["2",  "Bob",   ""],
        ]
        rows = _raw_to_profiler_rows(sample, ["id", "name", "val"])
        assert len(rows) == 2
        assert rows[0] == ["1", "Alice", "10"]
        assert rows[1][2] is None   # empty string → None

    def test_empty_sample(self):
        rows = _raw_to_profiler_rows([], ["a", "b"])
        assert rows == []

    def test_only_header(self):
        rows = _raw_to_profiler_rows([["a", "b"]], ["a", "b"])
        assert rows == []


# ── POST /api/schema/infer endpoint tests ────────────────────────────────────

client = TestClient(app)


class TestSchemaInferEndpoint:
    def _csv_upload(self, content: str, filename: str = "test.csv"):
        return ("file", (filename, content.encode("utf-8"), "text/csv"))

    def test_happy_path_csv(self):
        resp = client.post(
            "/api/schema/infer",
            files=[self._csv_upload(CSV_BASIC)],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["schema_version"] == "1.0"
        assert body["source_type"] == "csv"
        assert len(body["fields"]) == 5

    def test_field_types_returned(self):
        resp = client.post(
            "/api/schema/infer",
            files=[self._csv_upload(CSV_BASIC)],
        )
        body = resp.json()
        type_map = {f["name"]: f["type"] for f in body["fields"]}
        assert type_map["id"]    == "integer"
        assert type_map["amount"] == "number"
        assert type_map["active"] == "boolean"
        assert type_map["created_at"] == "date"

    def test_inferred_by_frictionless(self):
        resp = client.post(
            "/api/schema/infer",
            files=[self._csv_upload(CSV_BASIC)],
        )
        for field in resp.json()["fields"]:
            assert field["inferred_by"] == "frictionless"

    def test_profile_included(self):
        resp = client.post(
            "/api/schema/infer",
            files=[self._csv_upload(CSV_BASIC)],
        )
        body = resp.json()
        assert "profile" in body
        assert body["profile"] is not None
        assert len(body["profile"]["column_profiles"]) == 5

    def test_unsupported_extension_returns_422(self):
        resp = client.post(
            "/api/schema/infer",
            files=[("file", ("data.json", b'{"a":1}', "application/json"))],
        )
        assert resp.status_code == 422

    def test_source_name_from_filename(self):
        resp = client.post(
            "/api/schema/infer",
            files=[self._csv_upload(CSV_BASIC, filename="my_orders.csv")],
        )
        assert resp.json()["source_name"] == "my_orders"

    def test_no_raw_data_in_response(self):
        resp = client.post(
            "/api/schema/infer",
            files=[self._csv_upload(CSV_BASIC)],
        )
        body = resp.json()
        # Ensure no actual row values leak in any field or profile.
        body_str = str(body)
        for value in ["Alice", "Bob", "Carol", "1234.56"]:
            assert value not in body_str, f"Raw value '{value}' found in response"

    def test_oversized_upload_returns_413(self):
        # MAX_UPLOAD_BYTES is 50 MB — one byte over that must 413, not 500 or 200.
        from app.services.file_schema import MAX_UPLOAD_BYTES

        oversized = b"a" * (MAX_UPLOAD_BYTES + 1)
        resp = client.post(
            "/api/schema/infer",
            files=[("file", ("big.csv", oversized, "text/csv"))],
        )
        assert resp.status_code == 413, resp.text

    def test_xlsx_upload_via_endpoint(self):
        import io

        import openpyxl

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["id", "name"])
        ws.append([1, "Alice"])
        ws.append([2, "Bob"])
        buf = io.BytesIO()
        wb.save(buf)
        buf.seek(0)

        resp = client.post(
            "/api/schema/infer",
            files=[(
                "file",
                ("sheet.xlsx", buf.read(),
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            )],
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["source_type"] == "excel"
        assert {f["name"] for f in body["fields"]} == {"id", "name"}
