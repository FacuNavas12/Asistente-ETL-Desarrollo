"""
Parte 3 de la serie dim_contracts (ver structure_inferrer.py para la Parte 1 y
etl_generator.py para la Parte 2): tercera linea de defensa, no la primera.

La Parte 1 hizo que dim_contracts sobreviva la serializacion. La Parte 2 hizo
que la fase de generacion de steps lo consuma en vez de deducirlo por parseo
del DDL. Esta parte cubre lo que igual se escape: el DDL no cumple el contrato
que declara (columna faltante, indice parcial donde no debe, fila
"desconocido" con SK distinta a la que el contrato declara). Sin esto, el
step queda apuntando a algo que no existe -- PDI no falla al guardar el .ktr,
falla en runtime.

validate_and_correct_ddl() corre ANTES de que etl_generator arme los prompts
de KTR_2 (STG->DWH) -- el .ktr se construye contra el DDL final que sale de
aca, no contra el DDL crudo de la inferencia.
"""
from __future__ import annotations

import logging
from pathlib import Path

import sqlglot
from sqlglot import exp

from app.domain.canonical_types import CanonicalType
from app.models.llm_base import BaseLLM, LLMResponse
from app.schemas.etl_schemas import DdlValidationResponse, DimContract, MetadataResponse, Validacion
from app.schemas.llm_output_schemas import DDL_VALIDATION_OUTPUT_SCHEMA
from app.services.adapters.ddl_adapter import parse_ddl

_log = logging.getLogger(__name__)
_SYSTEM_PROMPT = "prompt_validacion_src.txt"

# Centinelas de rango — mismos valores que escribe Kettle al cargar una
# dimensión (D47, H47 en 01-hallazgos.md): evitan que el lookup de FK del
# lado del hecho matchee por accidente la fila "desconocido".
_SEED_DATE_FROM = "1900-01-01 00:00:00"
_SEED_DATE_TO = "2199-12-31 23:59:59.999"


def _load_system(filename: str) -> str:
    return (Path(__file__).resolve().parent.parent.parent / "prompts" / filename).read_text(encoding="utf-8")


def _format_dim_contracts(dim_contracts: list[DimContract]) -> str:
    lines = []
    for c in dim_contracts:
        lines.append(
            f"- {c.table}: technical_key={c.technical_key}, version_field={c.version_field}, "
            f"date_from={c.date_from}, date_to={c.date_to}, natural_keys={list(c.natural_keys)}, "
            f"unknown_key_value={c.unknown_key_value}, scd_type={c.scd_type}"
        )
    return "\n".join(lines)


def _build_prompt(dwh_ddl: str, dim_contracts: list[DimContract]) -> str:
    return f"""## DDL A REVISAR
{dwh_ddl}

## CONTRATO DE DIMENSIONES (dim_contracts)
{_format_dim_contracts(dim_contracts)}

---
Audita el DDL contra el contrato y las invariantes. Devolve UNICAMENTE el JSON de la seccion SALIDA."""


def _parse_response(resp: LLMResponse) -> DdlValidationResponse:
    data = resp.json_data
    if data is None:
        raise ValueError("LLM returned no structured data — json_data is None")
    if "dwh_ddl" not in data:
        raise ValueError("La respuesta del modelo no contiene dwh_ddl.")

    return DdlValidationResponse(
        dwh_ddl=data["dwh_ddl"],
        sin_cambios=data.get("sin_cambios", False),
        cambios_aplicados=data.get("cambios_aplicados", []),
        conflictos=[Validacion(**c) for c in data.get("conflictos", [])],
        metadata=MetadataResponse(
            modelo_usado=resp.model,
            tokens_input=resp.input_tokens,
            tokens_output=resp.output_tokens,
            region_inferencia=resp.provider,
        ),
    )


