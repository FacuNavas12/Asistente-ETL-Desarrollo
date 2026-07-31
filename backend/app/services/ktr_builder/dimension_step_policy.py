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

D37 (docs/refactor/02-decisiones.md): derive_dimension_step_type() se movio a
domain/scd.py — D11 (acá) fijo que el STEP se deriva de scd_type; D37 fijo de
donde sale scd_type, que D11 daba por dado. Se reexporta acá, mismo patron de
excepcion nombrada que schemas/canonical.py -> domain/canonical_types.py, para
no tocar los call sites existentes de este modulo.

D44/D51 (docs/refactor/02-decisiones.md): derive_dimension_step_type() se
elimina (no queda alias) y se reemplaza por derive_dimension_loader_step()/
derive_fact_lookup_step() — el step se deriva por ROL (loader vs. fact_lookup
de D16), no solo por scd_type. La única rama de auto-fix segura se invierte:
antes era DimensionLookup -> CombinationLookup (downgrade, config subconjunto);
ahora es CombinationLookup -> DimensionLookup, sintetizando fields/date_from/
date_to/version_field desde el DimContract — sigue siendo config de un step
existente, nunca topología (no cruza la línea que D16 fijó). Ver R-K7 en
docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md.
"""
from __future__ import annotations

import logging

from app.domain.scd import (
    ATTRIBUTE_UPDATE_TYPE_CODES,
    derive_attribute_update_mode,
    derive_dimension_loader_step,
    derive_fact_lookup_step,
)
from app.services.ktr_builder.contracts import normalize_config, parse_cfg

logger = logging.getLogger(__name__)

__all__ = [
    "OVERRIDE_STEP_PREFIX",
    "DIMENSION_STEP_TYPES",
    "derive_dimension_loader_step",
    "derive_fact_lookup_step",
    "derive_attribute_update_mode",
    "ATTRIBUTE_UPDATE_TYPE_CODES",
    "role_of_dimension_step",
    "enforce_dimension_step_policy",
]

# Mismo patrón que FIELD_INTEGRITY_PREFIX en fields_validate.py: un prefijo de
# texto plano en validaciones[].mensaje que el código detecta por
# startswith() — el modelo lo usa para registrar un override intencional
# (campo = nombre exacto de la tabla) en vez de dejarlo como una discrepancia
# silenciosa entre el step elegido y el que deriva scd_type.
OVERRIDE_STEP_PREFIX = "[Override de step] "

# Tipos de step cuya función es cargar una dimensión (ver
# derive_dimension_loader_step/derive_fact_lookup_step). Si uno de estos
# apunta a una tabla ausente de dim_contracts, no es un step cualquiera fuera
# de alcance (fact, staging, etc.) — es evidencia de que la tabla debería
# estar en el contrato y no llegó (typo, mayúsculas distintas, o dimensión
# faltante en dim_contracts). Ese caso no puede quedar en silencio.
DIMENSION_STEP_TYPES = {"DimensionLookup", "CombinationLookup"}

# derive_dimension_loader_step()/derive_fact_lookup_step()/
# derive_attribute_update_mode() viven en domain/scd.py (D44/D51) — importadas
# arriba y reexportadas vía __all__.


# D16: tipos de step cuya escritura sobre tabla física es SIEMPRE inequívoca
# (nunca se usan como lookup de solo lectura en este generador) — el ancla
# del BFS de rol tiene que apoyarse en estos, NUNCA en DimensionLookup/
# CombinationLookup, cuyo status de escritura es exactamente lo que
# role_of_dimension_step() está tratando de resolver para la MISMA tabla
# (evita el chicken-and-egg, ver D16 en 02-decisiones.md).
_UNAMBIGUOUS_WRITER_TYPES = {"TableOutput", "InsertUpdate", "Update", "Delete"}


def _write_target_table(step: dict, step_type_aliases: dict[str, str]) -> str | None:
    canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
    if canonical not in _UNAMBIGUOUS_WRITER_TYPES:
        return None
    cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
    return (cfg.get("table") or "").strip() or None


def role_of_dimension_step(
    step_name: str,
    table: str,
    ktr_data: dict,
    step_type_aliases: dict[str, str],
) -> str:
    """"loader" | "fact_lookup" (D16). BFS hacia adelante desde step_name
    siguiendo hops habilitados: si alcanza algún step que escribe una tabla
    física DISTINTA de `table` (típicamente la carga del hecho), step_name es
    un lookup de FK del lado del hecho -> "fact_lookup" (debe quedar
    solo-lectura). Si nunca alcanza otro escritor — termina en la propia
    `table`, o solo en sinks sin tabla (WriteToLog, checkpoints, Dummy) —
    step_name es el loader de la dimensión -> "loader" (mantiene su
    escritura). Un loader que además loguea un checkpoint sigue clasificando
    bien: WriteToLog no es "escritor de tabla", no hace falta excluirlo del
    grado como hacía la heurística descartada (out_deg==0)."""
    steps_by_name = {s.get("name"): s for s in ktr_data.get("steps", [])}
    adjacency: dict[str, list[str]] = {}
    for hop in ktr_data.get("hops", []):
        if not hop.get("enabled", True):
            continue
        adjacency.setdefault(hop.get("from", ""), []).append(hop.get("to", ""))

    table_lower = table.strip().lower()
    visited: set[str] = {step_name}
    stack = list(adjacency.get(step_name, []))
    while stack:
        nxt = stack.pop()
        if nxt in visited:
            continue
        visited.add(nxt)
        nxt_step = steps_by_name.get(nxt)
        if nxt_step is not None:
            target = _write_target_table(nxt_step, step_type_aliases)
            if target and target.strip().lower() != table_lower:
                return "fact_lookup"
        stack.extend(adjacency.get(nxt, []))
    return "loader"


def _has_registered_override(validaciones: list, table: str) -> bool:
    table_lower = table.strip().lower()
    for v in validaciones or []:
        mensaje = str(v.get("mensaje", "") if isinstance(v, dict) else getattr(v, "mensaje", ""))
        campo = str(v.get("campo", "") if isinstance(v, dict) else getattr(v, "campo", "")).strip().lower()
        if mensaje.startswith(OVERRIDE_STEP_PREFIX) and campo == table_lower:
            return True
    return False


def _synthesize_dimension_lookup_config(cfg: dict, contract, *, update: str) -> dict:
    """D44/D51: reconstruye el config de DimensionLookup a partir del
    DimContract al reparar CombinationLookup -> DimensionLookup (dirección
    invertida respecto de la versión anterior de esta política, que hacía el
    downgrade opuesto). Nunca inventa: technical_key/version_field/date_from/
    date_to son obligatorios en TODA dimensión de dim_contracts (V1/V3,
    prompt_validacion_src.txt), y attributes_scd1/attributes_scd2 son el
    contrato completo de atributos no-clave (D37) — el modo de cada uno sale
    de derive_attribute_update_mode() (S-8), nunca del default silencioso
    "Insert" del emisor. `keys` se preserva del config original (ya resuelto
    por el LLM contra la clave natural, y compatible sin mapeo: CombinationLookup
    ya emite {"stream"/"name", "lookup"}, que DimensionLookup también acepta)
    — no se reconstruye desde contract.natural_keys, que no trae el nombre
    del campo del lado del stream.

    `update="N"` (reparación de rol fact_lookup, D16): sin `fields` — un
    lookup de solo lectura no necesita el modo de actualización de cada
    atributo, solo matchear por keys + rango de fechas y devolver
    return_field."""
    new_cfg: dict = {
        "schema": cfg.get("schema", ""),
        "table": cfg.get("table", ""),
        "connection": cfg.get("connection", ""),
        "return_field": cfg.get("return_field") or cfg.get("returnfield") or contract.technical_key,
        "keys": cfg.get("keys", []),
        "update": update,
        "date_from": contract.date_from,
        "date_to": contract.date_to,
        "version_field": contract.version_field,
    }
    if update == "Y":
        new_cfg["fields"] = [
            {
                "stream_field": attr,
                "table_field": attr,
                "type": derive_attribute_update_mode(attr, contract.attributes_scd1, contract.attributes_scd2),
            }
            for attr in (*contract.attributes_scd1, *contract.attributes_scd2)
        ]
    return new_cfg


def enforce_dimension_step_policy(
    ktr_data: dict,
    dim_contracts: list,
    step_type_aliases: dict[str, str],
    validaciones_modelo: list | None = None,
) -> list[dict]:
    """Compara, para cada step que carga/consulta una tabla listada en
    dim_contracts, el tipo realmente usado contra el step que corresponde
    según su ROL (D16: loader vs. fact_lookup) — derive_dimension_loader_step/
    derive_fact_lookup_step, D44/D51: ambos son 'DimensionLookup' para TODO
    scd_type, ver docstring de esas funciones en domain/scd.py.

    Desenlaces:
    - Coinciden, o hay un override registrado (OVERRIDE_STEP_PREFIX en
      validaciones con campo == tabla): no se toca nada.
    - Rol fact_lookup sin solo-lectura: se fuerza update="N" — si el step ya
      es DimensionLookup, in-place; si es CombinationLookup (sin modo de
      solo-lectura), se convierte sintetizando el config desde el contrato
      (_synthesize_dimension_lookup_config). R-K2 (rango [date_from, date_to)
      resuelve bien incluso en dimensiones sin historial real) cierra el
      residual que D16 dejaba abierto acá.
    - Rol loader con CombinationLookup donde el contrato pide DimensionLookup
      (D44/D51: TODO scd_type, 0/1/2): reparación SEGURA — se sintetiza
      fields/date_from/date_to/version_field desde el contrato, que ya los
      declara completos. Se corrige in-place y se reporta tipo="warning".
      (Antes de D44 era la dirección opuesta — downgrade DimensionLookup ->
      CombinationLookup — invertida por completo.)
    - Cualquier otro desajuste (tipo de step fuera de
      {DimensionLookup, CombinationLookup} sobre una tabla de dim_contracts):
      NO se corrige — mismo principio que check_missing_required_fields en
      ktr_default_validator.py ("reporta, no repara"). tipo="error".

    Devuelve dicts {"tipo", "campo", "mensaje"} listos para Validacion(**v).
    Muta ktr_data in-place solo en los casos de reparación segura."""
    if not dim_contracts:
        return []

    contracts_by_table = {c.table.strip().lower(): c for c in dim_contracts}
    validaciones_modelo = validaciones_modelo or []
    results: list[dict] = []

    for step in ktr_data.get("steps", []):
        canonical = step_type_aliases.get(step.get("type", ""), step.get("type", ""))
        # H4: alias de tabla resuelto vía contracts.STEP_CONTRACTS.key_aliases
        # (misma fuente que el builder XML), no un `or` inline propio.
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        table = (cfg.get("table") or "").strip()
        if not table:
            continue
        contract = contracts_by_table.get(table.lower())
        if contract is None:
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

        expected = derive_dimension_loader_step(contract.scd_type)  # "DimensionLookup", siempre (D44/R-K7)

        # D16 (Paso 4) — el rol decide qué regla aplica primero. Un step que
        # solo busca la FK de esta dimensión del lado del hecho (no la carga)
        # nunca debe quedar como escritor, sin importar qué deriva el
        # contrato — ver H21/H22/D16 en 01-hallazgos.md/02-decisiones.md.
        if canonical in DIMENSION_STEP_TYPES:
            role = role_of_dimension_step(step.get("name", ""), table, ktr_data, step_type_aliases)
            if role == "fact_lookup":
                if _has_registered_override(validaciones_modelo, table):
                    logger.info(
                        "enforce_dimension_step_policy: override registrado para '%s' — "
                        "rol fact_lookup no forzado a solo-lectura.", table,
                    )
                    continue
                already_readonly = (
                    canonical == "DimensionLookup"
                    and str(cfg.get("update", "Y")).strip().upper() == "N"
                )
                if already_readonly:
                    continue
                if canonical == "CombinationLookup":
                    # D44/D51: CombinationLookup no tiene modo solo-lectura —
                    # antes se reportaba sin reparar (D16 residual); R-K2
                    # (rango [date_from, date_to) resuelve bien incluso sin
                    # historial real) cierra ese residual, se sintetiza el
                    # DimensionLookup(update=N) equivalente desde el contrato.
                    new_cfg = _synthesize_dimension_lookup_config(cfg, contract, update="N")
                else:
                    new_cfg = dict(cfg)
                    new_cfg["update"] = "N"
                step["type"] = "DimensionLookup"
                step["config"] = new_cfg
                results.append({
                    "tipo": "warning",
                    "campo": table,
                    "mensaje": (
                        f"Step '{step.get('name')}' para '{table}' es un lookup de FK del lado del "
                        "hecho, no el loader de la dimensión — forzado a DimensionLookup con "
                        "update=N (solo lectura) para evitar doble escritor sobre la misma tabla "
                        "(D16). El rango [date_from, date_to) resuelve bien incluso sin historial "
                        "real (R-K2)."
                    ),
                })
                continue
            # role == "loader": cae al chequeo general de abajo.

        if canonical == expected:
            continue
        if _has_registered_override(validaciones_modelo, table):
            logger.info(
                "enforce_dimension_step_policy: override registrado para '%s' (%s en vez de %s) — respetado.",
                table, canonical, expected,
            )
            continue

        if canonical == "CombinationLookup":
            # D44/D51: única reparación segura, dirección invertida respecto
            # de antes — CombinationLookup -> DimensionLookup, sintetizando
            # fields/date_from/date_to/version_field desde el contrato
            # (disponibles siempre: V1/V3 de prompt_validacion_src.txt los
            # exige en TODA dimensión, sea scd_type 0, 1 o 2).
            new_cfg = _synthesize_dimension_lookup_config(cfg, contract, update="Y")
            step["type"] = "DimensionLookup"
            step["config"] = new_cfg
            results.append({
                "tipo": "warning",
                "campo": table,
                "mensaje": (
                    f"Step '{step.get('name')}' para '{table}' corregido de CombinationLookup a "
                    "DimensionLookup — D44/D51: vocabulario uniforme por rol, el loader es "
                    "'Dimension lookup/update' para todo scd_type (incluido 0/1, R-K7). Config "
                    "sintetizado desde dim_contracts (fields con modo por atributo, date_from, "
                    "date_to, version_field). Si el step correcto es otro (junk/technical "
                    f"dimension), registrá el override con el prefijo '{OVERRIDE_STEP_PREFIX}' y motivo."
                ),
            })
        else:
            results.append({
                "tipo": "error",
                "campo": table,
                "mensaje": (
                    f"Step '{step.get('name')}' para '{table}' es '{canonical}' pero el contrato "
                    f"(dim_contracts) deriva '{expected}' — sin override registrado. No se "
                    "corrigió automáticamente."
                ),
            })

    return results
