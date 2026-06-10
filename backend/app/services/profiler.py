"""
Two-level profiling:
  Level 1 — population stats via SQL aggregates pushed to the source
             (null_pct, distinct_count, min/max length).
             For CSV/Excel: computed from all in-memory rows.
  Level 2 — sample-based analysis using ≤20 rows
             (casing_distribution, leading_trailing_spaces_pct,
              format_hint, masked_examples).

Raw sample rows never leave this module. Only ColumnProfile objects exit.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from sqlalchemy import text

from app.models.connection import Connection
from app.schemas.context_schemas import ColumnProfile, ColumnStats
from app.services import masker as masker_svc
from app.services.db_connector import _validate_table_exists, build_engine
from app.services.dialect import get_dialect

logger = logging.getLogger(__name__)


# ─── Level 1: Population stats via SQL (DB sources) ──────────────────────────

def fetch_db_column_stats(
    conn: Connection,
    schema: str,
    table: str,
    col_names: list[str],
) -> dict[str, ColumnStats]:
    """
    Single table-scan query for population-level stats per column.
    Uses COUNT(*), SUM(IS NULL), COUNT(DISTINCT), MIN/MAX(LENGTH) — no row fetch.
    Returns an empty ColumnStats on any failure rather than raising.
    """
    dialect   = get_dialect(conn.db_type)
    engine    = build_engine(conn, read_only=True)
    qualified = f"{dialect.quote(schema)}.{dialect.quote(table)}"
    sql       = dialect.population_stats_sql(qualified, col_names)
    try:
        with engine.connect() as c:
            row = c.execute(text(sql)).fetchone()
        if row is None or row[0] is None:
            return {col: ColumnStats(total_count=0, null_count=0, distinct_count=0)
                    for col in col_names}

        total = int(row[0])
        result: dict[str, ColumnStats] = {}
        for i, col in enumerate(col_names):
            base = 1 + i * 4      # 4 expressions per column after __total__
            null_count  = int(row[base])     if row[base]     is not None else 0
            distinct    = int(row[base + 1]) if row[base + 1] is not None else 0
            min_len     = int(row[base + 2]) if row[base + 2] is not None else None
            max_len     = int(row[base + 3]) if row[base + 3] is not None else None
            result[col] = ColumnStats(
                total_count=total,
                null_count=null_count,
                distinct_count=distinct,
                min_length=min_len,
                max_length=max_len,
            )
        return result
    except Exception as exc:
        logger.warning("fetch_db_column_stats failed for %s.%s: %s", schema, table, exc)
        return {col: ColumnStats(total_count=0, null_count=0, distinct_count=0)
                for col in col_names}
    finally:
        engine.dispose()


# ─── Level 1: Population stats from memory (CSV/Excel sources) ───────────────

def compute_file_column_stats(
    col_names: list[str],
    all_rows: list[list],
) -> dict[str, ColumnStats]:
    """Exact population stats from all in-memory rows. Used for CSV/Excel."""
    total = len(all_rows)
    result: dict[str, ColumnStats] = {}
    for i, name in enumerate(col_names):
        col_vals = [row[i] for row in all_rows if i < len(row)]
        null_count = sum(1 for v in col_vals if v is None or v == "")
        str_vals   = [str(v) for v in col_vals if v is not None and v != ""]
        distinct   = len(set(str_vals))
        min_len    = min((len(v) for v in str_vals), default=None)
        max_len    = max((len(v) for v in str_vals), default=None)
        result[name] = ColumnStats(
            total_count=total,
            null_count=null_count,
            distinct_count=distinct,
            min_length=min_len,
            max_length=max_len,
        )
    return result


# ─── Level 2: Sample-based analysis helpers ───────────────────────────────────

_DATE_PATTERNS: list[tuple[str, str]] = [
    (r"^\d{4}-\d{2}-\d{2}T",    "ISO 8601 datetime"),
    (r"^\d{4}-\d{2}-\d{2}$",    "YYYY-MM-DD"),
    (r"^\d{2}/\d{2}/\d{4}$",    "DD/MM/YYYY or MM/DD/YYYY"),
    (r"^\d{4}/\d{2}/\d{2}$",    "YYYY/MM/DD"),
    (r"^\d{2}-\d{2}-\d{4}$",    "DD-MM-YYYY"),
]

_BOOL_VALS = frozenset({"true", "false", "yes", "no", "1", "0", "si", "sí"})

_THRESHOLD = 0.7   # fraction of sample agreeing on a type / format


def _infer_type(values: list[str]) -> str:
    if not values:
        return "unknown"
    counts: dict[str, int] = {"bool": 0, "date": 0, "int": 0, "float": 0}
    for v in values:
        s = v.strip()
        if s.lower() in _BOOL_VALS:
            counts["bool"] += 1
        elif any(re.match(p, s) for p, _ in _DATE_PATTERNS):
            counts["date"] += 1
        else:
            try:
                int(s)
                counts["int"] += 1
            except ValueError:
                try:
                    float(s.replace(",", "."))
                    counts["float"] += 1
                except ValueError:
                    pass
    n = len(values)
    for t in ("bool", "date", "int", "float"):
        if counts[t] / n >= _THRESHOLD:
            return t
    return "string"


def _compute_casing(values: list[str]) -> dict[str, float]:
    if not values:
        return {}
    counts: dict[str, int] = {"upper": 0, "lower": 0, "title": 0, "mixed": 0}
    for v in values:
        alpha = "".join(c for c in v if c.isalpha())
        if not alpha:
            continue
        if alpha == alpha.upper():
            counts["upper"] += 1
        elif alpha == alpha.lower():
            counts["lower"] += 1
        elif alpha == alpha.title():
            counts["title"] += 1
        else:
            counts["mixed"] += 1
    total = sum(counts.values())
    if total == 0:
        return {}
    return {k: round(v / total, 3) for k, v in counts.items() if v > 0}


def _compute_spaces_pct(values: list[str]) -> float:
    if not values:
        return 0.0
    with_spaces = sum(1 for v in values if v != v.strip())
    return round(with_spaces / len(values), 3)


def _infer_format_hint(
    values: list[str],
    inferred_type: str,
    distinct_count: int,
) -> Optional[str]:
    if not values:
        return None
    n = len(values)

    if inferred_type == "date":
        for pattern, label in _DATE_PATTERNS:
            if sum(1 for v in values if re.match(pattern, v.strip())) / n >= _THRESHOLD:
                return label
        return "date (format unclear)"

    if inferred_type == "string":
        email_pat = r"^[\w.+\-]+@[\w\-]+\.\w{2,}$"
        if sum(1 for v in values if re.match(email_pat, v.strip())) / n >= _THRESHOLD:
            return "email"

        phone_pat = r"^[\+\d][\d\s\-\(\)\.]{6,}$"
        if sum(1 for v in values if re.match(phone_pat, v.strip())) / n >= _THRESHOLD:
            return "phone number"

        # Enum-like: describe cardinality without listing values.
        if distinct_count <= 20:
            return f"enum-like ({distinct_count} distinct values)"

        if sum(1 for v in values if re.fullmatch(r"\d+", v.strip())) / n >= 0.8:
            return "numeric ID"

        if sum(1 for v in values if re.fullmatch(r"[A-Z0-9\-_]{3,20}", v.strip())) / n >= 0.8:
            return "alphanumeric code (e.g., SKU, document number)"

    return None


# ─── Main entry point ─────────────────────────────────────────────────────────

def profile_columns(
    col_names: list[str],
    stats: dict[str, ColumnStats],
    sample_rows: list[list],
) -> list[ColumnProfile]:
    """
    Build one ColumnProfile per column.

    stats       — population-level (from SQL aggregates or memory scan)
    sample_rows — ≤20 rows, used ONLY for casing / spaces / format_hint / masking.

    Raw sample values never exit this function.
    """
    profiles: list[ColumnProfile] = []

    for col_idx, name in enumerate(col_names):
        col_stats = stats.get(
            name,
            ColumnStats(total_count=0, null_count=0, distinct_count=0),
        )

        # Extract string values for this column from sample rows.
        sample_raw: list[str] = []
        for row in sample_rows:
            if col_idx < len(row) and row[col_idx] is not None:
                sample_raw.append(str(row[col_idx]))

        sample_stripped = [v.strip() for v in sample_raw if v.strip()]

        null_pct = (
            col_stats.null_count / col_stats.total_count
            if col_stats.total_count > 0 else 0.0
        )

        inferred_type = _infer_type(sample_stripped)
        casing        = _compute_casing(sample_stripped)
        spaces_pct    = _compute_spaces_pct(sample_raw)
        format_hint   = _infer_format_hint(
            sample_stripped, inferred_type, col_stats.distinct_count
        )

        masked_examples: Optional[list[str]] = None
        if masker_svc.should_provide_examples(format_hint, col_stats.distinct_count):
            raw_ex  = sample_stripped[:3]
            masked  = [masker_svc.mask_value(v, format_hint) for v in raw_ex]  # type: ignore[arg-type]
            masked_examples = [m for m in masked if m] or None

        profiles.append(ColumnProfile(
            name=name,
            inferred_type=inferred_type,
            null_pct=round(null_pct, 3),
            distinct_count=col_stats.distinct_count,
            leading_trailing_spaces_pct=round(spaces_pct, 3),
            casing_distribution=casing,
            min_length=col_stats.min_length,
            max_length=col_stats.max_length,
            format_hint=format_hint,
            masked_examples=masked_examples,
        ))

    return profiles
