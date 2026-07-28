"""
Test de arquitectura (E5, sesión de arquitectura 2026-07-27). Camina los imports
de `backend/app/` por AST y verifica, contra el mapa capa-objetivo de
`docs/arquitectura-objetivo.md` (E1), un subconjunto elegido a propósito de
R1/R3/R4 — no las tres reglas completas. Ver esa sección del doc para el
porqué del recorte: la mayor parte de `services/` ya importa infraestructura
directo (sin `ports/` todavía) y congelar esas decenas de aristas diluiría
la señal de este test a cero. Lo que sí se cubre acá:

  R1 — un módulo etiquetado `domain` (DOMAIN_MODULES) no importa infraestructura
       ni ningún módulo `app.*` que no esté también en DOMAIN_MODULES.
  R3 — ningún módulo de `services/` (ni `domain`, subconjunto de `services/`
       hoy) importa `fastapi`.
  R4 — ningún router (`routers/*.py`) importa `app.models.*` (ORM) directo.

Modo "no empeorar" (E2): las violaciones ya existentes están en las listas
FROZEN_* de abajo, con su justificación. El test falla si aparece una
violación nueva, o si una violación congelada desaparece sin que alguien
achique la lista a mano (así la lista no queda mintiendo).
"""
from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"

# Módulos (dotted path relativo a backend/app/, sin el prefijo "app.") cuyo
# contenido es hoy puramente dominio: sin imports de infraestructura, sin
# SQLAlchemy/FastAPI/clientes HTTP/LLM. Ver docs/arquitectura-objetivo.md
# (mapa E1) para la justificación archivo por archivo.
DOMAIN_MODULES = {
    "services.ktr_builder.contracts",
    "services.ktr_builder.fragmentation",
    "services.ktr_builder.dimension_step_policy",
    "services.ktr_builder.fields_validate",
    "services.ktr_builder.validate",
    # step_types.py: identidad de tipo de step (STEP_TYPE_ALIASES) + completitud
    # mínima (_CRITICAL_FIELDS) — mitad domain del split de registry.py (sesión
    # de arquitectura). La mitad infra (STEP_BUILDERS, STEP_CONFIG_KEYS) quedó
    # en step_emitters.py, deliberadamente afuera de este set.
    "services.ktr_builder.step_types",
    # common.py está partido (E1): _yn/KtrBuilderError son puros, _sub es XML
    # (infra). Se incluye acá solo para permitir que contracts.py importe la
    # mitad pura sin que el test lo marque como cruce de capa — no implica
    # que TODO común.py sea dominio (build.py/connection.py/steps/* siguen
    # usando su mitad infra libremente, eso no lo chequea este test).
    "services.ktr_builder.common",
    "services.sql_defaults",
    "services.ktr_default_validator",
    "services.validate_business_rules",
    # canonical_types.py: CanonicalType/FieldFormat/ColumnRole — value objects
    # puros de stdlib (Enum/Literal), vocabulario de dominio movido afuera de
    # schemas/canonical.py (que los reexporta con excepción nombrada, ver ese
    # archivo). type_mappings.py NO entra acá — se reclasificó a infra en la
    # misma sesión (traduce vendor concreto, consumido solo por otro adaptador).
    "domain.canonical_types",
    # scd.py: criterio determinista de SCD1/SCD2 (D37) + derive_dimension_step_type
    # (movida desde dimension_step_policy.py, que la reexporta) — vocabulario de
    # dominio compartido entre la etapa de inferencia y la de generación de KTR.
    "domain.scd",
}

# Invariante que sostiene 2.b del cierre de la sesión de arquitectura: nada de
# lo de arriba es "schemas.*", y ningún par de FROZEN_R1 debería nombrar
# "schemas.canonical" como target de forma genérica (solo si hace falta un
# caso puntual, documentado, nunca un comodín). Mientras eso se mantenga, un
# módulo de dominio futuro que intente importar CanonicalType a través de la
# fachada de schemas/canonical.py (en vez de domain/canonical_types.py directo)
# cae afuera de DOMAIN_MODULES/FROZEN_R1 y el test de abajo lo va a marcar
# solo — no hace falta una regla nueva para eso, ya lo hace esta.

# Nombres de paquete top-level que son infraestructura casi por definición.
# Si un módulo `domain` los importa (directo o vía `import x.y`), es R1.
INFRA_LIBS = {"sqlalchemy", "fastapi", "httpx", "requests", "google", "anthropic", "frictionless", "sqlglot"}

# --- Violaciones existentes, congeladas (E2 "no empeorar") -----------------

# R1: (módulo domain, módulo app.* que importa sin ser domain) — la razón de
# cada una está en docs/arquitectura-objetivo.md, sección "Mapa E1".
#
# Vacío desde el split de registry.py + movida de CanonicalType a domain/
# (sesión de arquitectura, cierre): las dos violaciones que vivían acá se
# resolvieron de raíz, no se relocaron —
#   - validate.py ↔ registry.py: registry.py se borró, validate.py importa
#     step_types.py directo (domain → domain, cero excepción necesaria).
#   - type_mappings.py ↔ schemas.canonical: type_mappings.py se reclasificó a
#     infra (nunca perteneció a DOMAIN_MODULES) e importa domain/canonical_types.py
#     directo, no a través de la fachada de schemas/.
# Se deja el set tipado (no un comentario "vacío por ahora") para que la
# próxima violación real tenga dónde caer sin rehacer la estructura.
FROZEN_R1: set[tuple[str, str]] = set()

