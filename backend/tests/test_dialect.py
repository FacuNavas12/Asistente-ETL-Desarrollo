"""
Tests for the dialect layer (app/services/dialect.py).

No database or LLM required — all tests are pure unit tests.
Run with: pytest tests/test_dialect.py -v
"""
from __future__ import annotations

import pytest

from app.models.connection import DbType
from app.schemas.context_schemas import ColumnStats
from app.services.db_connector import _quote_identifier
from app.services.dialect import (
    FakeDialect,
    PostgreSQLDialect,
    SQLServerDialect,
    SamplingBias,
    get_dialect,
)
from app.services.profiler import profile_columns


# ─── All registered engines (parametrize over these everywhere possible) ──────

_ALL_ENGINES = [
    pytest.param(DbType.postgresql, PostgreSQLDialect, id="postgresql"),
    pytest.param(DbType.sqlserver,  SQLServerDialect,  id="sqlserver"),
]


# ─── 1. Registry selection ────────────────────────────────────────────────────

@pytest.mark.parametrize("db_type, expected_cls", _ALL_ENGINES)
def test_get_dialect_returns_correct_implementation(db_type, expected_cls):
    assert isinstance(get_dialect(db_type), expected_cls)


def test_get_dialect_unknown_engine_raises():
    with pytest.raises(NotImplementedError, match="No DialectProfiler registered"):
        get_dialect("oracle")  # type: ignore[arg-type]


# ─── 2. population_stats_sql structure ───────────────────────────────────────

@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
def test_stats_sql_contains_count_star(db_type, _):
    sql = get_dialect(db_type).population_stats_sql('"s"."t"', ["col1"])
    assert "COUNT(*)" in sql.upper()


@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
def test_stats_sql_contains_null_sum(db_type, _):
    sql = get_dialect(db_type).population_stats_sql('"s"."t"', ["col1"])
    assert "SUM(CASE WHEN" in sql.upper()
    assert "IS NULL" in sql.upper()


@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
def test_stats_sql_contains_count_distinct(db_type, _):
    sql = get_dialect(db_type).population_stats_sql('"s"."t"', ["col1"])
    assert "COUNT(DISTINCT" in sql.upper()


def test_stats_sql_pg_uses_char_length():
    sql = get_dialect(DbType.postgresql).population_stats_sql('"s"."t"', ["col1"])
    assert "CHAR_LENGTH" in sql.upper()
    assert "LEN(" not in sql.upper()


def test_stats_sql_mssql_uses_len_cast():
    sql = get_dialect(DbType.sqlserver).population_stats_sql('"s"."t"', ["col1"])
    assert "LEN(" in sql.upper()
    assert "NVARCHAR" in sql.upper()


@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
def test_stats_sql_four_exprs_per_column(db_type, _):
    # Parser in fetch_column_stats relies on base = 1 + i*4.
    # Verify that for N cols there are 1 + N*4 alias markers in the SQL.
    cols = ["a", "b", "c"]
    sql  = get_dialect(db_type).population_stats_sql('"s"."t"', cols)
    expected_aliases = ["__total__"] + [
        f"__{pfx}{i}__"
        for i in range(len(cols))
        for pfx in ("n", "d", "minl", "maxl")
    ]
    for alias in expected_aliases:
        assert alias in sql, f"Expected alias '{alias}' missing from SQL"


@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
def test_stats_sql_contains_qualified_table(db_type, _):
    qualified = '"myschema"."mytable"'
    sql = get_dialect(db_type).population_stats_sql(qualified, ["id"])
    assert qualified in sql


# ─── 3. Sampling strategies & bias declaration ────────────────────────────────

@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
def test_primary_sample_returns_known_bias(db_type, _):
    result = get_dialect(db_type).primary_sample('"s"."t"', 20)
    assert result.bias in SamplingBias


@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
def test_fallback_sample_returns_known_bias(db_type, _):
    result = get_dialect(db_type).fallback_sample('"s"."t"', 20)
    assert result.bias in SamplingBias


def test_pg_primary_is_page_level():
    assert get_dialect(DbType.postgresql).primary_sample('"s"."t"', 20).bias is SamplingBias.page_level


def test_pg_fallback_is_row_level():
    assert get_dialect(DbType.postgresql).fallback_sample('"s"."t"', 20).bias is SamplingBias.row_level


def test_mssql_primary_is_page_level():
    assert get_dialect(DbType.sqlserver).primary_sample('"s"."t"', 20).bias is SamplingBias.page_level


def test_mssql_fallback_is_row_level():
    assert get_dialect(DbType.sqlserver).fallback_sample('"s"."t"', 20).bias is SamplingBias.row_level


