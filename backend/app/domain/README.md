# domain

**Capa:** `domain`
**Propósito:** entidades y vocabulario puro del problema — reglas y tipos que seguirían siendo ciertos aunque cambiara la DB, el proveedor de LLM o el formato de serialización.

## Qué entra
Nada — es la capa más adentro (R1: `domain` no conoce a nadie del proyecto, solo stdlib, con la excepción nombrada de abajo).

## Qué sale
Value objects puros, consumidos por `schemas/` (fachada, ver excepción) y por el resto del backend a través de import directo.

## Archivos
| Archivo | Qué hace |
|---|---|
| `canonical_types.py` | `CanonicalType` (Enum), `FieldFormat` (Literal), `ColumnRole` (Enum) — vocabulario de tipos/columnas, movido desde `schemas/canonical.py` (sesión de arquitectura). |

`services/ktr_builder/step_types.py` es domain por criterio pero queda físicamente en `services/ktr_builder/` — es vocabulario específico de ese paquete (identidad de tipo de step PDI, campos críticos), no vocabulario compartido; sacarlo de ahí sería un segundo movimiento estructural sin necesidad. Ver `docs/arquitectura-objetivo.md`, mapa capa-objetivo, para el resto de lo etiquetado `domain` que todavía no se movió.

## Reglas que aplican
R1 — nada de acá importa infraestructura, ni siquiera indirectamente.
R7 — es el único lugar del repo para conocimiento de dominio compartido entre módulos (si dos módulos necesitan el mismo vocabulario, vive acá, no duplicado).

**Excepción nombrada (no de paquete):** `schemas/canonical.py` reexporta `CanonicalType`/`FieldFormat`/`ColumnRole` de acá para no romper a sus consumidores existentes. Es la única dirección permitida — código de `domain/` nuevo que necesite estos símbolos los importa de acá directo, nunca a través de la fachada de `schemas/` (si lo hiciera, sería domain→schemas por la puerta de atrás; `backend/tests/test_architecture_layers.py` lo detecta solo, ver su comentario sobre `DOMAIN_MODULES`).

## Qué NO va acá
- Un `BaseModel` de Pydantic — eso es `schemas/`, aunque el concepto sea parecido (`CanonicalField`/`CanonicalSchema` se quedan en `schemas/canonical.py`, son DTOs de transporte reales).
- Cualquier import de `sqlalchemy`, `fastapi`, un cliente HTTP o un SDK de LLM — si algo de acá necesita eso, no es dominio.
- Conocimiento específico de Pentaho/KTR que no se comparte fuera de `ktr_builder/` — eso vive en `services/ktr_builder/step_types.py`, no acá (ver nota de arriba).
