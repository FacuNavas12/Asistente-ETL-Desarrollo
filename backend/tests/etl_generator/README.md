# tests/etl_generator — orquestación, prompt, contratos, progreso async

⚠️ **`test_structured_outputs.py` tiene tests con costo real**, marcados
`@pytest.mark.integration` — hacen llamadas reales a la API del LLM (opt-in,
no requieren servidor vivo, solo `.env` con la key). El resto del archivo
(sin el marker) corre siempre, con LLM mockeado. **Excluidos por default**
del comando "gratis" del README raíz vía `-m "not integration"`. Correrlos
a propósito:

```bash
pytest tests/etl_generator/test_structured_outputs.py -m integration -v
```

Los demás archivos de esta carpeta no tienen costo — LLM mockeado en todos.

| Archivo | Tipo | Valida |
|---|---|---|
| `test_context_safety.py` | unit (LLM mockeado) | Ni un identificador de conexión ni valores de columna crudos aparecen nunca en el payload de prompt enviado al LLM, en todos los call sites listados. |
| `test_contract_validate.py` | unit + integración (`TestClient`, LLM mockeado) | `validate_ktr_contracts` detecta un writer que no popula una columna NOT NULL que un DBLookup downstream necesita, y ese mismatch llega a `ETLGenerateResponse` como `Validacion(tipo="error", campo="contrato_ktr")` vía el flujo HTTP completo. |
| `test_etl_generate_response_shape.py` | integración (`TestClient`, LLM mockeado) | Cuando `compute_cut()` detecta necesidad real de fragmentación, el flujo entrega N archivos + `.kjb` intermedio (no solo un warning); `ETLGenerateResponse`/`EtapaOutput`/`ArchivoKtr` hacen round-trip por JSON igual que `result_json` del job async. |
| `test_structured_outputs.py` | unit (siempre) + integración (`@pytest.mark.integration`, **costo real**) | Confirma que el decoding estructurado/constreñido está realmente activo (prompts adversariales no producirían prosa/fences si no) en todos los servicios que llaman al LLM, más lógica unitaria de servicio alrededor de `json_data`. |
| `test_ktr_job_progress.py` | integración (SQLite en memoria + `TestClient` + LLM mockeado) | Eventos de progreso quedan registrados en orden y truncados en count/length máximo; logs de retry/fallback de Gemini se capturan solo con un sink activo; el checkpoint de stage-1 sobrevive a un fallo de stage-2, permitiendo que `reuse_stage_1` se salte la primera llamada al LLM. |

```bash
pytest tests/etl_generator/ -m "not integration" -v
```