async def validate_and_correct_ddl(
    dwh_ddl: str,
    dim_contracts: list[DimContract],
    llm: BaseLLM,
) -> DdlValidationResponse:
    """Sin dimensiones (dim_contracts vacio — modelo normalizado) no hay nada
    que auditar contra un contrato que no existe: devuelve el DDL sin tocar,
    sin gastar una llamada al modelo.

    ACOPLAMIENTO: este short-circuit asume que "dim_contracts vacio" siempre
    significa "modelo normalizado, sin dimensiones" -- nunca "el contrato se
    perdio en el camino". Esa distincion no se verifica aca: la hace
    ddl_checks._dim_contracts_anomaly_warning() (compara contra dwh_ddl
    buscando tablas dim_*), en un archivo distinto y sin llamar a esta
    funcion. Si esa advertencia se saca en el futuro, este short-circuit
    queda ciego a un contrato perdido -- no hay redundancia entre las dos."""
    if not dim_contracts:
        return DdlValidationResponse(
            dwh_ddl=dwh_ddl,
            sin_cambios=True,
            cambios_aplicados=[],
            conflictos=[],
            metadata=MetadataResponse(
                modelo_usado="(sin dimensiones — no se llamó al modelo)",
                tokens_input=0, tokens_output=0, region_inferencia="local",
            ),
        )

    prompt = _build_prompt(dwh_ddl, dim_contracts)
    system = _load_system(_SYSTEM_PROMPT)
    resp = await llm.complete(prompt, system, schema=DDL_VALIDATION_OUTPUT_SCHEMA)
    result = _parse_response(resp)

    # R8: instrumentación, no solo red de contención — si esto empieza a
    # aplicar los mismos cambios en cada corrida, la señal es que la
    # inferencia (Parte 1) dejó de emitir el contrato completo.
    if result.sin_cambios:
        _log.info("validate_and_correct_ddl: sin cambios (%d dimension(es) auditadas)", len(dim_contracts))
    else:
        _log.info(
            "validate_and_correct_ddl: %d cambio(s) aplicado(s): %s",
            len(result.cambios_aplicados), result.cambios_aplicados,
        )
    for c in result.conflictos:
        _log.warning("validate_and_correct_ddl conflicto [%s] %s: %s", c.tipo, c.campo, c.mensaje)

    return result


def _table_name_variants(table: str) -> set[str]:
    """Mismo criterio 'full'/'bare' que `ddl_checks._dwh_column_check_constraints`
    (con/sin schema) para no fallar el match por una diferencia de calificación."""
    normalized = table.strip().lower()
    return {normalized, normalized.rsplit(".", 1)[-1]}


def _insert_targets(statements: list[exp.Expression]) -> set[str]:
    """Nombres de tabla (full + bare, minúsculas) que ya tienen algún
    `INSERT INTO` en el DDL — detección por PRESENCIA, no por columnas/valores
    (D6-bis, igual que el resto de este pass)."""
    targets: set[str] = set()
    for stmt in statements:
        if not isinstance(stmt, exp.Insert) or stmt.this is None:
            continue
        tbl = stmt.this.find(exp.Table)
        if tbl is None or not tbl.name:
            continue
        bare = tbl.name.lower()
        targets.add(bare)
        targets.add(f"{tbl.db}.{bare}".lower() if tbl.db else bare)
    return targets


