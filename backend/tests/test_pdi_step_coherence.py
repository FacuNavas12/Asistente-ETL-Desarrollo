"""
Coherencia entre los tres catálogos de nombres de step PDI que tienen que
estar de acuerdo (sesión de arquitectura, cierre del split de registry.py):

  1. Lo que system_etl.txt le OFRECE al LLM (prompt).
  2. Lo que step_types.STEP_TYPE_ALIASES NORMALIZA (alias → canónico).
  3. Lo que step_emitters.STEP_BUILDERS CONSTRUYE (canónico → XML).

Reemplaza a KNOWN_PDI_STEP_TYPES (borrado — nunca se consultaba en runtime,
build.py ya rechaza por STEP_BUILDERS.get() is None). Este test no cambia
comportamiento de build_ktr(): convierte lo que antes era un abort en
runtime con un ETL entero fallado en un rojo de CI, para la única dirección
que importa (prompt → sin builder). Las otras dos direcciones son
inofensivas (capacidad desperdiciada / alias huérfano) y se testean con su
propio mensaje para no confundirlas con la bloqueante.

Lectura de system_etl.txt: no se tocan delimitadores en el archivo (es el
system prompt real, cualquier marcador que se le agregue se lo mandaríamos
al modelo). Se usa la estructura de párrafos que el archivo ya tiene: el
bloque de nombres está separado por líneas en blanco reales de la prosa que
lo rodea (después de la oración explicativa, antes de la siguiente sección).
Frágil solo si alguien borra esa línea en blanco — por eso cada token
extraído se valida contra un patrón de identifier; si prosa se cuela adentro
del bloque, el assert de forma falla con mensaje explícito en vez de
comparar conjuntos corrompidos en silencio.
"""
from __future__ import annotations

import re
from pathlib import Path

from app.services.ktr_builder.contracts import STEP_CONTRACTS, TABLE_BEARING_STEPS
from app.services.ktr_builder.step_emitters import STEP_BUILDERS
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_etl.txt"

_HEADER_MARKER = "NOMBRES DE PLUGIN PDI"
_TOKEN_RE = re.compile(r"^[A-Za-z][A-Za-z0-9]*$")


def _extract_prompt_step_names() -> set[str]:
    lines = PROMPT_PATH.read_text(encoding="utf-8").splitlines()
    header_idx = next(i for i, line in enumerate(lines) if _HEADER_MARKER in line)

    # Primera línea en blanco después del header = fin de la prosa explicativa.
    i = header_idx + 1
    while lines[i].strip():
        i += 1
    i += 1  # saltar la línea en blanco misma

    # Bloque de nombres: hasta la próxima línea en blanco.
    block_lines = []
    while i < len(lines) and lines[i].strip():
        block_lines.append(lines[i])
        i += 1

    raw_tokens = [t.strip() for t in " ".join(block_lines).split(",")]
    tokens = {t for t in raw_tokens if t}

    malformed = [t for t in tokens if not _TOKEN_RE.fullmatch(t)]
    assert not malformed, (
        f"system_etl.txt: el bloque de '{_HEADER_MARKER}' tiene tokens que no parecen "
        f"nombres de step ({malformed}) — probablemente se rompió la línea en blanco "
        "que separa la prosa explicativa de la lista. Revisar el archivo a mano; "
        "este test no puede distinguir prosa de nombres si eso pasa."
    )
    return tokens


def test_prompt_names_all_resolve_to_a_builder():
    """La dirección que importa (bloqueante): un nombre que el prompt le
    promete al LLM tiene que terminar en un builder real, directo o vía
    alias — si no, el LLM puede emitir un step que garantiza abortar el
    build entero (KtrBuilderError en build.py)."""
    prompt_names = _extract_prompt_step_names()
    unresolved = sorted(
        name for name in prompt_names
        if STEP_TYPE_ALIASES.get(name, name) not in STEP_BUILDERS
    )
    assert not unresolved, (
        "system_etl.txt promete al LLM estos 'type' sin builder que los construya "
        f"(ni directo ni vía STEP_TYPE_ALIASES): {unresolved}. Cualquier ETL que use "
        "alguno de estos types va a abortar el build — o se agrega el builder, o se "
        "saca el nombre del prompt."
    )


def test_alias_targets_without_builder_are_documented():
    """Alias huérfanos: STEP_TYPE_ALIASES normaliza a un canónico que
    STEP_BUILDERS no sabe construir. Inofensivo hoy porque el prompt no
    ofrece los nombres display que resuelven a estos (ver test de arriba),
    pero si el LLM alucina uno de estos aliases igual, aborta. Lista
    congelada — crece solo si alguien la revisa a mano."""
    orphans = sorted(set(STEP_TYPE_ALIASES.values()) - set(STEP_BUILDERS.keys()))
    known_orphans = [
        "FieldMetaDataValidation", "GetXMLData", "Mapping",
        "MicrosoftExcelWriter", "Normaliser", "Rest", "TransExecutor",
    ]
    assert orphans == sorted(known_orphans), (
        f"Los alias huérfanos cambiaron: eran {sorted(known_orphans)}, ahora son {orphans}. "
        "Si agregaste un alias nuevo sin builder, o un builder para uno de estos, "
        "actualizá esta lista a mano — no es un chequeo automático de 'cero huérfanos', "
        "es un chequeo de que no aparezca uno nuevo sin que alguien lo note."
    )


def test_builders_not_offered_in_prompt_are_documented():
    """Capacidad desperdiciada: builders que existen y el prompt nunca
    ofrece. Inofensivo (el LLM nunca los va a pedir), registro nomás —
    mismo criterio que el test de arriba."""
    prompt_names = _extract_prompt_step_names()
    unused = sorted(set(STEP_BUILDERS.keys()) - prompt_names)
    known_unused = ["DataValidator", "Denormaliser", "SplitFieldToRows", "SplitFieldToRows3"]
    assert unused == sorted(known_unused), (
        f"Los builders no ofrecidos en el prompt cambiaron: eran {sorted(known_unused)}, "
        f"ahora son {unused}. Si agregaste un builder nuevo, decidí si el prompt lo "
        "debería ofrecer y actualizá esta lista a mano."
    )


def test_table_bearing_steps_matches_key_aliases_targeting_table():
    """H29 (docs/refactor/01-hallazgos.md) — contracts.TABLE_BEARING_STEPS es
    deliberadamente explícito (no derivado por introspección) para que este
    test pueda comparar contra STEP_CONTRACTS.key_aliases y avisar si diverge
    — ej. alguien agrega un alias de tabla a un step nuevo y se olvida de
    sumarlo a TABLE_BEARING_STEPS, o viceversa."""
    derived = {
        step_type for step_type, contract in STEP_CONTRACTS.items()
        if "table" in contract.key_aliases.values()
    }
    assert TABLE_BEARING_STEPS == derived, (
        f"TABLE_BEARING_STEPS ({sorted(TABLE_BEARING_STEPS)}) no coincide con los tipos "
        f"que STEP_CONTRACTS declara con alias de tabla ({sorted(derived)}). Si agregaste/"
        "sacaste un alias 'algo': 'table' en contracts.py, actualizá TABLE_BEARING_STEPS "
        "a mano — o si el tipo nuevo declara 'table' directo sin alias, agregalo a mano "
        "a TABLE_BEARING_STEPS y a este test."
    )
