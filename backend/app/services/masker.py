"""
Format-preserving masking for ambiguous column values.

Rules:
- Never return the original value.
- Preserve structural format (length, separators, character classes).
- Low-cardinality columns must NOT receive masked_examples — the set
  of masked values could still reveal the full category list.
"""
from __future__ import annotations

import re


# ─── Value maskers ────────────────────────────────────────────────────────────

def _mask_email(value: str) -> str:
    if "@" not in value:
        return "***@***.***"
    local, _, domain = value.partition("@")
    masked_local = (local[0] + "***") if local else "***"
    parts = domain.rsplit(".", 1)
    if len(parts) == 2:
        masked_domain = ("*" * min(3, len(parts[0]))) + "." + parts[1]
    else:
        masked_domain = "***"
    return f"{masked_local}@{masked_domain}"


def _mask_phone(value: str) -> str:
    return re.sub(r"\d", "*", value)


def _mask_date(value: str) -> str:
    return re.sub(r"\d", "X", value)


def _mask_generic(value: str) -> str:
    masked = ""
    for ch in value:
        if ch.isdigit():
            masked += "*"
        elif ch.isalpha():
            masked += "X"
        else:
            masked += ch
    return masked


# ─── Public API ───────────────────────────────────────────────────────────────

def mask_value(value: str, format_hint: str) -> str:
    """
    Mask a single value preserving its structural format.
    Returns a masked string; the original value never leaves this function.
    """
    if not value or not format_hint:
        return "***"
    hint = format_hint.lower()
    if "email" in hint:
        return _mask_email(value)
    if any(k in hint for k in ("phone", "tel", "celular", "móvil", "movil")):
        return _mask_phone(value)
    if any(k in hint for k in ("date", "fecha", "yyyy", "dd/mm", "mm/dd", "iso 8601")):
        return _mask_date(value)
    return _mask_generic(value)


# Minimum distinct count to allow masked examples.
# Below this threshold the masked values could reveal the full value set.
_MIN_DISTINCT_FOR_EXAMPLES = 10


def should_provide_examples(format_hint: str | None, distinct_count: int) -> bool:
    """
    Return True only when masked examples add signal about an ambiguous format
    and cardinality is high enough that masking does not reveal the value set.
    """
    if not format_hint:
        return False
    if distinct_count < _MIN_DISTINCT_FOR_EXAMPLES:
        return False
    hint = format_hint.lower()
    ambiguous = ("email", "phone", "tel", "celular", "fecha", "date", "yyyy",
                 "document", "alphanumeric", "numeric id")
    return any(kw in hint for kw in ambiguous)
