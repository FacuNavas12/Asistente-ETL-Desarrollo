"""Fuente única de verdad por tipo de step: alias de claves de config y
semántica de flujo de campos (produce/consume/narrows). Un mismo defecto
apareció tres veces con distinta cara (tipo no registrado degradado a Dummy,
semántica de campo no modelada en el validador, validador leyendo una clave
que el config no trae por drift camelCase/snake_case) porque cada capa
(emisor XML, validador de grafo) reimplementaba por su cuenta qué claves leer
y qué campos produce/consume cada step. Este módulo centraliza eso:

  normalize_config()  — traduce alias de clave -> canónica (top-level y
                         anidada) UNA sola vez, antes de emitir y validar.
                         Los emisores en steps/*.py NO cambian: reciben el
                         config ya normalizado.
  STEP_CONTRACTS       — produces/consumes/required_keys por tipo, usado por
                         fields_validate.py en vez de tener su propia tabla
                         de semántica por tipo.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable

from app.services.ktr_builder.common import _yn

ProducerFn = Callable[[dict, "set[str] | None"], "set[str] | None"]
ConsumerFn = Callable[[dict], "set[str]"]


def parse_cfg(raw) -> dict:
    """Config puede llegar como dict (schema object) o string JSON (schema
    string) — normaliza siempre a dict. Usada por build.py y fields_validate.py
    para no reimplementar el mismo try/except JSON en cada módulo."""
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    return raw or {}


def _names(items, *keys: str) -> set[str]:
    """Extrae un set de nombres de una lista de items string|dict, probando
    `keys` en orden de preferencia por item dict."""
    out: set[str] = set()
    for it in items or []:
        if isinstance(it, str):
            out.add(it)
            continue
        if not isinstance(it, dict):
            continue
        for k in keys:
            v = it.get(k)
            if v:
                out.add(v)
                break
    return out - {"", None}


def _select_columns(sql: str) -> set[str] | None:
    """Extrae nombres de columna de un SELECT simple (sin subqueries). None si
    no se puede resolver con certeza (SELECT *, expresión no reconocida) —
    en ese caso el step se trata como fuente desconocida."""
    if not sql or not sql.strip():
        return None
    m = re.search(r"select\s+(.*?)\s+from\s", sql, re.IGNORECASE | re.DOTALL)
    if not m:
        return None
    cols_str = m.group(1)
    if "*" in cols_str:
        return None

    parts, current, depth = [], "", 0
    for ch in cols_str:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)

    cols: set[str] = set()
    for p in parts:
        p = p.strip()
        if not p:
            continue
        alias_match = re.search(r"\bas\s+([A-Za-z_][A-Za-z0-9_]*)\s*$", p, re.IGNORECASE)
        if alias_match:
            cols.add(alias_match.group(1))
            continue
        token = p.split()[-1] if " " in p else p
        token = token.split(".")[-1].strip('`"[]')
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", token):
            cols.add(token)
        else:
            return None  # expresión no resoluble -> se pierde certeza para todo el SELECT
    return cols


@dataclass(frozen=True)
class StepContract:
    key_aliases: dict[str, str] = field(default_factory=dict)
    # (required_key, razón legible si falta) — evaluado sobre el config YA
    # normalizado (alias resueltos), así "returns" cuenta como "return_fields".
    required_keys: tuple[tuple[str, str], ...] = ()
    produces: ProducerFn | None = None
    consumes: ConsumerFn | None = None


# ─── produces: (cfg, upstream) -> set[str] | None ──────────────────────────
# None = desconocido, no validar consumidores aguas abajo de este punto.

def _produces_table_input(cfg, upstream):
    return _select_columns(cfg.get("sql", ""))


def _produces_file_input(cfg, upstream):
    names = {f.get("name") for f in cfg.get("fields", []) if isinstance(f, dict) and f.get("name")}
    return names or None


def _produces_added_fields(cfg, upstream):
    if upstream is None:
        return None
    added = {f.get("name") for f in cfg.get("fields", []) if isinstance(f, dict) and f.get("name")}
    return upstream | added


def _produces_calculator(cfg, upstream):
    if upstream is None:
        return None
    added = {
        c.get("field_name") for c in cfg.get("calculations", [])
        if c.get("field_name") and _yn(c.get("removed_from_result", c.get("remove"))) != "Y"
    }
    return upstream | added


def _produces_number_range(cfg, upstream):
    if upstream is None:
        return None
    return upstream | {cfg.get("output_field", "range")}


def _produces_group_by(cfg, upstream):
    if upstream is None:
        return None
    # GroupBy descarta el resto del stream: solo sobreviven los campos de
    # agrupación y los resultados de agregación (mismo comportamiento que
    # GroupByMeta/MemoryGroupByMeta en Kettle).
    group = _names(cfg.get("group_fields", []), "name")
    aggregates = {
        agg.get("name") or agg.get("result_field") or agg.get("aggregate") or agg.get("output_field")
        for agg in cfg.get("aggregates", [])
    }
    return (group | aggregates) - {None, ""}


def _produces_formula(cfg, upstream):
    if upstream is None:
        return None
    added = _names(cfg.get("formulas", cfg.get("fields", [])), "field_name", "name")
    return upstream | added


def _produces_select_values(cfg, upstream):
    select_fields = cfg.get("select") or cfg.get("fields") or cfg.get("columns") or []
    remove_fields = _names(cfg.get("remove", []), "name")
    if select_fields:
        out = set()
        for f in select_fields:
            if isinstance(f, str):
                out.add(f)
            else:
                out.add(f.get("rename") or f.get("name", ""))
        return out - {""}
    if upstream is None:
        return None
    return upstream - remove_fields


def _produces_dimension_lookup(cfg, upstream):
    if upstream is None:
        return None
    return_field = (cfg.get("return_field") or cfg.get("returnfield") or
                    cfg.get("sk_field") or cfg.get("surrogate_key") or "id_sk")
    return upstream | {return_field}


def _produces_db_lookup(cfg, upstream):
    if upstream is None:
        return None
    added = _names(cfg.get("return_fields", cfg.get("returns", [])), "rename", "name")
    return upstream | added


def _produces_stream_lookup(cfg, upstream):
    if upstream is None:
        return None
    added = _names(cfg.get("values", cfg.get("fields", [])), "rename", "name")
    return upstream | added


# ─── consumes: cfg -> set[str] ──────────────────────────────────────────────

def _consumes_table_output(cfg):
    return _names(cfg.get("fields", []), "stream_name", "source")


def _consumes_keys_and_fields(cfg):
    return (_names(cfg.get("keys", []), "stream_field", "name") |
            _names(cfg.get("fields", []), "stream_field", "name"))


def _consumes_delete(cfg):
    return _names(cfg.get("keys", []), "stream_field", "name")


def _consumes_dimension_lookup(cfg):
    req = _names(cfg.get("keys", []), "stream", "stream_field", "name")
    if cfg.get("date_field"):
        req.add(cfg["date_field"])
    return req


def _consumes_combination_lookup(cfg):
    return _names(cfg.get("keys", []), "stream", "name")


def _consumes_db_lookup(cfg):
    return _names(cfg.get("keys", []), "stream_field", "name")


def _consumes_stream_lookup(cfg):
    return _names(cfg.get("keys", []), "stream", "name")


def _consumes_sort_rows(cfg):
    return _names(cfg.get("fields", cfg.get("sort_fields", [])), "name", "field", "column")


def _consumes_unique(cfg):
    return _names(cfg.get("fields", []), "name")


# ─── Registry ────────────────────────────────────────────────────────────────

STEP_CONTRACTS: dict[str, StepContract] = {
    "TableInput": StepContract(produces=_produces_table_input),
    "CsvInput": StepContract(produces=_produces_file_input),
    "ExcelInput": StepContract(produces=_produces_file_input),
    "JsonInput": StepContract(produces=_produces_file_input),
    "TextFileInput": StepContract(produces=_produces_file_input),

    "Constant": StepContract(produces=_produces_added_fields),
    "GetSystemInfo": StepContract(produces=_produces_added_fields),

    "Calculator": StepContract(
        required_keys=(("calculations", "no declara calculations en su config"),),
        produces=_produces_calculator,
    ),
    "NumberRange": StepContract(
        key_aliases={"inputField": "input_field", "outputField": "output_field", "fallBackValue": "fallback"},
        required_keys=(("input_field", "no declara input_field en su config"),),
        produces=_produces_number_range,
    ),
    "GroupBy": StepContract(
        required_keys=(("aggregates", "no declara aggregates en su config"),),
        produces=_produces_group_by,
    ),
    "MemoryGroupBy": StepContract(
        required_keys=(("aggregates", "no declara aggregates en su config"),),
        produces=_produces_group_by,
    ),
    "Formula": StepContract(
        key_aliases={"fieldName": "field_name"},
        required_keys=(("formulas", "no declara formulas en su config"),),
        produces=_produces_formula,
    ),
    "SelectValues": StepContract(produces=_produces_select_values),

    "DimensionLookup": StepContract(
        key_aliases={
            "target_table": "table", "table_name": "table",
            "returnfield": "return_field", "sk_field": "return_field", "surrogate_key": "return_field",
        },
        required_keys=(("keys", "no declara keys de búsqueda en su config"),),
        produces=_produces_dimension_lookup,
        consumes=_consumes_dimension_lookup,
    ),
    "CombinationLookup": StepContract(
        key_aliases={"target_table": "table", "table_name": "table"},
        required_keys=(("keys", "no declara keys de búsqueda en su config"),),
        produces=_produces_dimension_lookup,
        consumes=_consumes_combination_lookup,
    ),
    "DBLookup": StepContract(
        key_aliases={"target_table": "table", "table_name": "table", "returns": "return_fields"},
        required_keys=(("return_fields", "no declara campos de retorno (return_fields) en su config"),),
        produces=_produces_db_lookup,
        consumes=_consumes_db_lookup,
    ),
    "StreamLookup": StepContract(
        required_keys=(("values", "no declara values a traer del stream de lookup en su config"),),
        produces=_produces_stream_lookup,
        consumes=_consumes_stream_lookup,
    ),

    "TableOutput": StepContract(
        key_aliases={"target_table": "table", "table_name": "table"},
        consumes=_consumes_table_output,
    ),
    "InsertUpdate": StepContract(
        key_aliases={"target_table": "table", "table_name": "table"},
        consumes=_consumes_keys_and_fields,
    ),
    "Update": StepContract(
        key_aliases={"target_table": "table", "table_name": "table"},
        consumes=_consumes_keys_and_fields,
    ),
    "Delete": StepContract(
        key_aliases={"target_table": "table", "table_name": "table"},
        consumes=_consumes_delete,
    ),
    "SortRows": StepContract(consumes=_consumes_sort_rows),
    "Unique": StepContract(consumes=_consumes_unique),
}


def _apply_aliases(node, aliases: dict[str, str]):
    if isinstance(node, dict):
        return {aliases.get(k, k): _apply_aliases(v, aliases) for k, v in node.items()}
    if isinstance(node, list):
        return [_apply_aliases(item, aliases) for item in node]
    return node


def normalize_config(canonical_type: str, cfg: dict) -> dict:
    """Traduce alias de clave -> canónica en `cfg`, a cualquier profundidad,
    según el contrato de `canonical_type`. Idempotente. cfg sin contrato o
    contrato sin key_aliases -> se devuelve tal cual (passthrough)."""
    contract = STEP_CONTRACTS.get(canonical_type)
    if contract is None or not contract.key_aliases or not isinstance(cfg, dict):
        return cfg
    return _apply_aliases(cfg, contract.key_aliases)


def missing_required_keys(canonical_type: str, cfg: dict) -> list[tuple[str, str]]:
    """[(key, razón)] para required_keys del contrato ausentes/vacíos en
    `cfg` (ya normalizado). [] si el tipo no tiene contrato o no le falta nada."""
    contract = STEP_CONTRACTS.get(canonical_type)
    if contract is None or not isinstance(cfg, dict):
        return []
    return [(key, reason) for key, reason in contract.required_keys if not cfg.get(key)]
