# Tests manuales con LLM real (consumen API, cobran por llamada)

Esta carpeta vive fuera de `tests/` a propósito: `pytest.ini` (`python_files = tests/test_*.py`)
solo colecciona archivos dentro de `tests/`, y `tests/README.md` documenta `pytest tests/ -v`
como el comando estándar. Ningún corredor automático (ni `pytest` a secas, ni CI, ni el comando
que usan los devs) va a tocar esta carpeta ni a gastar API sin que alguien la invoque a mano y
explícito.

## Cómo correr

```bash
cd backend
venv\Scripts\activate
pytest tests_manual_llm/ -v -s
```

Requiere `backend/.env` con el proveedor LLM configurado (`LLM_PROVIDER` + su API key —
ver `CLAUDE.md`).

## Contenido

- `test_h9_h10_live_scenario.py` — corrida real contra el escenario de
  `docs/refactor/01-hallazgos.md` H9/H10 (ventas/productos → dim_producto/dim_tiempo/fact_venta),
  para confirmar si E3 (mapeo invertido), E14 (Number vs BigNumber) y key vacía en un lookup
  siguen vivos contra el prompt actual, más E1 (SelectValues solo-cast) y E2 (SCD2 declarada y
  ejercitada) que el corpus original no evaluaba. Ver `docs/refactor/02-decisiones.md` D22.
