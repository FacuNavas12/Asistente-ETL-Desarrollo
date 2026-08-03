"""V-1/V-2 (docs/refactor/plan-reparacion-etl.md, item 5): contra-chequeo
determinista entre lo que el modelo narra en `validaciones` sobre el modo de
un `DimensionLookup` y lo que el step realmente tiene configurado en el KTR
que se va a emitir. Acotado al patrón ya evidenciado -- afirmaciones sobre
`update=Y`/`update=N` (o su paráfrasis "modo Update"/"modo lookup") para una
tabla puntual -- no es NLU general (ver docs/refactor/plan-reparacion-etl.md
§ MATERIAL PARA SESIÓN D).

Objeción registrada post-plan (sesión de cierre de ciclo C): el pass hace
regex sobre prosa en español generada por un LLM -- si el regex no matchea
nada, `findings` sale vacío, indistinguible de "narración consistente". Ese
falso negativo invisible es exactamente el modo de falla de V-1 que este
pass viene a atajar. No se resuelve acá (la alternativa de fondo -- derivar
el informe del XML en vez de parsear narración -- queda para sesión D, ver
MATERIAL PARA SESIÓN D) ni se extiende el regex (mismo criterio D6-bis:
NLU arbitraria no es alcance de este pass). Lo que sí se hace, mismo
criterio D5/D45 pt.1 que los ítems 7 y 8 (nada degrada en silencio): el pass
SIEMPRE declara su cobertura real al final -- cuántos steps DimensionLookup
hay vs. cuántos quedaron efectivamente cruzados contra alguna afirmación de
la narración -- para que "cruzó cero" se lea en el informe como "no
verificado", no como ausencia de hallazgos."""
from __future__ import annotations

import re

from app.services.ktr_builder.contracts import normalize_config, parse_cfg
from app.services.ktr_builder.validators.base import Finding, ValidationContext

NARRATION_CROSSCHECK_PREFIX = "[Narración vs XML] "

name = "check_narration_crosscheck"

_CLAIM_UPDATE_Y = re.compile(
    r"update\s*=\s*Y\b|modo\s+update\b|todos?\s+los?\s+atributos?\s+en\s+modo\s+update",
    re.IGNORECASE,
)
_CLAIM_UPDATE_N = re.compile(
    r"update\s*=\s*N\b|modo\s+lookup\b|solo\s+lectura\b",
    re.IGNORECASE,
)


def _claimed_mode(mensaje: str) -> str | None:
    has_y = bool(_CLAIM_UPDATE_Y.search(mensaje))
    has_n = bool(_CLAIM_UPDATE_N.search(mensaje))
    if has_y and not has_n:
        return "Y"
    if has_n and not has_y:
        return "N"
    return None


def check_narration_crosscheck(ctx: ValidationContext) -> list[Finding]:
    dim_lookup_steps: list[tuple[str, str, str]] = []
    for step in ctx.ktr_data.get("steps", []):
        raw_type = step.get("type", "")
        canonical = ctx.step_type_aliases.get(raw_type, raw_type)
        if canonical != "DimensionLookup":
            continue
        cfg = normalize_config(canonical, parse_cfg(step.get("config", {})))
        table = str(cfg.get("table") or "").strip().lower()
        if not table:
            continue
        actual_mode = "N" if str(cfg.get("update", "Y")).strip().upper() == "N" else "Y"
        dim_lookup_steps.append((step.get("name", ""), table, actual_mode))

    if not dim_lookup_steps:
        # Nada que cruzar -- a diferencia del caso "hay steps pero la
        # narración no dijo nada", acá no hay ninguna afirmación posible
        # que verificar, así que "sin findings" sí significa "nada que
        # reportar" (no un blind spot).
        return []

    findings: list[Finding] = []
    checked_tables: set[str] = set()
    for campo, mensaje in ctx.narracion_modelo:
        claimed = _claimed_mode(mensaje)
        if claimed is None:
            continue
        campo_norm = campo.strip().lower()
        for step_name, table, actual_mode in dim_lookup_steps:
            if table != campo_norm:
                continue
            checked_tables.add(table)
            if actual_mode == claimed:
                continue
            findings.append(Finding(
                severity="error", step_name=step_name,
                message=(
                    f"{NARRATION_CROSSCHECK_PREFIX}La narración del modelo para '{campo}' afirma "
                    f"update={claimed} ('{mensaje}'), pero el step '{step_name}' en el XML emitido "
                    f"tiene update={actual_mode} -- narración y KTR emitido no coinciden."
                ),
            ))

    # Cobertura real del pass (ver docstring del módulo) -- SIEMPRE se
    # declara, con o sin mismatches encontrados arriba. severity="info"
    # (no "error"/"warning": no es un defecto del KTR, es el alcance del
    # propio chequeo -- mismo criterio que el finding tipo="info" de
    # dimension_step_policy.py para el branch de override, item 1 de este
    # plan: "no se corrige, pero se dice por qué" en vez de un continue
    # mudo). No se promueve a Validacion tipo=error (split_findings_by_
    # severity/_split_integrity_warnings) -- no verificado no es lo mismo
    # que roto.
    total = len(dim_lookup_steps)
    covered = len(checked_tables)
    coverage_msg = (
        f"{NARRATION_CROSSCHECK_PREFIX}Cobertura: {covered}/{total} step(s) DimensionLookup "
        "cruzados contra alguna afirmación de la narración del modelo."
    )
    if covered == 0:
        coverage_msg += (
            " Ninguna afirmación de update=Y/N detectada para verificar -- 'sin hallazgos' acá "
            "significa 'no verificado', no 'narración consistente'."
        )
    findings.append(Finding(severity="info", message=coverage_msg))
    return findings
