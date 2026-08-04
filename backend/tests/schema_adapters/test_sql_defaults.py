"""Tests de app.services.sql_defaults — clasificación general de DEFAULT: literal vs función."""
from __future__ import annotations

import pytest

from app.services.sql_defaults import classify_default_expr, looks_like_sql_function


class TestLooksLikeSqlFunction:
    @pytest.mark.parametrize("expr", [
        "NOW()",
        "now()",
        "CURRENT_TIMESTAMP",
        "current_timestamp",
        "CURRENT_TIMESTAMP()",
        "LOCALTIMESTAMP",
        "gen_random_uuid()",
        "nextval('seq')",
        "nextval('public.seq'::regclass)",
        "getdate()",
        "(getdate())",          # forma cruda de SQL Server (column_default con parens extra)
        "uuid_generate_v4()",
    ])
    def test_function_defaults_detected(self, expr):
        assert looks_like_sql_function(expr) is True

    @pytest.mark.parametrize("expr", [
        "'ACTIVO'",
        "'ACTIVO'::character varying",
        "0",
        "((0))",
        "TRUE",
        "FALSE",
        "1000",
        None,
        "",
        "   ",
    ])
    def test_literal_defaults_not_detected(self, expr):
        assert looks_like_sql_function(expr) is False


class TestClassifyDefaultExpr:
    def test_function_expr_classified_as_function(self):
        assert classify_default_expr("NOW()") == "function"

    def test_literal_expr_classified_as_literal(self):
        assert classify_default_expr("'ACTIVO'") == "literal"

    def test_none_or_empty_classified_as_none(self):
        assert classify_default_expr(None) is None
        assert classify_default_expr("") is None
