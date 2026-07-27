"""Reparación dirigida de steps con config incompleto (STEP_CONTRACTS.required_keys).

El LLM a veces emite un step con el `type` correcto pero un `config` que no
cumple el contrato de ese tipo (ver contracts.py) — el ejemplo documentado es
Calculator/DBLookup/StreamLookup con la clave obligatoria vacía o ausente.
build.py aborta el build entero ante eso (correcto: mejor no generar el .ktr
que generar uno que Spoon abre pero no corre). Este módulo intenta, ANTES de
llegar a build_ktr(), salvar esos steps con una llamada al LLM acotada a UN
step por vez — server no depende de que el modelo acierte la forma completa
en la respuesta grande inicial.

No reemplaza el hard-abort de build.py: si tras los reintentos el step sigue
incompleto, se deja tal cual y build.py corta igual, con el mismo mensaje de
siempre.
"""
from __future__ import annotations

import json
import logging

from app.models.llm_base import BaseLLM
from app.services.ktr_builder.contracts import missing_required_keys, normalize_config, parse_cfg
from app.services.ktr_builder.fields_validate import find_missing_field_producers, find_nearest_source_table_name
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES

logger = logging.getLogger(__name__)

# Pocos-ejemplos por tipo, para los canonical_type que declaran required_keys
# en STEP_CONTRACTS (contracts.py) — duplican a propósito los bloques
# equivalentes de system_etl.txt en vez de parsear el prompt en runtime:
# el prompt puede reformatearse libremente sin arriesgar romper el parser acá.
STEP_FEWSHOT: dict[str, str] = {
    "Calculator": (
        '{"calculations": [\n'
        '  {"field_name": "monto_usd", "calc_type": "MULTIPLY", "field_a": "monto", '
        '"field_b": "FACTOR_UYU_USD", "value_type": "Number", "value_length": 15, "value_precision": 2}\n'
        "]}"
    ),
    "Formula": (
        '{"formulas": [{"field_name": "total_con_iva", "formula": "[monto] * 1.22", '
        '"type": "Number", "length": 15, "precision": 2}]}'
    ),
    "NumberRange": (
        '{"input_field": "edad", "output_field": "rango_edad", "fallback": "Sin rango",\n'
        ' "ranges": [{"lower": 0, "upper": 18, "value": "Menor"}, {"lower": 18, "upper": 999, "value": "Adulto"}]}'
    ),
    "GroupBy": (
        '{"group_fields": ["factura_id"],\n'
        ' "aggregates": [{"result_field": "total_cobrado", "subject_field": "monto", "type": "SUM"}]}'
    ),
    "MemoryGroupBy": (
        '{"group_fields": ["cliente_id"],\n'
        ' "aggregates": [{"result_field": "total_compras", "subject_field": "importe", "type": "SUM"}]}'
    ),
    "DimensionLookup": (
        '{"connection": "conn_dwh", "table": "dim_cliente", "returnfield": "sk_cliente",\n'
        ' "keys": [{"stream_field": "cliente_id", "table_field": "bk_cliente"}],\n'
        ' "fields": [{"stream_field": "rut", "table_field": "rut", "type": "Insert"}],\n'
        ' "date_from": "fecha_inicio", "date_to": "fecha_fin"}'
    ),
    "CombinationLookup": (
        '{"connection": "conn_dwh", "table": "dim_tipo_pago", "return_field": "sk_tipo_pago",\n'
        ' "keys": [{"stream_field": "tipo_pago", "table_field": "tipo_pago"}]}'
    ),
    "DBLookup": (
        '{"connection": "conn_dwh", "table": "dim_cliente",\n'
        ' "keys": [{"stream_field": "cod_cliente", "lookup_field": "bk_cliente", "condition": "="}],\n'
        ' "return_fields": [{"name": "sk_cliente", "rename": "sk_cliente", "type": "Integer"}]}'
    ),
    "StreamLookup": (
        '{"step": "Nombre del step que alimenta el lookup", '
        '"keys": [{"stream": "cliente_id", "lookup": "cliente_id"}],\n'
        ' "values": [{"name": "categoria_cliente", "rename": "categoria_cliente", "type": "String"}]}'
    ),
    "RowGenerator": (
        '{"limit": 1, "fields": [{"name": "FACTOR_UYU_USD", "type": "Number", "value": "40"}]}'
    ),
    "Constant": (
        '{"fields": [{"name": "stg_origen", "type": "String", "format": "", "value": "nombre_tabla_origen"},\n'
        '            {"name": "stg_estado", "type": "String", "format": "", "value": "ACTIVO"}]}'
    ),
}

