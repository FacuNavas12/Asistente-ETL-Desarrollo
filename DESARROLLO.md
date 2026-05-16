# Registro de desarrollo — Asistente ETL con IA

Última actualización: 2026-05-13

---

## Qué estamos construyendo

Motor de IA que asiste a analistas en la generación de procesos ETL para Pentaho Data Integration (PDI / Kettle). El usuario completa un formulario web describiendo origen, staging y DWH, y el sistema genera:

1. **Explicación del flujo ETL** — steps PDI sugeridos con justificación, validaciones y documentación técnica
2. **Archivo `.ktr` descargable** — transformación Pentaho lista para abrir en Spoon y ejecutar

Un solo submit, dos outputs. La pantalla de explicación y el botón de descarga coexisten en la misma vista de resultado.

---

## Stack

| Capa | Tecnología |
|------|-----------|
| Frontend | React 19 + Vite, Auth0, localStorage/sessionStorage |
| Backend | FastAPI + Python, Pydantic |
| IA | Google Gemini 2.5 Flash (`google-genai`) |
| ETL target | Pentaho PDI 9.x (Kettle) |

---

## Arquitectura del flujo

```
Usuario llena formulario (origen → staging → DWH + reglas de negocio)
        ↓
POST /api/ai/etl
        ↓
etl_generator.py
  → _build_prompt()         construye prompt con los 3 esquemas + objetivo
  → call_main(system_etl.txt)  una sola llamada a Gemini
  → parse JSON response
  → build_ktr(data["ktr"])  serializa JSON → XML .ktr (Python puro, sin IA)
        ↓
ETLGenerateResponse
  proceso_etl    → explicación con steps, validaciones, documentación
  ktr_xml        → XML del archivo .ktr
  ktr_filename   → nombre sugerido para el archivo
        ↓
Frontend: vista EtlDetail
  → muestra explicación del flujo
  → botón "Descargar .ktr para Pentaho PDI" (descarga client-side)
```

---

## Archivos clave

### Backend

| Archivo | Rol |
|---------|-----|
| `app/services/etl_generator.py` | Servicio principal: construye prompt, llama Gemini, parsea respuesta |
| `app/services/ktr_builder.py` | Serializa el JSON `ktr` del modelo a XML `.ktr` válido para Spoon |
| `app/schemas/etl_schemas.py` | Modelos Pydantic de entrada (`ETLRequest`) y salida (`ETLGenerateResponse`) |
| `app/models/gemini_client.py` | Cliente Gemini: `call_main()` con JSON forzado y `thinking_budget=0` |
| `app/core/config.py` | Variables de entorno; `main_max_tokens=16384` (crítico para no truncar el JSON) |
| `prompts/system_etl.txt` | System prompt: steps PDI válidos, reglas de negocio (R1–R11), formato JSON, instrucciones KTR (K1–K10) |

### Frontend

| Archivo | Rol |
|---------|-----|
| `src/views/CreateETL.jsx` | Formulario principal con 4 secciones + submit al backend |
| `src/views/EtlDetail.jsx` | Vista de resultado: explicación + botón de descarga .ktr |
| `src/context/EtlContext.jsx` | Estado global: lista de ETLs en localStorage, draft en sessionStorage (TTL 2h) |
| `src/components/etl/OrigenInput.jsx` | Sección origen: tablas, columnas, datos de ejemplo |
| `src/components/etl/StagingForm.jsx` | Sección staging: auto-poblado desde origen, reglas de limpieza por columna, reglas de tabla |
| `src/components/etl/DwhModel.jsx` | Sección DWH: dimensiones/facts, surrogate keys, mapeo origen→destino |
| `src/components/etl/tableUtils.jsx` | Hooks y componentes compartidos para edición de tablas |

---

## Decisiones de diseño tomadas

### Una sola llamada a Gemini (no dos)

El diseño original contemplaba dos llamadas separadas: una para la explicación ETL y otra para el KTR. Se decidió usar **una sola llamada** que genera ambas cosas en el mismo JSON.

