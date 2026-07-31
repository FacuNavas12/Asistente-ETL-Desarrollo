"""Fase 2-ter, item 2 (S-5/H-5, docs/refactor/03c-investigacion-vocabulario-
dimension-kettle.md): backstop determinista de D42 (commit 850dcdb, "staging
deja de recibir reglas de negocio en el prompt").

Evidencia: Set B crudo filtró precios negativos en `origen->staging` (`Leer
Productos` 10 filas -> `Cargar stg_tienda_producto` 8) — rompe el contrato
"truncate+load = copia estructural completa" que el prompt de la etapa 1 le
pide al modelo (K-algo en system_etl.txt: staging es "un contenedor FIEL del
origen", los únicos steps además de lectura/escritura son transformación
TÉCNICA — tipos, renombres, campos de auditoría; ningún `FilterRows` u otro
step de validación/filtrado por regla de negocio). D42 ya sacó esa regla del
prompt; este pass es el guard determinista que no depende de que el modelo la
respete: destino (tabla `stg_*`/`staging_*`/etc., D45) y tipo de step
(`FilterRows`) son conocidos en build-time, sin necesitar LLM.

Reachability, no presencia plana (a diferencia de check_constraint_filter.py):
acá SÍ importa que el FilterRows alimente de verdad al writer de staging —
un FilterRows que sanea una rama completamente distinta del mismo KTR (ej.
descarta filas defectuosas antes de un TableOutput a una tabla DE ORIGEN
re-emitida) no es la violación que D42 prohíbe. Reusa build_rw_matrix
(fragmentation.py) para no reimplementar qué step escribe qué tabla."""
from __future__ import annotations

from app.domain.table_layer import infer_table_layer
from app.services.ktr_builder.fragmentation import build_rw_matrix
from app.services.ktr_builder.validators.base import Finding, ValidationContext

STAGING_GUARD_PREFIX = "[Guard capa staging] "

name = "guard_staging_layer"


def _ancestors(target: str, hops: list[dict]) -> set[str]:
    """Nombres de step con camino dirigido (hops habilitados) hacia `target`."""
    reverse_adj: dict[str, set[str]] = {}
    for hop in hops:
        if not hop.get("enabled", True):
            continue
        a, b = hop.get("from", ""), hop.get("to", "")
        reverse_adj.setdefault(b, set()).add(a)

    seen: set[str] = set()
    stack = [target]
    while stack:
        cur = stack.pop()
        for prev in reverse_adj.get(cur, ()):
            if prev not in seen:
                seen.add(prev)
                stack.append(prev)
    return seen


def guard_staging_layer(ctx: ValidationContext) -> list[Finding]:
    steps = ctx.ktr_data.get("steps", [])
    hops = ctx.ktr_data.get("hops", [])

    filter_names = {
        s.get("name", "")
        for s in steps
        if ctx.step_type_aliases.get(s.get("type", ""), s.get("type", "")) == "FilterRows"
    }
    if not filter_names:
        return []

    # Sin resolve_sql_tables: mismo alcance que antes de D45 (TableInput/
    # ExecSQL invisibles) — este guard mira solo writers directos (table
    # declarada) via TableOutput/InsertUpdate/Update/DimensionLookup, que no
    # dependen de la resolución SQL de D45.
    matrix, _resolution_findings = build_rw_matrix(ctx.ktr_data, ctx.step_type_aliases)
    staging_writers: dict[str, str] = {}  # step_name -> table
    for (_connection, table), roles in matrix.items():
        if infer_table_layer(table) != "staging":
            continue
        for step_name, rw in roles.items():
            if rw in ("W", "RW"):
                staging_writers[step_name] = table

    findings: list[Finding] = []
    for step_name, table in staging_writers.items():
        upstream_filters = filter_names & _ancestors(step_name, hops)
        for filter_name in sorted(upstream_filters):
            findings.append(Finding(
                severity="error", step_name=filter_name,
                message=(
                    f"{STAGING_GUARD_PREFIX}FilterRows '{filter_name}' alimenta, vía hops, al step "
                    f"'{step_name}' que escribe la tabla de staging '{table}' — staging tiene que ser "
                    "copia estructural completa (truncate+load), sin filtrado por regla de negocio "
                    "(D42). Mover este filtro a la etapa STG→DWH, o confirmar que es transformación "
                    "técnica y no un FilterRows."
                ),
            ))
    return findings