_REPAIR_SYSTEM = (
    "Sos un reparador de configuración de un step de Pentaho Data Integration (Kettle). "
    "Se te da el tipo de step, su config actual (incompleta) y qué claves obligatorias le faltan. "
    "Respondé ÚNICAMENTE el objeto JSON del `config` corregido — nada de texto extra, nada de markdown, "
    "sin envolverlo en otra clave. Conservá todo lo que ya esté bien del config actual; solo completá "
    "lo que falta, usando el contexto de esquema provisto para que los nombres de tabla/columna sean reales."
)


def _repair_prompt(step_name: str, canonical: str, cfg: dict, missing: list[tuple[str, str]], context_text: str) -> str:
    missing_txt = "\n".join(f"- `{key}`: {reason}" for key, reason in missing)
    fewshot = STEP_FEWSHOT.get(canonical, "")
    fewshot_block = f"\nForma esperada (ejemplo):\n```json\n{fewshot}\n```\n" if fewshot else ""
    return f"""Step: "{step_name}" (tipo: {canonical})

Config actual (incompleto):
```json
{json.dumps(cfg, ensure_ascii=False, indent=2)}
```

Claves obligatorias faltantes:
{missing_txt}
{fewshot_block}
## Contexto de esquema (staging/DWH disponibles para nombrar tablas/columnas reales)
{context_text}

Devolvé el `config` corregido completo (JSON, sin comentarios)."""


async def repair_step_config(
    step_name: str,
    canonical: str,
    cfg: dict,
    missing: list[tuple[str, str]],
    context_text: str,
    llm: BaseLLM,
) -> dict | None:
    """Una llamada al LLM acotada a un solo step. None si la llamada falla o
    no devuelve un dict — el caller trata eso como intento fallido (cuenta
    para max_retries, no rompe el loop)."""
    prompt = _repair_prompt(step_name, canonical, cfg, missing, context_text)
    try:
        resp = await llm.complete(prompt, _REPAIR_SYSTEM, schema={"type": "object"})
    except Exception as exc:
        logger.warning("repair_step_config: llamada al LLM falló para '%s' (%s): %s", step_name, canonical, exc)
        return None
    if not isinstance(resp.json_data, dict):
        logger.warning("repair_step_config: respuesta no-dict para '%s' (%s)", step_name, canonical)
        return None
    return resp.json_data


