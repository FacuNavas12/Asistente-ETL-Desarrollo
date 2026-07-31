"""Contrato de resolución de tabla(s) desde SQL crudo (`TableInput.sql`,
`ExecSQL`) — D45 punto 1 (docs/refactor/02-decisiones.md): `Table input` en
Pentaho se define por SQL, no por un campo `table` — es el caso normal, no la
excepción, y hoy lo deja invisible para la matriz R/W de `fragmentation.py`.

`fragmentation.py` está en DOMAIN_MODULES (test_architecture_layers.py: no
importa infraestructura, `sqlglot` incluido) — no puede parsear SQL por su
cuenta. Este módulo define el contrato (`SqlResolution`/`SqlTableResolver`);
la implementación real vive en `app/services/adapters/sql_table_resolver.py`
(sqlglot, infraestructura) y se inyecta como callable en
`build_rw_matrix(ktr_data, aliases, resolve_sql_tables=...)`. Primer port real
del repo (a favor de Track A, arquitectura-objetivo.md)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

# ExecSQL: qué operación de escritura declara el SQL. None cuando el SQL no
# escribe nada reconocible (ej. un SELECT suelto dentro de ExecSQL) o el
# statement no se pudo clasificar.
SqlWriteOp = str  # "TRUNCATE" | "INSERT" | "UPDATE" | "DELETE" | "CREATE"


@dataclass(frozen=True)
class SqlResolution:
    """Resultado de resolver un SQL crudo:

    tables:      conjunto de tablas involucradas (FROM/JOIN de un SELECT, o la(s)
                 tabla(s) afectada(s) por un TRUNCATE/INSERT/UPDATE/DELETE/CREATE),
                 lowercase, con schema si el SQL lo declara ("public.stg_x").
    operation:   SqlWriteOp si el SQL es una sentencia de escritura reconocida,
                 None para un SELECT (o si no se pudo clasificar).
    columns:     columnas proyectadas de un SELECT (S-7), None si no se puede
                 resolver con certeza (SELECT *, expresión sin alias) — mismo
                 criterio de "perder certeza para todo el SELECT" que
                 ktr_builder/contracts.py:_select_columns.
    error:       motivo si el SQL no se pudo parsear en absoluto. `tables`
                 queda vacío en ese caso — el caller decide qué Finding emitir
                 (D15: notifica, no aborta), este contrato no lo prescribe.
    """
    tables: frozenset[str]
    operation: SqlWriteOp | None = None
    columns: frozenset[str] | None = None
    error: str | None = None


class SqlTableResolver(Protocol):
    def __call__(self, sql: str) -> SqlResolution: ...
