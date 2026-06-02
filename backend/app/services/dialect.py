"""
Dialect layer for the profiler — one implementation per DB engine.

DialectProfiler (Protocol) defines four pure operations (no I/O):
  - quote()                 — identifier quoting; guards against reserved-word
                              conflicts and identifier injection
  - population_stats_sql()  — single-scan aggregate SELECT
  - primary_sample()        — preferred sampling strategy, with bias declared
  - fallback_sample()       — triggered when primary returns 0 rows (small table)

To add a new engine:
  1. Add a value to DbType in models/connection.py.
  2. Implement the four methods in a new class (see MySQLDialect sketch in
     the module docstring comment below as a template).
  3. Register it in _REGISTRY.
  4. Add it to the parametrized quoting test in tests/test_dialect.py.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple, Protocol, runtime_checkable

from app.models.connection import DbType


# ─── Sampling metadata ────────────────────────────────────────────────────────

class SamplingBias(str, Enum):
    row_level = "row_level"
    # Each row is equally likely to be selected.
    # Unbiased sample for format/casing inference.

    page_level = "page_level"
    # Selection operates at the storage-page or extent level.
    # Rows from the same page share insertion order: if data was loaded in
    # bulk batches (one date format or casing style per batch), the sample
    # can over-represent a single format. Acceptable for most profiling use
    # cases, but callers should log this bias for observability.


class SamplingResult(NamedTuple):
    """SQL + bias for a single sampling strategy."""
    sql:  str
    bias: SamplingBias


@dataclass(frozen=True)
class SampleResult:
    """
    Return type of db_connector.get_sample_rows().

    col_names and rows are the actual data; bias is operational metadata.
    Keep bias available for logging in the router/context_builder, but
    never pass it into format_model_context_for_prompt() or any prompt string.

    Frozen so callers cannot mutate rows after receiving them.
    """
    col_names: list[str]
    rows:      list[list]
    bias:      SamplingBias


# ─── Protocol ─────────────────────────────────────────────────────────────────

@runtime_checkable
class DialectProfiler(Protocol):
    """
    Dialect-specific SQL generation for the profiler.
    All methods are pure — they return strings or named tuples, never execute I/O.
    """

    def quote(self, identifier: str) -> str:
        """
        Return a safely-quoted identifier for this dialect.
        Inner quote characters are doubled per each dialect's escaping convention.
        """
        ...

    def population_stats_sql(self, qualified: str, col_names: list[str]) -> str:
        """
        Return a single SELECT that computes, per column:
          COUNT(*), SUM(IS NULL), COUNT(DISTINCT col), MIN/MAX string length.
        `qualified` is an already-quoted "schema"."table" string.
        Column aliases use positional names (__total__, __n0__, __d0__,
        __minl0__, __maxl0__, ...) so the caller can parse by position.
        """
        ...

    def primary_sample(self, qualified: str, limit: int) -> SamplingResult:
        """
        Preferred sampling strategy.
        `.bias` declares the selection granularity so callers can log it.
        """
        ...

    def fallback_sample(self, qualified: str, limit: int) -> SamplingResult:
        """
        Used when primary_sample returns 0 rows (table is too small for
        block-level sampling). Strategies here are O(N) or O(N log N)
        but are safe because N is known to be small at this point.
        """
        ...


# ─── PostgreSQL ───────────────────────────────────────────────────────────────

class PostgreSQLDialect:
    """
    PostgreSQL dialect for profiling.

    quote: double-quotes per SQL standard; inner " are doubled.

    population_stats: CHAR_LENGTH(col::TEXT) — character count, works on any
      type via the TEXT cast. Consistent with SQL Server's LEN(NVARCHAR) result.

    primary_sample: TABLESAMPLE SYSTEM(1) — page-level, O(pages sampled).
      Bias: rows from the same 8 KB heap page are contiguous in storage.
      If data was bulk-loaded by batch (one date format or casing per batch),
      the sample can be skewed. Acceptable for most format/casing inference.

    fallback_sample: ORDER BY RANDOM() LIMIT n — row-level, O(N log N).
      Safe here because we only reach fallback when SYSTEM(1) returned 0 rows,
      guaranteeing the table is small enough that O(N) is not a concern.
    """

    def quote(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def population_stats_sql(self, qualified: str, col_names: list[str]) -> str:
        exprs = ["COUNT(*) AS __total__"]
        for i, col in enumerate(col_names):
            q = self.quote(col)
            exprs.extend([
                f"SUM(CASE WHEN {q} IS NULL THEN 1 ELSE 0 END) AS __n{i}__",
                f"COUNT(DISTINCT {q}) AS __d{i}__",
                f"MIN(CHAR_LENGTH({q}::TEXT)) AS __minl{i}__",
                f"MAX(CHAR_LENGTH({q}::TEXT)) AS __maxl{i}__",
            ])
        return f"SELECT {', '.join(exprs)} FROM {qualified}"

    def primary_sample(self, qualified: str, limit: int) -> SamplingResult:
        return SamplingResult(
            sql=f"SELECT * FROM {qualified} TABLESAMPLE SYSTEM(1) LIMIT {limit}",
            bias=SamplingBias.page_level,
        )

    def fallback_sample(self, qualified: str, limit: int) -> SamplingResult:
        return SamplingResult(
            sql=f"SELECT * FROM {qualified} ORDER BY RANDOM() LIMIT {limit}",
            bias=SamplingBias.row_level,
        )


# ─── SQL Server ───────────────────────────────────────────────────────────────

class SQLServerDialect:
    """
    SQL Server dialect for profiling.

    quote: bracket-quoting per T-SQL convention; inner ] are doubled.

    population_stats: LEN(CAST(col AS NVARCHAR(MAX))) — character count.
      LEN() on NVARCHAR returns character count (not bytes), matching PostgreSQL's
      CHAR_LENGTH. CAST is required because LEN() only accepts string types.

    primary_sample: TOP n … TABLESAMPLE (10 PERCENT) — page-level.
      SQL Server TABLESAMPLE operates at the 8 KB page level (not row level).
      TOP n caps the result in case 10% of a large table still exceeds `limit`.
      Same clustering bias applies as with PostgreSQL SYSTEM.

    fallback_sample: TOP n … ORDER BY NEWID() — row-level, O(N) sort.
      NEWID() generates a UUID per row, forcing a full sort pass. Safe only on
      small tables (same reasoning: we reach here only when TABLESAMPLE returned
      nothing, guaranteeing N is small).
    """

    def quote(self, identifier: str) -> str:
        return '[' + identifier.replace(']', ']]') + ']'

    def population_stats_sql(self, qualified: str, col_names: list[str]) -> str:
        exprs = ["COUNT(*) AS __total__"]
        for i, col in enumerate(col_names):
            q = self.quote(col)
            exprs.extend([
                f"SUM(CASE WHEN {q} IS NULL THEN 1 ELSE 0 END) AS __n{i}__",
                f"COUNT(DISTINCT {q}) AS __d{i}__",
                f"MIN(LEN(CAST({q} AS NVARCHAR(MAX)))) AS __minl{i}__",
                f"MAX(LEN(CAST({q} AS NVARCHAR(MAX)))) AS __maxl{i}__",
            ])
        return f"SELECT {', '.join(exprs)} FROM {qualified}"

    def primary_sample(self, qualified: str, limit: int) -> SamplingResult:
        return SamplingResult(
            sql=f"SELECT TOP {limit} * FROM {qualified} TABLESAMPLE (10 PERCENT)",
            bias=SamplingBias.page_level,
        )

    def fallback_sample(self, qualified: str, limit: int) -> SamplingResult:
        return SamplingResult(
            sql=f"SELECT TOP {limit} * FROM {qualified} ORDER BY NEWID()",
            bias=SamplingBias.row_level,
        )


# ─── Fake (tests only) ────────────────────────────────────────────────────────

class FakeDialect:
    """
    In-memory dialect for unit tests. Never executes SQL.

    quote() uses generic double-quotes so quoting tests can assert on the format.
    population_stats_sql() returns a no-op SELECT; tests drive profiling directly
    through profile_columns() without going through fetch_column_stats().
    """

    def quote(self, identifier: str) -> str:
        return '"' + identifier.replace('"', '""') + '"'

    def population_stats_sql(self, qualified: str, col_names: list[str]) -> str:
        return "SELECT 1"

    def primary_sample(self, qualified: str, limit: int) -> SamplingResult:
        return SamplingResult(
            sql=f"SELECT * FROM {qualified} LIMIT {limit}",
            bias=SamplingBias.row_level,
        )

    def fallback_sample(self, qualified: str, limit: int) -> SamplingResult:
        return SamplingResult(
            sql=f"SELECT * FROM {qualified} LIMIT {limit}",
            bias=SamplingBias.row_level,
        )


# ─── Registry / factory ───────────────────────────────────────────────────────

# Instances are stateless and immutable — safe to share across requests.
_REGISTRY: dict[DbType, DialectProfiler] = {
    DbType.postgresql: PostgreSQLDialect(),
    DbType.sqlserver:  SQLServerDialect(),
}


def get_dialect(db_type: DbType) -> DialectProfiler:
    """
    Return the DialectProfiler registered for db_type.

    Raises NotImplementedError if no dialect is registered, forcing an explicit
    registration step whenever a new engine is added to DbType.
    """
    try:
        return _REGISTRY[db_type]
    except KeyError:
        raise NotImplementedError(
            f"No DialectProfiler registered for {db_type!r}. "
            "Implement the dialect and add it to dialect._REGISTRY."
        )
