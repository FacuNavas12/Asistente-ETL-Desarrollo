# tests/architecture — checks estáticos cross-cutting

Sin costo real (LLM/API) — solo AST/parseo estático, no importan `app` con
efectos secundarios de red.

| Archivo | Valida |
|---|---|
| `test_architecture_layers.py` | Recorre por AST los imports de `app/` para exigir que módulos de dominio nunca importen infraestructura, `services` nunca importe `fastapi`, `routers` nunca importe modelos ORM directo — contra una allowlist congelada de violaciones preexistentes. |
| `test_pdi_step_coherence.py` | Todo nombre de step ofrecido al LLM en el prompt (`prompts/system_etl.txt`) resuelve a un emitter real (dirección bloqueante); mismatches alias-sin-builder / builder-no-ofrecido quedan documentados explícitamente, no como drift silencioso. |

```bash
pytest tests/architecture/ -v
```
