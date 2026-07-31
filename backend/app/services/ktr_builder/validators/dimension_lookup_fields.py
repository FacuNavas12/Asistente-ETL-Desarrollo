"""D44/D51/R-K7 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md):
`Dimension lookup/update` (steps/lookups.py:_step_DimensionLookup) toma
date_from/date_to/fields[].type de `cfg` con default silencioso cuando faltan:
- date_from -> "fecha_desde", date_to -> "fecha_hasta": literales que no
  coinciden con lo que emite el DDL real (dim_contracts suele declarar
  "fecha_inicio"/"fecha_fin" u otro nombre) — un config incompleto produce un
  .ktr que apunta a columnas inexistentes, sin fallar al guardar, solo en
  runtime.
- fields[].type -> "Insert": DimensionLookupMeta.getUpdateType() (Kettle) cae
  SILENCIOSAMENTE en TYPE_UPDATE_DIM_INSERT ante cualquier string fuera de su
  tabla typeCodes (Insert/Update/Punch through/DateInsertedOrUpdated/
  DateInserted/DateUpdated/LastVersion) — un typo del emisor ("SCD1",
  "overwrite") produce un .ktr válido que VERSIONA en vez de sobrescribir, sin
  error ni warning visible en Spoon.

Este pass cierra ambos huecos ANTES de que el default silencioso los tape —
mismo principio que recover_table_key/flag_dead_computed_fields: reporta
severidad error (D15: notifica, no bloquea, el .ktr sale igual), nunca repara
por su cuenta (no hay forma segura de adivinar el nombre de columna correcto
ni el modo de negocio de un atributo)."""
from __future__ import annotations

from app.domain.scd import ATTRIBUTE_UPDATE_TYPE_CODES
from app.services.ktr_builder.contracts import parse_cfg
from app.services.ktr_builder.validators.base import Finding, ValidationContext

DIMENSION_LOOKUP_FIELDS_PREFIX = "[Dimension lookup/update] "

name = "check_dimension_lookup_fields"

_VALID_TYPE_CODES = {c.lower() for c in ATTRIBUTE_UPDATE_TYPE_CODES}


def check_dimension_lookup_fields(ctx: ValidationContext) -> list[Finding]:
    findings: list[Finding] = []
    for step in ctx.ktr_data.get("steps", []):
        raw_type = step.get("type", "")
        canonical = ctx.step_type_aliases.get(raw_type, raw_type)
        if canonical != "DimensionLookup":
            continue
        step_name = step.get("name", "")
        cfg = parse_cfg(step.get("config", {}))

        if not str(cfg.get("date_from") or "").strip():
            findings.append(Finding(
                severity="error", step_name=step_name,
                message=(
                    f"{DIMENSION_LOOKUP_FIELDS_PREFIX}Step '{step_name}': falta 'date_from' en su "
                    "config — sin él, el emisor cae al literal 'fecha_desde', que puede no existir "
                    "como columna física (dim_contracts suele declarar 'fecha_inicio' u otro "
                    "nombre real). Completar con el nombre EXACTO de dim_contracts."
                ),
            ))
        if not str(cfg.get("date_to") or "").strip():
            findings.append(Finding(
                severity="error", step_name=step_name,
                message=(
                    f"{DIMENSION_LOOKUP_FIELDS_PREFIX}Step '{step_name}': falta 'date_to' en su "
                    "config — mismo riesgo que 'date_from' (el emisor cae al literal 'fecha_hasta')."
                ),
            ))
        for f in cfg.get("fields", []):
            raw_field_type = f.get("type")
            field_type = str(raw_field_type or "").strip()
            field_name = f.get("stream_field") or f.get("stream") or f.get("name") or "?"
            if not field_type:
                findings.append(Finding(
                    severity="error", step_name=step_name,
                    message=(
                        f"{DIMENSION_LOOKUP_FIELDS_PREFIX}Step '{step_name}', atributo '{field_name}': "
                        "sin 'type' explícito — el emisor cae al default 'Insert' (versiona, semántica "
                        "SCD2), que puede no ser lo que el contrato pide para este atributo. "
                        f"Literales válidos (Kettle): {', '.join(ATTRIBUTE_UPDATE_TYPE_CODES)}."
                    ),
                ))
            elif field_type.lower() not in _VALID_TYPE_CODES:
                findings.append(Finding(
                    severity="error", step_name=step_name,
                    message=(
                        f"{DIMENSION_LOOKUP_FIELDS_PREFIX}Step '{step_name}', atributo '{field_name}': "
                        f"type='{raw_field_type}' no es un literal que Kettle reconozca — "
                        "DimensionLookupMeta.getUpdateType() cae SILENCIOSAMENTE en 'Insert' (versiona) "
                        "ante cualquier valor fuera de la lista, sin error visible en Spoon. "
                        f"Literales válidos: {', '.join(ATTRIBUTE_UPDATE_TYPE_CODES)}."
                    ),
                ))
    return findings