@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
def test_primary_sample_sql_is_nonempty_string(db_type, _):
    sql = get_dialect(db_type).primary_sample('"s"."t"', 10).sql
    assert isinstance(sql, str) and sql.strip()


@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
def test_sample_sql_embeds_limit(db_type, _):
    limit = 17
    primary  = get_dialect(db_type).primary_sample('"s"."t"', limit).sql
    fallback = get_dialect(db_type).fallback_sample('"s"."t"', limit).sql
    assert str(limit) in primary,  f"limit {limit} not in primary SQL"
    assert str(limit) in fallback, f"limit {limit} not in fallback SQL"


# ─── 4. Quoting invariant: _quote_identifier == get_dialect().quote() ─────────
#
# This test pins the contract that both quoting paths stay in sync.
# If a new engine is added to DbType without updating one of the two paths,
# this parametrized test will catch the divergence.

_QUOTE_CASES = [
    "simple",
    "with space",
    'with"double',
    "with]bracket",
    "with`backtick",
    "SELECT",          # reserved word
    "order",           # reserved word (lowercase)
]


@pytest.mark.parametrize("db_type, _", _ALL_ENGINES)
@pytest.mark.parametrize("identifier", _QUOTE_CASES)
def test_quoting_invariant(db_type, _, identifier):
    legacy  = _quote_identifier(identifier, db_type)
    dialect = get_dialect(db_type).quote(identifier)
    assert legacy == dialect, (
        f"Quoting diverged for {db_type}/{identifier!r}: "
        f"_quote_identifier={legacy!r}, dialect.quote={dialect!r}"
    )


# ─── 5. Sample transitivity: raw values never survive in ColumnProfile ─────────
#
# Uses FakeDialect so no DB is needed. Drives profile_columns() directly,
# which is the only function that consumes raw rows.

_RAW_EMAILS   = ["john.doe@acme.com", "jane.smith@corp.com", "carol@domain.org"]
_RAW_PHONES   = ["555-1234", "+1-800-555-0000", "0011-49-30-12345"]
_RAW_INTEGERS = ["100", "200", "300"]


def _run_profile(raw_values: list[str], distinct: int = 1000, total: int = 5000):
    """Helper: build ColumnProfile from raw sample values via profile_columns()."""
    stats = {
        "col": ColumnStats(
            total_count=total,
            null_count=0,
            distinct_count=distinct,
            min_length=min(len(v) for v in raw_values),
            max_length=max(len(v) for v in raw_values),
        )
    }
    rows = [[v] for v in raw_values]
    return profile_columns(["col"], stats, rows)[0]


def _assert_no_raw_value(profile, raw_values: list[str], label: str):
    """Assert that no raw value appears verbatim in any ColumnProfile field."""
    for raw in raw_values:
        assert raw not in (profile.format_hint or ""), (
            f"[{label}] raw value '{raw}' leaked into format_hint"
        )
        for ex in (profile.masked_examples or []):
            assert raw not in ex, (
                f"[{label}] raw value '{raw}' leaked into masked_examples"
            )
        # Casing keys are category names, not values — just check values aren't there.
        assert raw not in str(profile.casing_distribution), (
            f"[{label}] raw value '{raw}' leaked into casing_distribution"
        )


def test_transient_email_values_not_in_profile():
    profile = _run_profile(_RAW_EMAILS)
    _assert_no_raw_value(profile, _RAW_EMAILS, "email")


def test_transient_phone_values_not_in_profile():
    profile = _run_profile(_RAW_PHONES)
    _assert_no_raw_value(profile, _RAW_PHONES, "phone")


def test_transient_integer_values_not_in_profile():
    profile = _run_profile(_RAW_INTEGERS, distinct=300)
    _assert_no_raw_value(profile, _RAW_INTEGERS, "integer")


def test_transient_enum_like_values_not_in_profile():
    raw = ["active", "inactive", "pending", "suspended"]
    profile = _run_profile(raw, distinct=4, total=10000)
    _assert_no_raw_value(profile, raw, "enum")
    # format_hint may say "enum-like (4 distinct values)" — the count is fine,
    # but none of the actual category labels should appear.
    for val in raw:
        assert val not in (profile.format_hint or ""), (
            f"enum category '{val}' should not appear in format_hint"
        )


def test_fake_dialect_satisfies_protocol():
    from app.services.dialect import DialectProfiler
    assert isinstance(FakeDialect(), DialectProfiler)


def test_fake_dialect_primary_is_row_level():
    assert FakeDialect().primary_sample('"s"."t"', 20).bias is SamplingBias.row_level
