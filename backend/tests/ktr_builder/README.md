# tests/ktr_builder — paquete `services/ktr_builder/`

Sin costo real (LLM/API) en ninguna de las 3 subcarpetas — todo unitario o
con fixtures estáticas.

| Subcarpeta | Qué cubre |
|---|---|
| [`build/`](build/README.md) | `build.py` — emisión de steps a XML, reparación, validadores defensivos, parseo de config |
| [`validators/`](validators/README.md) | `validators/` — passes de validación pre-emisión sobre `ktr_data` (contrato `ValidationContext`/`Finding`) |
| [`connections/`](connections/README.md) | Resolución de conexiones reales, XML de `<connection>` |

```bash
pytest tests/ktr_builder/ -v
```
