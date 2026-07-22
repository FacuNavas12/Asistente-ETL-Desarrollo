"""
Parte 4 (bloque A) de la serie dim_contracts: el tipo de step que carga una
dimension se decidia DOS veces — una implicitamente al escribir el DDL
(scd_type), otra al elegir el step en la fase de generacion. Dos decisiones
sobre lo mismo pueden discrepar, y el sintoma aparece en runtime, no al
guardar el .ktr.

La correccion: el tipo de SCD se declara UNA vez, en la inferencia
(dim_contracts[i].scd_type). El tipo de step se DERIVA de esa declaracion en
codigo — no es un juicio del modelo en cada corrida, porque la respuesta es
determinista. El juicio que SÍ sigue siendo del modelo es decidir scd_type en
la inferencia (Parte 1) — eso no cambia acá.

Overrides son legitimos (volumen muy alto cuya cache no entra en memoria,
matching por reglas complejas o difusas, dimension de recarga full refresh) y
existen. La propiedad que se preserva es "default determinista + override
explicito, nunca silencioso": ver OVERRIDE_STEP_PREFIX.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# Mismo patrón que FIELD_INTEGRITY_PREFIX en fields_validate.py: un prefijo de
# texto plano en validaciones[].mensaje que el código detecta por
# startswith() — el modelo lo usa para registrar un override intencional
# (campo = nombre exacto de la tabla) en vez de dejarlo como una discrepancia
# silenciosa entre el step elegido y el que deriva scd_type.
OVERRIDE_STEP_PREFIX = "[Override de step] "

# Tipos de step cuya función es cargar una dimensión (ver derive_dimension_step_type).
# Si uno de estos apunta a una tabla ausente de dim_contracts, no es un step
# cualquiera fuera de alcance (fact, staging, etc.) — es evidencia de que la
# tabla debería estar en el contrato y no llegó (typo, mayúsculas distintas,
# o dimensión faltante en dim_contracts). Ese caso no puede quedar en silencio.
DIMENSION_STEP_TYPES = {"DimensionLookup", "CombinationLookup"}


def derive_dimension_step_type(scd_type: int) -> str:
    """Unica fuente de verdad para "qué step carga esta dimensión". Toda
    dimensión en dim_contracts ya declara su propia surrogate key (D2/D4 de
    la inferencia — el contrato completo es obligatorio sea SCD1 o SCD2), así
    que el único eje de decisión real es si versiona (SCD2) o no.

    Dimensiones sin surrogate key que gestionar (tablas de referencia
    estáticas, PK = clave natural) no entran en dim_contracts en absoluto —
    no llegan a esta función."""
    return "DimensionLookup" if scd_type == 2 else "CombinationLookup"


def _parse_cfg(raw) -> dict:
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    return raw or {}


def _has_registered_override(validaciones: list, table: str) -> bool:
    table_lower = table.strip().lower()
    for v in validaciones or []:
        mensaje = str(v.get("mensaje", "") if isinstance(v, dict) else getattr(v, "mensaje", ""))
        campo = str(v.get("campo", "") if isinstance(v, dict) else getattr(v, "campo", "")).strip().lower()
        if mensaje.startswith(OVERRIDE_STEP_PREFIX) and campo == table_lower:
            return True
    return False


def enforce_dimension_step_policy(
    ktr_data: dict,
    dim_contracts: list,
    step_type_aliases: dict[str, str],
    validaciones_modelo: list | None = None,
) -> list[dict]:
    """Compara, para cada step que carga una tabla listada en dim_contracts,
    el tipo realmente usado contra derive_dimension_step_type(scd_type).

    Tres desenlaces:
    - Coinciden, o hay un override registrado (OVERRIDE_STEP_PREFIX en
      validaciones con campo == tabla): no se toca nada.
    - DimensionLookup usado donde el contrato deriva CombinationLookup (SCD2
      no requerido): downgrade SEGURO — el config de CombinationLookup es un
      subconjunto del de DimensionLookup (table/connection/keys/return_field,
      sin fields ni date_from/date_to). Se corrige in-place y se reporta
      tipo="warning".
    - Cualquier otro desajuste (falta el step de historial que el contrato sí
      pide, o se usó un tipo fuera de {DimensionLookup, CombinationLookup}):
      NO se corrige — faltaría inventar fields/date_from/date_to sin criterio
      de negocio, mismo principio que check_missing_required_fields en
      ktr_default_validator.py ("reporta, no repara"). tipo="error".

    Devuelve dicts {"tipo", "campo", "mensaje"} listos para Validacion(**v).
    Muta ktr_data in-place solo en el caso de downgrade seguro."""
    if not dim_contracts:
        return []

    derived_by_table = {c.table.strip().lower(): derive_dimension_step_type(c.scd_type) for c in dim_contracts}
    validaciones_modelo = validaciones_modelo or []
    results: list[dict] = []

    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        cfg = _parse_cfg(step.get("config", {}))
        table = (cfg.get("table") or cfg.get("target_table") or cfg.get("table_name") or "").strip()
        if not table:
            continue
        if table.lower() not in derived_by_table:
            if canonical in DIMENSION_STEP_TYPES:
                results.append({
                    "tipo": "warning",
                    "campo": table,
                    "mensaje": (
                        f"Step '{step.get('name')}' es '{canonical}' (carga de dimensión) para la tabla "
                        f"'{table}', que no aparece en dim_contracts — no se pudo verificar el tipo de step "
                        "contra el contrato. Revisar si es un typo/mayúsculas distinto al nombre declarado "
                        "en dim_contracts, o si a esa dimensión le falta el contrato."
                    ),
                })
            continue

        expected = derived_by_table[table.lower()]
        if canonical == expected:
            continue
        if _has_registered_override(validaciones_modelo, table):
            logger.info(
                "enforce_dimension_step_policy: override registrado para '%s' (%s en vez de %s) — respetado.",
                table, canonical, expected,
            )
            continue

        if expected == "CombinationLookup" and canonical == "DimensionLookup":
            step["type"] = "CombinationLookup"
            step["config"] = {
                "schema": cfg.get("schema", ""),
                "table": table,
                "connection": cfg.get("connection", ""),
                "return_field": cfg.get("return_field") or cfg.get("returnfield") or "id_sk",
                "keys": cfg.get("keys", []),
            }
            results.append({
                "tipo": "warning",
                "campo": table,
                "mensaje": (
                    f"Step '{step.get('name')}' para '{table}' corregido de DimensionLookup a "
                    "CombinationLookup — el contrato (dim_contracts) declara scd_type != 2 (sin "
                    f"historial de cambios), sin override registrado. Si el step correcto es "
                    f"otro, registrá el override con el prefijo '{OVERRIDE_STEP_PREFIX}' y motivo."
                ),
            })
        else:
            results.append({
                "tipo": "error",
                "campo": table,
                "mensaje": (
                    f"Step '{step.get('name')}' para '{table}' es '{canonical}' pero el contrato "
                    f"(dim_contracts) deriva '{expected}' — sin override registrado. No se "
                    "corrigió automáticamente: faltaría la configuración de historial "
                    "(fields/date_from/date_to) que nadie puede inventar sin criterio de negocio."
                ),
            })

    return results
