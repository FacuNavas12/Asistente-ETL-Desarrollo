"""Inferencia de capa lógica (staging/dwh) por prefijo de nombre de tabla —
heurística de nombre, no de schema real ni de metadata de conexión (D45,
docs/refactor/02-decisiones.md, nota de ejecución bajo "Estado: puntos 3/4/5/7
ejecutados... Decisión ya tomada para cuando se ejecute el punto 2").

Extraído de `ktr_builder/connection.py` (`_STAGING_PREFIXES`/`_DWH_PREFIXES`,
usados ahí solo para inferir la conexión lógica de un step sin `connection`
explícita) para que la matriz R/W de `fragmentation.py` (clave `(connection,
table)`, D45 punto 2) y el emisor de conexiones lean la MISMA lista — antes de
esta extracción, un prefijo nuevo agregado en un lugar no se reflejaba en el
otro (drift silencioso). Vocabulario de dominio puro (tuplas de string +
comparación de prefijo, stdlib): no importa nada de infraestructura."""
from __future__ import annotations

STAGING_TABLE_PREFIXES = ("stg_", "staging_", "tmp_", "temp_", "ods_", "raw_", "wrk_", "work_")
DWH_TABLE_PREFIXES = ("dim_", "fact_", "fct_", "hecho_", "ft_", "dwh_", "bridge_", "br_", "rel_")


def infer_table_layer(table: str) -> str | None:
    """'staging' | 'dwh' | None (sin match — origen, o nombre no reconocible
    por prefijo). Case-insensitive, ignora schema-prefijo (compara contra el
    string completo tal cual llega — si el caller quiere ignorar
    `schema.tabla`, debe pasar la parte de tabla ya separada)."""
    t = (table or "").strip().lower()
    if any(t.startswith(p) for p in DWH_TABLE_PREFIXES):
        return "dwh"
    if any(t.startswith(p) for p in STAGING_TABLE_PREFIXES):
        return "staging"
    return None
