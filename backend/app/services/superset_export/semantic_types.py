"""Clasificacion semantica de columnas por nombre + valor de muestra — decide si una
columna es usable como dimension/metrica, su tipo semantico (id/boolean/date/category/
metric) y su tipo SQL de dataset. Port 1:1 de isUsableColumn/inferSemanticType/inferType
en frontend/src/utils/supersetExport.js.

Nota de porting JS->Python: `typeof sample === "number"` en JS separa numero de boolean
de forma nativa. En Python `bool` es subclase de `int`, asi que el orden de los checks
de tipo se invierte (bool antes que int/float) para preservar el mismo resultado."""

from __future__ import annotations

import re
from typing import Any

from app.services.superset_export.constants import (
    AUDIT_KEYWORDS,
    CAT_PREFIXES,
    DATE_KW,
    METRIC_KW,
)

_NOTFOUND = object()

_DATE_LIKE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")


def _first_sample(values: list) -> Any:
    """Primer valor no nulo/vacio de la lista, o el sentinel _NOTFOUND si no hay ninguno
    (equivalente a que Array.prototype.find devuelva undefined en el JS original)."""
    for v in values:
        if v is not None and v != "":
            return v
    return _NOTFOUND


def is_usable_column(name: str | None) -> bool:
    if not name:
        return False
    upper = str(name).upper()
    if upper.startswith("SK_"):
        return False
    if upper.startswith("FK_"):
        return False
    if upper.startswith("ID_"):
        return False
    if upper.startswith("COD_"):
        return False
    if upper.startswith("BK_"):
        return False
    if upper == "ID" or upper.endswith("_ID"):
        return False
    # Identificadores de negocio LATAM — no aportan valor analitico como dimension
    if upper == "RUT":
        return False
    if upper == "CI":
        return False
    if upper == "DNI":
        return False
    if upper == "LEGAJO":
        return False
    if upper == "CODIGO":
        return False
    if upper == "CODE":
        return False
    if upper in ("NRO", "NUMERO"):
        return False
    if upper.startswith("NRO_"):
        return False
    if upper.startswith("NUM_"):
        return False
    if upper.startswith("COD") and len(upper) <= 6:
        return False
    return True


def infer_semantic_type(name: str, values: list) -> str:
    u = str(name).upper()
    sample = _first_sample(values)

    # Surrogate / foreign / natural keys → exclude
    if u == "ID" or u.endswith("_ID") or u.startswith("SK_") or u.startswith("FK_") or u.startswith("ID_"):
        return "id"

    if isinstance(sample, bool):
        return "boolean"

    # Audit columns → treat as non-usable
    if any(k in u for k in AUDIT_KEYWORDS):
        return "id"

    # Date detection
    if any(k in u for k in DATE_KW):
        return "date"
    if isinstance(sample, str) and _DATE_LIKE_RE.match(sample):
        return "date"

    # Category-prefix indicators (TIPO_VENTA should be category, not metric even if
    # VENTA is a metric keyword)
    if any(u == k or u.startswith(k + "_") for k in CAT_PREFIXES):
        return "category"

    # Metric detection — keywords cover the common DWH vocabulary
    if isinstance(sample, (int, float)) and not isinstance(sample, bool) and any(k in u for k in METRIC_KW):
        return "metric"
    # Name-only metric inference for KTR-parsed columns where values are all null
    if sample is _NOTFOUND and any(k in u for k in METRIC_KW):
        return "metric"
    if isinstance(sample, (int, float)) and not isinstance(sample, bool):
        return "metric"

    return "category"


def infer_type(values: list) -> str:
    sample = _first_sample(values)
    if sample is _NOTFOUND:
        return "VARCHAR"
    if isinstance(sample, bool):
        return "BOOLEAN"
    if isinstance(sample, int):
        return "INTEGER"
    if isinstance(sample, float):
        return "DOUBLE PRECISION"
    return "VARCHAR"
