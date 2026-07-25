"""
Gap identificado en D23 (docs/refactor/02-decisiones.md), separado del validador de
contrato entre KTR (escritor→lector): nada en el pipeline valida hoy que las reglas
de negocio (`business_rules`/`reglasNegocio`) declaradas por el usuario se hayan
aplicado efectivamente en los steps generados. Hoy `business_rules` solo entra como
texto libre al prompt de `structure_inferrer.py` para dar forma a `stg_ddl`/`dwh_ddl`/
`dim_contracts` en el momento de inferir — ningún validador post-generación la vuelve
a mirar contra el KTR ya armado.

Stub deliberado: pase libre siempre (lista vacía). Ya queda wireado en
`etl_generator.py` (llamado por etapa, con el DDL correspondiente disponible en ese
punto) para que el punto de enganche exista desde ahora — implementar la lógica real
de comparación reglas↔steps es trabajo futuro, no de esta sesión.
"""
from __future__ import annotations

#TODO: agregar tests unitarios para este validador de reglas de negocio (D23).

def validate_business_rules(ddl: str, business_rules: str, ktr_data: dict) -> list[str]:
    """Debe comparar `business_rules` contra los steps de `ktr_data` (config,
    fórmulas, filtros) usando `ddl` como referencia de columnas/tipos de la etapa,
    y devolver un mensaje de warning por cada regla que no encuentre reflejada.
    Hoy: pase libre siempre, sin implementación real todavía (D23)."""
    return []
