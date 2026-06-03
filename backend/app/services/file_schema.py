"""
Schema extraction from uploaded files (CSV, Excel) using Frictionless v5.

API contract:
  - infer_file_schema(path, source_name) → CanonicalSchema
  - Raw rows NEVER leave this module; only CanonicalSchema exits.

Frictionless v5 notes (verified on 5.19.0):
  - Sampling: Detector(sample_size=n) — parameter name confirmed in v5.
  - resource.sample → list of raw string lists (index 0 = headers, 1..n = data rows).
  - resource.schema.fields → list of Field(name, type, format).
  - resource.encoding → auto-detected encoding (uses chardet internally).
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from frictionless import Detector, Resource
from frictionless.exception import FrictionlessException

from app.schemas.canonical import CanonicalSchema, TableProfile
from app.schemas.context_schemas import ColumnProfile, ColumnStats
from app.services import profiler as profiler_svc
from app.services.adapters.frictionless_adapter import frictionless_schema_to_canonical

logger = logging.getLogger(__name__)

# How many rows frictionless reads for type inference and our profiling.
# Large enough to be representative; small enough for fast uploads.
_SAMPLE_SIZE = 1000


def infer_file_schema(path: str | Path, source_name: str) -> CanonicalSchema:
    """
    Infer schema and compute statistical profile from a CSV or Excel file.

    Steps:
      1. Open file with Frictionless using Detector(sample_size=_SAMPLE_SIZE).
      2. Collect resource.sample (raw string rows already in memory).
      3. Build CanonicalSchema via frictionless_adapter (structural layer).
      4. Compute null_pct and distinct_count per column from the sample
         using the existing profiler.compute_stats_from_memory() (statistical layer).
      5. Embed stats as TableProfile inside the returned CanonicalSchema.

    Never stores or returns raw row values.
    Raises ValueError for unreadable or structurally invalid files.
    """
    path = Path(path)
    source_type = "excel" if path.suffix.lower() in (".xlsx", ".xls") else "csv"

    try:
        resource = Resource(str(path), detector=Detector(sample_size=_SAMPLE_SIZE))
        resource.open()
    except FrictionlessException as exc:
        raise ValueError(f"No se pudo leer el archivo: {exc.error.message}") from exc

    try:
        fr_schema = resource.schema
        # resource.sample: list of lists; index 0 = header row, 1..n = data rows.
        raw_sample = resource.sample  # already in memory, no extra I/O

        # Build structural layer from Frictionless schema.
        canonical = frictionless_schema_to_canonical(fr_schema, source_name, source_type)

        # Build statistical layer from the raw sample.
        col_names  = [f.name for f in fr_schema.fields]
        data_rows  = _raw_to_profiler_rows(raw_sample, col_names)
        profile    = _compute_profile(col_names, data_rows)
        canonical.profile = profile

        return canonical

    except FrictionlessException as exc:
        raise ValueError(f"Error al inferir el esquema: {exc.error.message}") from exc
    finally:
        resource.close()


# ── Internal helpers ──────────────────────────────────────────────────────────

def _raw_to_profiler_rows(
    sample: list[list],
    col_names: list[str],
) -> list[list]:
    """
    Convert frictionless raw sample to the row format expected by the profiler.

    resource.sample[0] is the header row; data rows start at index 1.
    Empty strings are treated as nulls (None) to match the profiler convention.
    """
    header = sample[0] if sample else []
    col_indices = [header.index(name) for name in col_names if name in header]

    rows = []
    for raw_row in sample[1:]:
        row = []
        for idx in col_indices:
            val = raw_row[idx] if idx < len(raw_row) else None
            row.append(None if val == "" else val)
        rows.append(row)
    return rows


def _compute_profile(col_names: list[str], data_rows: list[list]) -> TableProfile:
    """
    Compute ColumnStats + ColumnProfile per column using the existing profiler.
    Stats are from the sample only — this is disclosed via distinct_count which
    may be lower than the full population's distinct count.
    """
    if not data_rows:
        profiles = [
            ColumnProfile(
                name=name,
                inferred_type="unknown",
                null_pct=0.0,
                distinct_count=0,
                leading_trailing_spaces_pct=0.0,
                casing_distribution={},
            )
            for name in col_names
        ]
        return TableProfile(column_profiles=profiles)

    stats        = profiler_svc.compute_stats_from_memory(col_names, data_rows)
    sample_rows  = data_rows[:20]
    profiles     = profiler_svc.profile_columns(col_names, stats, sample_rows)
    return TableProfile(
        row_count_estimate=len(data_rows),
        column_profiles=profiles,
    )