async def repair_ktr_steps(
    ktr_data: dict,
    llm: BaseLLM,
    context_text: str = "",
    max_retries: int = 2,
) -> tuple[dict, list[str]]:
    """Recorre ktr_data['steps'], y para cada uno cuyo config no cumpla
    STEP_CONTRACTS.required_keys intenta regenerar SOLO ese config (hasta
    max_retries veces). Muta ktr_data in-place y lo devuelve junto con
    warnings — uno por step que siguió incompleto tras agotar los reintentos
    (ese step, sin cambios, hará que build_ktr() aborte más abajo, como
    siempre: este loop no reemplaza el hard-abort, solo reduce cuánto se
    dispara)."""
    warnings: list[str] = []
    for step in ktr_data.get("steps", []):
        canonical = STEP_TYPE_ALIASES.get(step.get("type", ""), step.get("type", ""))
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        step["config"] = cfg

        missing = missing_required_keys(canonical, cfg)
        if not missing:
            continue

        step_name = step.get("name", "")
        attempt = 0
        while missing and attempt < max_retries:
            attempt += 1
            logger.info(
                "repair_ktr_steps: reparando '%s' (%s), intento %d/%d, faltan=%s",
                step_name, canonical, attempt, max_retries, [k for k, _ in missing],
            )
            new_cfg = await repair_step_config(step_name, canonical, cfg, missing, context_text, llm)
            if new_cfg is None:
                continue
            cfg = normalize_config(canonical, new_cfg)
            step["config"] = cfg
            missing = missing_required_keys(canonical, cfg)

        if missing:
            warnings.append(
                f"No se pudo reparar '{step_name}' ({canonical}) tras {max_retries} intento(s): "
                f"siguen faltando {[k for k, _ in missing]}."
            )

    return ktr_data, warnings


def _find_twin_constant_config(
    ktr_data: dict, step_type_aliases: dict[str, str], exclude_step: str, missing_fields: set[str]
) -> dict | None:
    """Busca otro step `Constant` en la misma transformación con `fields` ya
    poblado, para usarlo como referencia de forma en el prompt de reparación
    (ej. 'Agregar Constantes Categorías' como gemelo de 'Agregar Constantes
    Productos'). Prioriza el que comparte más nombres de campo con los que
    faltan acá; si ninguno comparte, devuelve el primer `Constant` poblado
    que encuentre. None si no hay ninguno."""
    best: dict | None = None
    best_overlap = -1
    for step in ktr_data.get("steps", []):
        if step.get("name") == exclude_step:
            continue
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        if canonical != "Constant":
            continue
        cfg = parse_cfg(step.get("config", {}))
        fields = cfg.get("fields")
        if not fields:
            continue
        names = {f.get("name") for f in fields if isinstance(f, dict) and f.get("name")}
        overlap = len(names & missing_fields)
        if overlap > best_overlap:
            best_overlap = overlap
            best = cfg
    return best


def _infer_constant_field_value(
    field: str, ktr_data: dict, step_type_aliases: dict[str, str], culprit_step: str
) -> str:
    """Fallback determinístico (sin LLM) para el `value` de un campo de
    auditoría que quedó sin resolver tras agotar los reintentos: `stg_origen`
    (o cualquier campo con 'origen' en el nombre) se deriva de la tabla/
    archivo fuente más cercano aguas arriba (find_nearest_source_table_name);
    `stg_estado` (o cualquier campo con 'estado' en el nombre) recibe
    'ACTIVO'; cualquier otro campo recibe un placeholder neutro."""
    field_lower = field.lower()
    if "origen" in field_lower:
        table = find_nearest_source_table_name(ktr_data, step_type_aliases, culprit_step)
        return table or "origen_desconocido"
    if "estado" in field_lower:
        return "ACTIVO"
    return "N/A"