# R3: módulos de services/ (o domain) que importan fastapi directo.
FROZEN_R3 = {
    # job_analyzer.py usa fastapi.UploadFile para el upload de .ktr en
    # POST /api/v1/job/analyze — violación real y citable de R3.
    "services.job_analyzer",
    # etl_service.py / job_service.py lanzan fastapi.HTTPException directo en
    # vez de una excepción de dominio que `core` traduzca — R3 tal cual está
    # escrita ("si necesita fallar, lanza una excepción de dominio") violada
    # por los dos services de CRUD más simples del repo.
    "services.etl_service",
    "services.job_service",
}

# R4: routers que importan app.models.* (ORM) directo, salteando el service.
FROZEN_R4 = {
    # routers/ai.py: db.add(KtrBuildJob) directo en generate-async y
    # {job_id}/connections/{job_id}/status (00-inventario.md sección 2).
    "routers.ai",
    # routers/connections.py: CRUD completo de Connection sin service/repo
    # (00-inventario.md sección 2).
    "routers.connections",
}


def _module_name(path: Path) -> str:
    rel = path.relative_to(APP_DIR).with_suffix("")
    return ".".join(rel.parts)


def _iter_py_files():
    for path in APP_DIR.rglob("*.py"):
        if "__pycache__" in path.parts or path.name == "__init__.py":
            continue
        yield path


def _imported_module_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.append(node.module)
    return names


def test_domain_modules_do_not_import_infrastructure():
    """R1 — dominio no importa infraestructura (subconjunto DOMAIN_MODULES)."""
    violations = set()
    for path in _iter_py_files():
        mod = _module_name(path)
        if mod not in DOMAIN_MODULES:
            continue
        for imported in _imported_module_names(path):
            top = imported.split(".")[0]
            if top in INFRA_LIBS:
                violations.add((mod, imported))
                continue
            if imported.startswith("app."):
                target = imported[len("app."):]
                if target in DOMAIN_MODULES:
                    continue
                if (mod, target) in FROZEN_R1:
                    continue
                violations.add((mod, target))

    assert not violations, (
        "R1 violado — dominio importa infraestructura sin pasar por la "
        f"lista congelada de docs/arquitectura-objetivo.md: {sorted(violations)}"
    )


def test_services_do_not_import_fastapi():
    """R3 — el service no importa fastapi."""
    violations = set()
    for path in _iter_py_files():
        mod = _module_name(path)
        if not mod.startswith("services.") and mod not in DOMAIN_MODULES:
            continue
        if mod in FROZEN_R3:
            continue
        if "fastapi" in {n.split(".")[0] for n in _imported_module_names(path)}:
            violations.add(mod)

    assert not violations, f"R3 violado — service importa fastapi: {sorted(violations)}"


def test_routers_do_not_import_orm_models_directly():
    """R4 — no se saltean capas: el router no importa app.models.* directo."""
    violations = set()
    for path in _iter_py_files():
        mod = _module_name(path)
        if not mod.startswith("routers."):
            continue
        if mod in FROZEN_R4:
            continue
        for imported in _imported_module_names(path):
            if imported.startswith("app.models."):
                violations.add(mod)

    assert not violations, f"R4 violado — router importa ORM directo: {sorted(violations)}"


def test_frozen_lists_have_no_stale_entries():
    """Si una violación congelada ya no existe en el código, la lista miente.

    Este test obliga a achicar FROZEN_* a mano cuando se corrige una — nunca
    se detecta solo "porque el test de arriba pasó" (eso también pasaría con
    la entrada de más)."""
    all_mods = {_module_name(p) for p in _iter_py_files()}
    still_present = set()

    for mod, target in FROZEN_R1:
        if mod not in all_mods:
            continue
        imports = {
            (n[len("app."):] if n.startswith("app.") else n)
            for n in _imported_module_names(APP_DIR / (mod.replace(".", "/") + ".py"))
        }
        if target in imports:
            still_present.add(("R1", mod, target))

    for mod in FROZEN_R3:
        if mod not in all_mods:
            continue
        imports = {n.split(".")[0] for n in _imported_module_names(APP_DIR / (mod.replace(".", "/") + ".py"))}
        if "fastapi" in imports:
            still_present.add(("R3", mod))

    for mod in FROZEN_R4:
        if mod not in all_mods:
            continue
        imports = _imported_module_names(APP_DIR / (mod.replace(".", "/") + ".py"))
        if any(n.startswith("app.models.") for n in imports):
            still_present.add(("R4", mod))

    expected = (
        {("R1",) + t for t in FROZEN_R1}
        | {("R3", m) for m in FROZEN_R3}
        | {("R4", m) for m in FROZEN_R4}
    )
    assert still_present == expected, (
        "Una entrada de FROZEN_* ya no reproduce — sacala de la lista en "
        f"test_architecture_layers.py. Congeladas que ya no aplican: {expected - still_present}"
    )
