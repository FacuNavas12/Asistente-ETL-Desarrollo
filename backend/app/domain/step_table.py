"""T1 (docs/refactor/05-transversales.md), D62 (docs/refactor/02-decisiones.md):
una sola función que resuelve "qué tabla toca este step", devolviendo un
mensaje de notificación en vez de tragar el caso vacío en silencio (R12,
docs/arquitectura-objetivo.md). Reemplaza el `if not table: continue`
reimplementado por separado en fragmentation.build_rw_matrix,
dimension_step_policy.enforce_dimension_step_policy y
fields_validate.validate_dimension_lookup_races — los tres normalizaban
(`.strip()`, a veces `.lower()`) y descartaban el caso vacío cada uno a su
manera, sin dejar rastro.

Deliberadamente NO decide qué candidato mirar (`cfg["table"]` vs.
`cfg["target_table"]`/`cfg["table_name"]`, prioridad entre ellos) ni si el
tipo de step "debería" tener tabla — eso sigue siendo contrato de cada
caller (DIMENSION_STEP_TYPES, el filtro de canonical de
validate_dimension_lookup_races, _step_rw). Notificar por cada step sin
'table' sin ese filtro previo sería ruido, no señal: la mayoría de los steps
de una transformación (Sort, FilterRows, JavaScript...) legítimamente no
tocan ninguna tabla. Tampoco fuerza minúsculas — dos de los tres callers
comparan case-insensitive y el tercero preserva mayúsculas para mensajes al
usuario; forzar acá rompería esa diferencia ya intencional.

Devuelve un mensaje de texto plano, no un `Finding` (services/ktr_builder/
validators/base.py) — importarlo desde acá cierra un ciclo real:
validators/base vive en el paquete validators/, cuyo __init__ importa
guard_staging_layer, que importa fragmentation, que importa este módulo
(ImportError: partially initialized module, verificado). Cada caller ya
sabe envolver un mensaje en su propia forma de notificación (Finding,
dict {"tipo","campo","mensaje"}, o string plano) — este módulo no necesita
saber cuál."""
from __future__ import annotations


def resolve_step_table(step_name: str, table_raw: str | None) -> tuple[str | None, str | None]:
    """(tabla trimeada | None, mensaje | None). `table_raw` es el candidato
    que el caller ya extrajo de su config normalizada (una sola clave, o una
    prioridad entre varias — eso no es asunto de esta función). Vacío o
    ausente -> (None, mensaje) en vez de (None, None): el caller decide si
    ese mensaje es relevante para su step (ver docstring del módulo) antes
    de agregarlo a su propia lista de resultados."""
    table = (table_raw or "").strip()
    if table:
        return table, None
    return None, (
        f"Step '{step_name}': no se pudo resolver la tabla que toca — la config "
        "normalizada no trae 'table' (vacío o ausente). Se descarta del análisis "
        "en vez de participar con un valor adivinado."
    )