**Razón:** dos llamadas independientes pueden generar inconsistencias (la explicación dice "usar Sort rows" pero el KTR no lo incluye). Con una sola llamada el modelo tiene contexto completo de ambas salidas y mantiene coherencia.

**Implicación:** `system_etl.txt` contiene tanto las instrucciones de explicación como las de generación KTR. El objeto `ktr` en el JSON del modelo es parseado por `ktr_builder.py` (Python puro) que lo convierte a XML.

### Serialización KTR en Python, no en el modelo

El modelo genera un **JSON estructurado** con `connections`, `steps` y `hops`. El backend (`ktr_builder.py`) convierte ese JSON a XML usando `xml.etree.ElementTree`.

**Razón:** generar XML directamente dentro de un campo string JSON es frágil (el modelo puede no escapar correctamente los caracteres especiales). Con JSON estructurado + serialización Python el XML siempre es válido.

### Conexiones de BD con placeholder

Las conexiones en el `.ktr` generado usan `type: GENERIC` con `host: PLACEHOLDER_HOST`, `database: PLACEHOLDER_DATABASE`, etc.

**Razón:** aún no se definió el motor de BD de destino (PostgreSQL, MySQL, etc.). Cuando se defina, el único cambio es el `type` en el system prompt y el port por defecto. El usuario abre el `.ktr` en Spoon, edita la conexión una vez, y Spoon guarda las credenciales encriptadas.

**Para implementar cuando se defina el motor:**
1. Cambiar `"type": "GENERIC"` al tipo real en `system_etl.txt` (instrucción K6)
2. Ajustar el port por defecto en la instrucción K6
3. Opcionalmente agregar un campo en el formulario para seleccionar el motor

---

## Reglas del system prompt que surgieron de pruebas reales

Estas reglas se agregaron después de analizar un proceso ETL generado con errores:

- **R8 — Colisión de nombres:** si dos tablas origen tienen un campo con el mismo nombre, renombrar desde el `Table Input` con alias SQL antes de cualquier join.
- **R9 — Relaciones N:1 requieren Group by:** si el join entre tablas multiplica filas por clave de negocio, agregar `Group by` antes de cargar al destino.
- **R10 — No asumir claves de join:** si la columna de unión no está en el esquema declarado, reportar error (no inventar el join).
- **R11 — No inferir mapeos:** si un campo en staging/DWH no tiene origen explícito, reportar warning (no crear pasos para campos no declarados).

---

## Pendiente

| Item | Estado | Notas |
|------|--------|-------|
| Definir motor de BD | Pendiente | Cuando se decida, actualizar `system_etl.txt` (instrucción K6) y ajustar port por defecto |
| Probar .ktr en Spoon | Pendiente | Validar que el XML generado abre sin errores y muestra steps conectados |
| Fix Auth0 403 | Pendiente | Agregar `http://localhost:5173/home` en Auth0 dashboard: Allowed Callback URLs, Allowed Logout URLs, Allowed Web Origins |
| Push a rama `backend` | Pendiente | Los commits actuales son locales |
| Merge `backend` → `develop` | Pendiente | Después de probar el flujo completo en navegador |
| Flujo completo end-to-end | Pendiente | Probar submit del formulario → explicación + descarga .ktr en un caso real |

---

## Cómo levantar el proyecto

### Backend
```bash
cd backend
venv\Scripts\activate          # Windows
uvicorn app.main:app --reload  # http://localhost:8000
```

### Frontend
```bash
cd frontend
npm run dev                    # http://localhost:5173
```

El frontend espera el backend en `http://localhost:8000`. Configurar en `frontend/.env` si cambia el puerto.

El backend requiere `backend/.env` con:
```
GOOGLE_API_KEY=AIza...
```

**Nunca commitear `backend/.env`** — contiene la API key real. Solo commitear `backend/.env.example` con placeholder.