async def repair_integrity_gaps(
    ktr_data: dict,
    llm: BaseLLM | None,
    context_text: str = "",
    max_retries: int = 1,
) -> tuple[dict, list[str]]:
    """Segunda pasada de reparación, pensada para correr DESPUÉS de
    repair_ktr_steps() (mismo llamador, mismo momento — antes de build_ktr()).

    repair_ktr_steps() detecta config incompleto por step de forma aislada
    (missing_required_keys) pero no sabe QUÉ nombres de campo hacen falta —
    solo que a un `Constant` le falta declarar `fields`. Acá se cruza esa
    misma señal con el grafo de campos (fields_validate.find_missing_field_producers)
    para saber exactamente qué campo necesita el consumidor aguas abajo
    (TableOutput/InsertUpdate/DimensionLookup) y reparar ESE `Constant` con
    esa info — el caso documentado es categorías (Constant con fields
    poblado) vs productos (Constant con config vacío) generados por el mismo
    prompt.

    Dos niveles:
      1. Self-repair acotado (si llm no es None): reenvía SOLO el `Constant`
         culpable al LLM, con el config de un `Constant` "gemelo" ya poblado
         en esta misma transformación (si existe) como referencia de forma.
         Hasta max_retries intentos.
      2. Fallback determinístico (siempre, sin LLM): lo que siga faltando —
         porque llm es None, porque se agotaron los reintentos, o porque no
         hubo llamada — se sintetiza (name de la columna requerida, type
         'String', value inferido por _infer_constant_field_value) y queda
         como warning en vez de dejar que build_ktr aborte con error.

    No reemplaza el hard-abort de build_ktr(): un hueco cuyo culprit no sea
    un `Constant` identificable (ej. rama de hops mal armada) sigue llegando
    tal cual — este módulo solo cubre el caso "Constant con config vacío".

    Muta ktr_data in-place. Devuelve (ktr_data, warnings)."""
    step_by_name = {s.get("name"): s for s in ktr_data.get("steps", [])}
    warnings: list[str] = []

    if llm is not None:
        for attempt in range(1, max_retries + 1):
            records = find_missing_field_producers(ktr_data, STEP_TYPE_ALIASES)
            gaps = [r for r in records if r["culprit_type"] == "Constant" and r["culprit_step"]]
            if not gaps:
                break

            by_step: dict[str, set[str]] = {}
            for r in gaps:
                by_step.setdefault(r["culprit_step"], set()).add(r["field"])

            for step_name, missing_fields in by_step.items():
                step = step_by_name.get(step_name)
                if step is None:
                    continue
                cfg = normalize_config("Constant", parse_cfg(step.get("config", {})))
                twin_cfg = _find_twin_constant_config(ktr_data, STEP_TYPE_ALIASES, step_name, missing_fields)
                twin_block = (
                    "\n\nStep 'gemelo' ya configurado en esta misma transformación (mismo patrón, "
                    "otra tabla) — usalo como referencia de forma, adaptando nombres/valores:\n"
                    f"```json\n{json.dumps(twin_cfg, ensure_ascii=False, indent=2)}\n```"
                    if twin_cfg else ""
                )
                logger.info(
                    "repair_integrity_gaps: reparando '%s' (Constant), intento %d/%d, campos_faltantes=%s",
                    step_name, attempt, max_retries, sorted(missing_fields),
                )
                new_cfg = await repair_step_config(
                    step_name, "Constant", cfg,
                    [("fields", f"faltan declarar (name/type/value) los campos {sorted(missing_fields)}")],
                    context_text + twin_block,
                    llm,
                )
                if new_cfg is not None:
                    step["config"] = normalize_config("Constant", new_cfg)

    records = find_missing_field_producers(ktr_data, STEP_TYPE_ALIASES)
    for r in records:
        if r["culprit_type"] != "Constant" or not r["culprit_step"]:
            continue
        step = step_by_name.get(r["culprit_step"])
        if step is None:
            continue
        cfg = normalize_config("Constant", parse_cfg(step.get("config", {})))
        fields = cfg.setdefault("fields", [])
        if any(isinstance(f, dict) and f.get("name") == r["field"] for f in fields):
            continue
        value = _infer_constant_field_value(r["field"], ktr_data, STEP_TYPE_ALIASES, r["culprit_step"])
        fields.append({"name": r["field"], "type": "String", "value": value})
        step["config"] = cfg
        warnings.append(
            f"Campo '{r['field']}' faltante en '{r['culprit_step']}' (Constant, requerido por "
            f"'{r['consumer']}') — no se pudo reparar vía LLM; se sintetizó determinísticamente "
            f"(value={value!r}) para no bloquear el build. Revisar antes de ejecutar en Spoon."
        )

    return ktr_data, warnings
