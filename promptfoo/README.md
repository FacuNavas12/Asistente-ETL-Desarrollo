# Comparación de modelos — promptfoo

Herramienta de evaluación **separada de pytest**. Compara 4 modelos lado a lado en latencia, costo y calidad de respuesta usando la UI web de promptfoo.

No reemplaza pytest. pytest verifica el código; promptfoo verifica si los modelos responden bien.

## Modelos comparados

| Label | Modelo |
|-------|--------|
| `gemini-flash` | google:gemini-2.5-flash |
| `gemini-pro` | google:gemini-2.5-pro |
| `claude-haiku` | anthropic:messages:claude-haiku-4-5 |
| `claude-sonnet` | anthropic:messages:claude-sonnet-4-5-20250929 |

## Primera corrida — paso a paso

> **IMPORTANTE:** los comandos se corren desde la **raíz del proyecto**, no desde dentro de `promptfoo/`.
> El `package.json` con el script `eval` está en la raíz; si lo corrés desde `promptfoo/` no encuentra el config.

```powershell
# 1. Posicionarse en la raíz del proyecto
cd c:\...\Asistente-ETL-Desarrollo   # o la ruta que corresponda

# 2. Exportar las API keys como variables de entorno de la sesión
$env:GOOGLE_API_KEY = "AIzaSy..."     # clave real de Google AI Studio
# $env:ANTHROPIC_API_KEY = "sk-ant-..." # solo si usás los providers de Claude

# 3. Instalar promptfoo (solo la primera vez, si no existe node_modules en la raíz)
npm install

# 4. Correr la evaluación
npm run eval

# 5. Ver resultados en la UI web
npm run eval:view   # abre http://localhost:15500
```

O directamente con promptfoo (también desde la raíz):
```powershell
npx promptfoo eval --config promptfoo/promptfooconfig.yaml
npx promptfoo view
```

## Requisitos antes de la primera corrida

1. **API keys disponibles como variables de entorno** — promptfoo las lee del entorno del proceso, no del `.env` de backend:
   - `GOOGLE_API_KEY` — obligatoria para los providers Gemini
   - `ANTHROPIC_API_KEY` — solo si descomentás los providers de Claude en `promptfooconfig.yaml`

2. Las keys se exportan por sesión de terminal (ver paso a paso arriba). Si querés que persistan, agregarlas al perfil de PowerShell (`$PROFILE`) o a las variables de entorno del sistema (Panel de control → Variables de entorno).

## Estructura

```
promptfoo/
├── promptfooconfig.yaml   — providers, prompts, tests, latency threshold
├── prompts/
│   ├── etl.yaml           — system_etl.txt + {{message}} (generación ETL)
│   ├── validator.yaml     — system_validator.txt + {{message}} (validar + documentar)
│   └── inference.yaml     — system_inference.txt + {{message}} (inferir + refinar)
└── tests/
    └── cases.yaml         — 10 casos migrados de backend/tests/test_api.py
```

## Tests incluidos

| # | Nombre original | Prompt | Qué mide |
|---|----------------|--------|----------|
| 1 | test_generar_etl_completo | etl | JSON completo, steps no vacíos, steps PDI válidos |
| 2 | test_generar_etl_sin_descripcion | etl | Genera ETL sin objetivo explícito |
| 3 | test_generar_etl_minimo | etl | Payload mínimo: 1 tabla, 1 columna |
| 4 | test_generar_etl_multiples_tablas | etl | Join multi-tabla, manejo de colisión id_prod |
| 5 | test_reglas_negocio_complejas | etl | Cobertura de 7 reglas de limpieza |
| 6 | test_generar_desde_inferencia | etl | ETL desde DDL SQL pre-validado |
| 7 | test_validar_etl | validator | Detección de problemas en ETL existente |
| 8 | test_documentar_etl | validator | Documentación narrativa (usa mismo system prompt) |
| 9 | test_inferir_estructuras | inference | STG + DWH desde estructura de origen |
| 10 | test_refinar_estructuras | inference | Corrección incremental, iteration >= 2 |

## Agregar nuevos casos de prueba

Editar `promptfoo/tests/cases.yaml` y agregar un item con:
```yaml
- description: "Descripción del test"
  prompt: etl          # etl | validator | inference
  vars:
    message: |
      [prompt construido manualmente siguiendo el mismo formato
       que el servicio Python genera en etl_generator.py / validator.py / structure_inferrer.py]
  assert:
    - type: javascript
      value: |
        try {
          const d = JSON.parse(output.replace(/^```(?:json)?\n?|```\s*$/gm, '').trim());
          return 'proceso_etl' in d;
        } catch(e) { return false; }
```

## Cambiar modelos

Editar la sección `providers:` en `promptfoo/promptfooconfig.yaml`. Los IDs de modelos siguen el formato `google:modelo` y `anthropic:messages:modelo`.

## Tests descartados (permanecen solo en pytest)

- test_health_check, test_generar_etl_v1 — testean routing HTTP, no el LLM
- test_generar_etl_sin_descripcion ya migrado (era test_3 equivalente)
- FALLO 1–25 — validan errores 422/404/405, no hay llamada al LLM
- test_connection_schemas.py, test_connections_api.py, test_db_connector.py — sin LLM

## Ajustes opcionales

- **Threshold de latencia** — en `promptfooconfig.yaml` está en 60 s (conservador para generación ETL compleja). Reducirlo a 30 s para un criterio más exigente.
- **Modelos de Claude** — si Anthropic depreca alguno de los IDs (`claude-haiku-4-5`, `claude-sonnet-4-5-20250929`) antes de correr, actualizar en `promptfooconfig.yaml` → `providers`.