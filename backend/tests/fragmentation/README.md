# tests/fragmentation — corte N-KTR, lineage, wiring

Sin costo real (LLM/API) — algoritmo puro + wiring con `build_ktr` mockeado
por `monkeypatch`.

| Archivo | Valida |
|---|---|
| `test_fragmentation.py` | Algoritmo de corte puro (`build_rw_matrix`, `compute_cut`, `split_ktr_by_cut`, `validate_stage_contract`) clasifica roles read/write y detecta carreras que exigen split (auto-lookup con materialización, hop cross-group, carrera de writers en el mismo componente), contra la forma real de `err1/err2.ktr`. |
| `test_fragmentation_wiring.py` | El resultado del corte se cablea correctamente en la generación de job-plan N-nivel (`_build_ktr_stage`, `_build_job_plan` — un `build_ktr` por grupo) y `stitch_lineage_many` reconecta los edges de lineage entre archivos partidos. |
| `test_lineage_builder.py` | `build_lineage` — conteo happy-path de nodos/edges/capas y extracción tabla/tipo; una referencia de hop rota se salta+loguea sin lanzar excepción, dejando nodos/edges válidos intactos; steps aislados se clasifican como nodo `origen`; clasificación de nombres dim/fact/staging del DWH. |
| `test_split_integrity_warnings_dedupe.py` | Findings exactamente duplicados de las dos pasadas de verificación (pre-cut full-graph, post-cut por fragmento) colapsan a uno; findings genuinamente distintos sobreviven ambos. |
| `test_job_entry_job.py` | Una entrada `.kjb` que llama a otro `.kjb` emite `<type>JOB</type>` con spec de filename (no TRANS), matcheando el XML real de `JobEntryJob` de Kettle. |

```bash
pytest tests/fragmentation/ -v
```
