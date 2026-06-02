"""
Unit tests for the profiler service.

No database or LLM required — all tests use synthetic in-memory data.
Run with: pytest tests/test_profiler.py -v
"""
from __future__ import annotations

import pytest

from app.schemas.context_schemas import ColumnStats
from app.services.profiler import (
    compute_stats_from_memory,
    profile_columns,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _stats(total=100, nulls=0, distinct=50, min_l=None, max_l=None) -> ColumnStats:
    return ColumnStats(
        total_count=total,
        null_count=nulls,
        distinct_count=distinct,
        min_length=min_l,
        max_length=max_l,
    )


def _profile(col_values: list[str], total=100, nulls=0, distinct=None):
    """Helper: build one ColumnProfile from a list of sample values."""
    n = len(col_values)
    d = distinct if distinct is not None else len(set(col_values))
    stats = {"col": _stats(total=total, nulls=nulls, distinct=d, min_l=min(len(v) for v in col_values) if col_values else None, max_l=max(len(v) for v in col_values) if col_values else None)}
    rows  = [[v] for v in col_values]
    return profile_columns(["col"], stats, rows)[0]


# ─── null_pct comes from SQL stats, not sample ────────────────────────────────

def test_null_pct_uses_stats_not_sample():
    stats = {"email": _stats(total=1000, nulls=200)}
    rows  = [["alice@test.com"]] * 10   # 0 nulls in sample
    p     = profile_columns(["email"], stats, rows)[0]
    assert p.null_pct == pytest.approx(0.2, abs=1e-3)


def test_null_pct_zero_rows():
    stats = {"col": _stats(total=0, nulls=0)}
    p     = profile_columns(["col"], stats, [])[0]
    assert p.null_pct == 0.0


# ─── distinct_count comes from SQL stats ─────────────────────────────────────

def test_distinct_count_uses_stats():
    stats = {"col": _stats(total=1000, distinct=42)}
    rows  = [["A"], ["B"], ["A"]]    # only 2 distinct in sample
    p     = profile_columns(["col"], stats, rows)[0]
    assert p.distinct_count == 42    # SQL aggregate wins


# ─── No raw values survive in the profile output ─────────────────────────────

def test_no_raw_values_in_profile_email():
    raw = ["john.doe@corp.com", "jane@corp.com", "alice@domain.org"]
    p   = _profile(raw, total=1000, distinct=1000)
    for v in raw:
        assert v not in (p.format_hint or ""), "Raw email in format_hint"
        for ex in (p.masked_examples or []):
            assert v not in ex, "Unmasked email in masked_examples"


def test_no_raw_values_in_profile_phone():
    raw = ["555-1234", "555-5678", "555-9012"]
    p   = _profile(raw, total=500, distinct=500)
    for v in raw:
        assert v not in (p.format_hint or "")
        for ex in (p.masked_examples or []):
            assert v not in ex


# ─── casing_distribution ─────────────────────────────────────────────────────

def test_casing_all_upper():
    p = _profile(["JOHN", "JANE", "ALICE", "BOB"])
    assert p.casing_distribution.get("upper", 0) == pytest.approx(1.0)


def test_casing_all_lower():
    p = _profile(["john", "jane", "alice"])
    assert p.casing_distribution.get("lower", 0) == pytest.approx(1.0)


def test_casing_mixed():
    vals = ["UPPER", "lower", "Title", "mIxEd"]
    p    = _profile(vals)
    total = sum(p.casing_distribution.values())
    assert total == pytest.approx(1.0, abs=0.01)


# ─── leading/trailing spaces ─────────────────────────────────────────────────

def test_spaces_pct_detection():
    rows = [["  hello"], ["world"], ["  end  "]]  # 2 of 3 have spaces
    stats = {"col": _stats(total=3)}
    p = profile_columns(["col"], stats, rows)[0]
    assert p.leading_trailing_spaces_pct == pytest.approx(2 / 3, abs=0.01)


# ─── format_hint ─────────────────────────────────────────────────────────────

def test_date_yyyy_mm_dd():
    p = _profile(["2024-01-15", "2024-02-20", "2024-03-31"], distinct=365)
    assert p.inferred_type == "date"
    assert p.format_hint == "YYYY-MM-DD"


def test_email_hint():
    p = _profile(["alice@test.com", "bob@test.com", "carol@test.com"], total=1000, distinct=1000)
    assert p.format_hint == "email"


def test_enum_like_descriptor_no_values_listed():
    raw = ["active", "inactive", "pending"]
    p   = _profile(raw, total=1000, distinct=3)
    # format_hint should describe cardinality, NOT list the actual values
    assert p.format_hint is not None
    assert "active"   not in p.format_hint
    assert "inactive" not in p.format_hint
    assert "pending"  not in p.format_hint
    assert "3" in p.format_hint   # cardinality is OK


# ─── masked_examples: only when cardinality is high enough ───────────────────

def test_no_masked_examples_low_cardinality():
    p = _profile(["yes", "no", "yes", "no"], total=100, distinct=2)
    assert p.masked_examples is None, "Low cardinality must not produce masked_examples"


def test_masked_examples_email_high_cardinality():
    raw = ["user1@corp.com", "user2@corp.com", "user3@corp.com"]
    p   = _profile(raw, total=1000, distinct=1000)
    if p.masked_examples:
        for ex in p.masked_examples:
            for v in raw:
                assert v not in ex, "Unmasked value in masked_examples"


# ─── compute_stats_from_memory ────────────────────────────────────────────────

def test_memory_stats_null_count():
    rows  = [["A"], [None], ["B"], [""], ["C"]]
    stats = compute_stats_from_memory(["col"], rows)
    assert stats["col"].null_count    == 2    # None and ""
    assert stats["col"].total_count   == 5


def test_memory_stats_distinct():
    rows  = [["A"], ["B"], ["A"], ["C"]]
    stats = compute_stats_from_memory(["col"], rows)
    assert stats["col"].distinct_count == 3


def test_memory_stats_min_max_length():
    rows  = [["hi"], ["hello"], ["bye"]]
    stats = compute_stats_from_memory(["col"], rows)
    assert stats["col"].min_length == 2
    assert stats["col"].max_length == 5


def test_memory_stats_multi_column():
    rows  = [["A", "1"], ["B", "22"], ["C", "333"]]
    stats = compute_stats_from_memory(["name", "code"], rows)
    assert stats["name"].distinct_count == 3
    assert stats["code"].max_length     == 3


# ─── type inference ───────────────────────────────────────────────────────────

def test_infer_int():
    p = _profile(["1", "2", "3", "42", "100"])
    assert p.inferred_type == "int"


def test_infer_float():
    p = _profile(["1.5", "2.7", "3.14", "0.001"])
    assert p.inferred_type == "float"


def test_infer_bool():
    p = _profile(["true", "false", "true", "true", "false"])
    assert p.inferred_type == "bool"


def test_infer_unknown_for_mixed():
    p = _profile(["hello", "42", "true", "2024-01-01", "world"])
    assert p.inferred_type in ("string", "unknown")