def synthesize_missing_seed_rows(
    dwh_ddl: str,
    dim_contracts: list[DimContract],
) -> tuple[str, list[str]]:
    """Tercera línea de defensa sobre I8/V5 (`prompt_validacion_src.txt`) — D47
    fijó el MECANISMO del sembrado (INSERT embebido en el DDL, no `ExecSQL`/
    segundo escritor), pero eso es una instrucción al LLM, no una garantía de
    código: ni la inferencia ni `validate_and_correct_ddl()` (ambas llamadas al
    modelo) sintetizan nada de forma determinista. Esta función sí: por cada
    `dim_contracts[i]` sin ningún `INSERT` contra su tabla en `dwh_ddl`
    (detección por presencia, D6-bis — no verifica columnas/valores de un
    INSERT ya existente), agrega el INSERT completo con los valores exactos de
    D47 (`01-hallazgos.md` H47): `technical_key=unknown_key_value`,
    `version_field=1`, centinelas de fecha, y toda columna NOT NULL sin
    DEFAULT que declare esa tabla (distinta de las 4 del contrato) recibe
    `'DESCONOCIDO'`/`0` según tipo — mismo criterio que V5.

    Sin parámetro de dialecto: el contrato de DDL del DWH es Postgres-only sin
    excepción hoy (`system_inference.txt:86`, `prompt_validacion_src.txt:14`),
    pese a que `Connection.db_type` sí admite `sqlserver` — ver H52
    (`01-hallazgos.md`). El día que eso cambie, el INSERT sintetizado acá
    necesita una segunda rama (`SET IDENTITY_INSERT <tabla> ON/OFF` alrededor
    de la sentencia para SQL Server) — no alcanza con este `dialect=None`.

    Idempotente: el detector es por presencia de CUALQUIER INSERT contra la
    tabla — si ya hay uno (del modelo o de una corrida anterior de esta misma
    función), no se duplica."""
    if not dwh_ddl or not dwh_ddl.strip() or not dim_contracts:
        return dwh_ddl, []

    try:
        statements = sqlglot.parse(dwh_ddl, dialect=None)
    except Exception as exc:
        _log.warning("synthesize_missing_seed_rows: DDL no parseable, seed rows no verificados: %s", exc)
        return dwh_ddl, []

    seeded_tables = _insert_targets(statements)

    schemas_by_name = {}
    for schema in parse_ddl(dwh_ddl, dialect=None):
        for variant in _table_name_variants(schema.source_name):
            schemas_by_name[variant] = schema

    seed_statements: list[str] = []
    warnings: list[str] = []
    for contract in dim_contracts:
        variants = _table_name_variants(contract.table)
        if variants & seeded_tables:
            continue  # ya sembrada — no se toca (idempotencia)

        schema = next((schemas_by_name[v] for v in variants if v in schemas_by_name), None)
        if schema is None:
            _log.warning(
                "synthesize_missing_seed_rows: tabla '%s' de dim_contracts no encontrada "
                "como CREATE TABLE en dwh_ddl — no se sintetiza seed row.",
                contract.table,
            )
            continue

        fixed_cols = {
            contract.technical_key.lower(), contract.version_field.lower(),
            contract.date_from.lower(), contract.date_to.lower(),
        }
        columns = [contract.technical_key, contract.version_field, contract.date_from, contract.date_to]
        values = [str(contract.unknown_key_value), "1", f"'{_SEED_DATE_FROM}'", f"'{_SEED_DATE_TO}'"]
        for field in schema.fields:
            if field.name.lower() in fixed_cols:
                continue
            if not field.constraints.required or field.default_expr is not None:
                continue
            columns.append(field.name)
            values.append("0" if field.type in (CanonicalType.INTEGER, CanonicalType.NUMBER) else "'DESCONOCIDO'")

        seed_statements.append(
            f"INSERT INTO {contract.table} ({', '.join(columns)}) VALUES ({', '.join(values)});"
        )
        warnings.append(
            f"{contract.table}: sin INSERT sembrado de la fila 'desconocido' (I8/V5) en el DDL final — "
            f"sintetizado con technical_key={contract.unknown_key_value} (dim_contracts.unknown_key_value)."
        )

    if not seed_statements:
        return dwh_ddl, []

    dwh_ddl_final = dwh_ddl.rstrip()
    if not dwh_ddl_final.endswith(";"):
        dwh_ddl_final += ";"
    dwh_ddl_final += "\n\n-- Seed rows sintetizadas (P1-4, sin INSERT del modelo) --\n"
    dwh_ddl_final += "\n".join(seed_statements) + "\n"
    return dwh_ddl_final, warnings
