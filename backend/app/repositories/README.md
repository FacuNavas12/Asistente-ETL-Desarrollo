# repositories

**Capa:** `infrastructure/persistence/`
**Propósito:** CRUD genérico sobre SQLAlchemy para `Etl`/`Job` — nada de negocio, solo leer y escribir.

## Qué entra
Una `Session` de SQLAlchemy (de `core.database.get_db`) + el modelo ORM a operar.

## Qué sale
Instancias ORM (`Etl`/`Job`) o `None`.

## Archivos
| Archivo | Qué hace |
|---|---|
| `base.py` (38) | `BaseRepository[ModelT]` genérico: `list_all`, `get`, `create`, `update`, `delete`. |
| `etl_repository.py` (4) | Instancia `BaseRepository(Etl)`. |
| `job_repository.py` (4) | Instancia `BaseRepository(Job)`. |

## Reglas que aplican
R8 — el repositorio no decide: no hay un solo `if` de negocio en `base.py`, solo `db.query`/`db.add`/`db.commit`.

**Nota de la sesión de arquitectura (E6):** un `StepRepository`/puerto formal sobre esto sería ceremonia — no hay segunda implementación ni doble de test que lo justifique hoy (los tests que ejercitan este paquete ya corren contra SQLite en memoria real). Ver `docs/arquitectura-objetivo.md` sección "Qué está sobre-especificado hoy". No agregar un `Protocol` acá "porque es lo prolijo" sin que aparezca esa segunda implementación primero.

## Qué NO va acá
- Un `if status == "failed": ...` — eso es un service.
- SQL armado a mano fuera de los métodos genéricos de `BaseRepository` — si un query necesita algo que `BaseRepository` no da, se extiende el repositorio, no se arma el SQL en el service que lo llama (R9).
