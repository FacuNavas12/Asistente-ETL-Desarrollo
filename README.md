# Asistente ETL

Sistema de asistencia para la generación de procesos ETL con Pentaho PDI, impulsado por IA (Google Gemini 2.5 Flash).
Desarrollado como trabajo de tesis — IAG ETL.

---

## ¿Qué hace?

El sistema ofrece dos secciones independientes accesibles desde el menú principal:

### 🔄 Generar Transformación (.ktr)

1. El usuario describe su fuente de datos, el objetivo del proceso y las reglas de negocio
2. El modelo infiere automáticamente la estructura de la tabla **Staging (STG)** y el **modelo DWH** en DDL SQL (PostgreSQL)
3. El usuario revisa las estructuras generadas y puede corregirlas en lenguaje natural (iterativamente)
4. Al confirmar, el modelo genera el **proceso ETL completo** con sus steps de Pentaho PDI y descarga el archivo `.ktr` listo para usar en Spoon

### ⚙️ Generar Job (.kjb)

1. El usuario sube N archivos `.ktr` existentes y describe el job en lenguaje natural
2. El modelo parsea los archivos, infiere el **orden lógico de ejecución** y propone la lógica de control (variables, checkpoints, manejo de errores, notificaciones)
3. El usuario revisa el plan y puede corregirlo en lenguaje natural (iterativamente)
4. Al confirmar, el modelo genera el **archivo `.kjb`** compatible con Pentaho Spoon, con todas las transformaciones encadenadas y los caminos de éxito/error correctamente configurados

---

## Requisitos previos

- **Python 3.11+**
- **Node.js 18+** y **npm**
- **API Key de Google Gemini** → [Google AI Studio](https://aistudio.google.com/)
- **Cuenta Auth0** con una aplicación configurada (ver sección Auth0)

---

## Instalación y arranque

### Backend (FastAPI + Gemini)

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\activate
# Mac / Linux
source venv/bin/activate

pip install -r requirements.txt

cp .env.example .env
# Editar .env y agregar GOOGLE_API_KEY=tu_api_key

uvicorn app.main:app --reload
```

Disponible en: **http://localhost:8000**
- Docs interactivos: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Frontend (React 19 + Vite)

```bash
cd frontend
npm install
npm run dev
```

Disponible en: **http://localhost:5173** (puerto fijo — ver `vite.config.js`)

---

## Configuración de Auth0

La aplicación usa Auth0 para autenticación. En el dashboard de Auth0 (`manage.auth0.com`):

1. Ir a **Applications → Applications** → seleccionar la app
2. En **Application URIs** configurar:

| Campo | Valor |
|---|---|
| Allowed Callback URLs | `http://localhost:5173/home` |
| Allowed Logout URLs | `http://localhost:5173` |
| Allowed Web Origins | `http://localhost:5173` |

3. Guardar con **Save Changes**

---

## Flujo de uso

### Flujo de Transformación (.ktr)

```
[Formulario — 3 campos]
  Estructura de origen + Objetivo del proceso + Reglas de negocio
        ↓
[Inferencia automática]
  POST /api/v1/etl/infer-structures
  → Gemini genera DDL para tabla STG y modelo DWH
        ↓
[Pantalla de revisión]
  Usuario revisa STG y DWH generados
  Puede corregir en lenguaje natural → POST /api/v1/etl/infer-structures/refine
  Itera hasta confirmar
        ↓
[Generación del ETL]
  POST /api/v1/etl/generate-from-inference
  → Gemini genera proceso ETL completo con steps Pentaho PDI
  → Backend serializa a archivo .ktr
        ↓
[Pantalla de resultados]
  Descripción del proceso + Steps + Validaciones + Documentación
  Descarga del archivo .ktr para Pentaho Spoon
```

### Flujo de Job (.kjb)

```
[Formulario de job]
  Subida de N archivos .ktr + Descripción del job + Reglas adicionales (opcional)
        ↓
[Análisis automático]
  POST /api/v1/job/analyze
  → Backend parsea el XML de cada .ktr y extrae metadata
  → Gemini infiere el orden lógico y la lógica de control del job
  → Los archivos .ktr se guardan temporalmente en el servidor (session_id)
        ↓
[Pantalla de revisión del job]
  Usuario revisa el orden inferido, variables, checkpoints y manejo de errores
  Puede corregir en lenguaje natural → POST /api/v1/job/refine
  Itera hasta confirmar
        ↓
[Generación del .kjb]
  POST /api/v1/job/generate
  → Backend construye el XML .kjb con entries, hops de éxito/error y layout automático
  → Gemini genera la explicación del job en lenguaje natural
  → Se limpian los archivos temporales del servidor
        ↓
[Pantalla de resultados]
  Explicación narrativa del job
  Descarga del archivo .kjb para Pentaho Spoon
  (el .kjb referencia los .ktr por ruta relativa — deben estar en la misma carpeta)
```

---

## Estructura del proyecto

```
Asistente-ETL-Desarrollo/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py              # Settings (API key, modelos, tokens)
│   │   ├── models/
│   │   │   └── gemini_client.py       # Cliente Gemini (call_main / call_secondary)
│   │   │                              # Con reintentos exponenciales para 503/429
│   │   ├── routers/
│   │   │   └── ai.py                  # Todos los endpoints FastAPI (ETL + Job)
│   │   ├── schemas/
│   │   │   ├── etl_schemas.py         # Modelos Pydantic — flujo de transformaciones
│   │   │   └── job_schemas.py         # Modelos Pydantic — flujo de jobs (.kjb)
│   │   └── services/
│   │       ├── etl_generator.py       # Generación del proceso ETL + .ktr
│   │       ├── structure_inferrer.py  # Inferencia y refinamiento de STG/DWH
│   │       ├── ktr_builder.py         # Serialización JSON → XML (.ktr Pentaho)
│   │       ├── job_analyzer.py        # Análisis de .ktr, generación de .kjb
│   │       ├── validator.py           # Validación de calidad del ETL
│   │       └── documenter.py          # Generación de documentación
│   ├── prompts/
│   │   ├── system_etl.txt             # System prompt para generación ETL + .ktr
│   │   ├── system_inference.txt       # System prompt para inferencia STG/DWH
│   │   ├── system_job.txt             # System prompt para análisis y generación de jobs
│   │   ├── system_job_kjb.txt         # System prompt para explicación del job en lenguaje natural
│   │   └── system_validator.txt       # System prompt para validación
│   ├── .env.example
│   └── requirements.txt
│
└── frontend/
    ├── src/
    │   ├── auth0/                     # AuthProvider, PrivateRoute
    │   ├── components/
    │   │   ├── etl/                   # DescripcionObjetivo, StagingMetadataSection
    │   │   ├── layout/                # Layout, Navbar
    │   │   └── ui/                    # UserOptions, LogoutButton
    │   ├── context/
    │   │   ├── EtlContext.jsx         # Estado global ETLs (localStorage + sessionStorage)
    │   │   └── ThemeContext.jsx       # Tema claro/oscuro
    │   ├── pages/
    │   │   ├── CrearETL/              # Formulario + flujo de inferencia STG/DWH
    │   │   │   ├── CrearETL.jsx       # Máquina de estados: form→infer→review→process
    │   │   │   └── components/
    │   │   │       ├── Input/         # InputFormulario (tablas de origen)
    │   │   │       ├── Staging/       # StagingForm
    │   │   │       ├── DWH/           # DwhForm
    │   │   │       ├── BussinesRules/ # ReglasNegocio
    │   │   │       ├── InferenceReview/ # Pantalla de revisión STG/DWH
    │   │   │       ├── EtlChecks.jsx  # Loading spinner con pasos
    │   │   │       └── HomeModal.jsx  # Modal de confirmación salida
    │   │   ├── CrearJob/              # Formulario + flujo de generación de jobs
    │   │   │   ├── CrearJob.jsx       # Máquina de estados: form→analyzing→review→generating→result
    │   │   │   └── components/
    │   │   │       ├── JobForm.jsx    # Drag & drop de .ktr + descripción + reglas
    │   │   │       ├── JobReview.jsx  # Plan del job + corrección iterativa
    │   │   │       └── JobResult.jsx  # Explicación + descarga .kjb
    │   │   ├── EtlDetail/             # Resultados: proceso + validaciones + .ktr
    │   │   ├── Home/                  # Lista de ETLs + acceso a ambas secciones
    │   │   ├── Login/
    │   │   └── Profile/
    │   ├── routes/
    │   │   └── AppRouter.jsx          # Rutas con PrivateRoute (incluye /job-create)
    │   └── styles/                    # CSS global y tema
    └── vite.config.js                 # Puerto fijo 5173, alias @/
```

---

## Endpoints de la API

### Transformaciones (.ktr)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/api/v1/etl/infer-structures` | Inferir STG y DWH desde los 3 campos del usuario |
| `POST` | `/api/v1/etl/infer-structures/refine` | Refinar estructuras con corrección en lenguaje natural |
| `POST` | `/api/v1/etl/generate-from-inference` | Generar ETL completo + .ktr desde estructuras inferidas |
| `POST` | `/api/v1/etl/generate` | Generar ETL desde estructuras manuales (flujo legacy) |
| `POST` | `/api/v1/etl/validate` | Validar calidad del proceso ETL |
| `POST` | `/api/v1/etl/document` | Generar documentación en lenguaje natural |

### Jobs (.kjb)

| Método | Endpoint | Content-Type | Descripción |
|--------|----------|--------------|-------------|
| `POST` | `/api/v1/job/analyze` | `multipart/form-data` | Subir N archivos .ktr + descripción → inferir plan del job |
| `POST` | `/api/v1/job/refine` | `application/json` | Aplicar corrección en lenguaje natural al plan actual |
| `POST` | `/api/v1/job/generate` | `application/json` | Generar .kjb final + explicación a partir del plan confirmado |

> Los archivos `.ktr` se guardan en un directorio temporal del servidor durante la sesión (identificada por `session_id`). Se limpian automáticamente al llamar a `/generate`.

Documentación completa con schemas: http://localhost:8000/docs

---

## Modelos IA utilizados

| Rol | Modelo | Uso |
|-----|--------|-----|
| Principal | `gemini-2.5-flash` | Inferencia de estructuras, generación ETL + .ktr |
| Secundario | `gemini-2.5-flash` | Validación, documentación |

Configurable en `backend/app/core/config.py` (variables `GOOGLE_MODEL_MAIN` y `GOOGLE_MODEL_SECONDARY`).

El cliente Gemini implementa **reintentos con backoff exponencial** (2s → 4s → 8s → 16s) para errores transitorios 503/429.

---

## Generación del archivo .ktr

El archivo `.ktr` es el formato nativo de **Pentaho Spoon (PDI 9.x)**.

- El modelo Gemini genera una representación JSON estructurada del flujo
- `ktr_builder.py` serializa ese JSON a XML válido para PDI
- El layout de steps se calcula automáticamente con ordenamiento topológico (algoritmo de Kahn)
- Las conexiones de base de datos usan **placeholders** (`PLACEHOLDER_HOST`, tipo `GENERIC`) — el usuario los completa en Spoon antes de ejecutar

---

## Generación del archivo .kjb

El archivo `.kjb` es el formato de **Jobs** de Pentaho Spoon (PDI 9.x).

- `job_analyzer.py` parsea el XML de cada `.ktr` subido con `xml.etree.ElementTree` y extrae metadata (nombre, descripción, tipos de steps, indicadores STG/DWH)
- Gemini recibe el resumen de metadata + descripción del usuario e infiere el orden lógico de ejecución
- `build_kjb_xml()` construye el XML con layout automático:
  - `START` en x=100, y=200
  - Transformaciones en secuencia horizontal (x += 200 por step)
  - Checkpoints de log debajo de cada transformación crítica (y+120)
  - Camino de error hacia `Abort job` (y=400)
  - `SUCCESS` al final del camino exitoso
- Los `.ktr` se referencian con **rutas relativas** (`./nombre.ktr`) — basta tener el `.kjb` y los `.ktr` en la misma carpeta para ejecutar sin modificaciones

---

## Seguridad y compliance regulatorio

El sistema fue diseñado para cumplir con el **Marco AGESIC 5.0 (Decreto 66/025)** y la **Ley 18.331 de Protección de Datos Personales** de Uruguay. A continuación se describen los controles implementados en el código.

### Principio de minimización de datos — Al LLM solo llega estructura

> **Invariante no negociable:** el modelo de IA nunca recibe filas de datos crudos, solo la estructura (nombres de columnas, tipos, formatos, reglas). Los valores de producción nunca salen del backend.

Todo origen de datos — CSV, Excel, conexión de BD, DDL pegado o formulario manual — converge en un `CanonicalSchema` y luego pasa por `format_model_context_for_prompt()` antes de enviarse al LLM. Esta función tiene una **whitelist explícita** de campos del perfil estadístico (tipos, porcentaje de nulos, cardinalidad estimada). No hay otro exit point hacia el modelo.

Referencia: `backend/app/services/context_builder.py`

---

### Autenticación de endpoints (AGESIC 5.0 — función Proteger)

Todos los endpoints de la API están protegidos por la dependencia `require_auth` de FastAPI.

| Variable | Valor por defecto | Descripción |
|---|---|---|
| `AUTH_REQUIRED` | `false` | `false` = sin validación (desarrollo). `true` = exige Bearer JWT firmado. |
| `AUTH_JWKS_URL` | — | Endpoint JWKS del proveedor de identidad (Auth0, Azure AD, Keycloak). |
| `AUTH_AUDIENCE` | — | Identificador de la API (claim `aud` del JWT). |
| `AUTH_ISSUER` | — | Issuer del token (claim `iss`). |

En producción se requiere `AUTH_REQUIRED=true` con las tres variables configuradas. El módulo valida firma RS256, expiración, audiencia e issuer en cada request.

Referencia: `backend/app/core/auth.py`

---

### Residencia geográfica de inferencia (Ley 18.331 / AGESIC 5.0)

El sistema soporta dos proveedores LLM, ambos con control de región configurable. Canadá tiene reconocimiento de adecuación GDPR equivalente a Uruguay (PIPEDA).

**Google Gemini — Vertex AI (recomendado para producción)**

```env
GEMINI_PROVIDER=vertex-ai
GCP_PROJECT_ID=mi-proyecto-gcp
GCP_LOCATION=northamerica-northeast1   # Montréal — adecuación GDPR equivalente UY
```

Con `GEMINI_PROVIDER=google-ai-studio` (default de desarrollo), las inferencias se procesan en EE.UU. sin control de región. Para entornos con restricciones de soberanía de datos, usar `vertex-ai`.

**Anthropic Claude**

```env
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
ANTHROPIC_MODEL=claude-sonnet-4-20250514
ANTHROPIC_INFERENCE_REGION=ca          # Canadá — adecuación GDPR equivalente UY
```

El header `anthropic-geography: ca` se envía en cada request para routing geográfico. La garantía de residencia de datos requiere DPA firmado con Anthropic (gestión contractual, independiente del código).

La región efectiva de cada generación queda registrada en el campo `region_inferencia` de la respuesta de la API y en los logs del servidor.

Referencia: `backend/app/models/gemini_llm.py`, `backend/app/models/anthropic_llm.py`

---

### Cifrado de credenciales de conexión (AGESIC 5.0 — función Proteger)

Los passwords de conexiones a bases de datos se cifran con **Fernet (AES-128-CBC + HMAC-SHA256)** antes de persistirse. La clave activa es la primera de la lista; las siguientes solo descifran (rotación sin downtime).

```env
CREDENTIALS_ENCRYPTION_KEYS=CLAVE_ACTIVA,CLAVE_ANTERIOR_SI_HAY_ROTACION
```

Generar una clave nueva:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Sin `CREDENTIALS_ENCRYPTION_KEYS` configurado el módulo de conexiones rechaza cualquier operación de escritura en runtime. **Nunca commitear este valor.**

Referencia: `backend/app/core/crypto.py`

---

### Logs de generaciones (Ley 18.331 — Limitación de conservación)

Cada llamada al LLM genera una entrada de log que incluye modelo usado, región de inferencia, tokens de entrada/salida y latencia. Los logs **nunca incluyen el contenido de los prompts** ni datos del usuario.

- Rotación diaria a medianoche UTC
- Retención: **90 días** (`backupCount=90`)
- Filtro activo que redacta passwords si aparecieran en cualquier mensaje de log

```
backend/logs/generaciones.log
backend/logs/generaciones.log.YYYY-MM-DD   ← archivos rotados
```

Referencia: `backend/app/main.py`, `backend/app/core/log_filters.py`

---

### Retención de datos en el cliente (Ley 18.331 — Limitación de conservación)

Los metadatos de esquema almacenados en `localStorage` (nombres de tablas, columnas, tipos) se tratan como datos personales indirectos bajo la definición amplia de la ley.

| Almacenamiento | TTL | Descripción |
|---|---|---|
| `sessionStorage` | 2 horas | Borrador activo del formulario ETL |
| `localStorage` | 30 días | Lista de ETLs y Jobs guardados |

Al expirar el TTL los datos se eliminan automáticamente en la próxima carga. El logout llama a `clearAllStoredData()` que limpia ambos almacenes.

Referencia: `frontend/src/context/EtlContext.jsx`

---

### Gestión de secretos

- `backend/.env` está excluido del repositorio vía `.gitignore`. **Nunca se commitea.**
- `backend/.env.example` sirve de plantilla documentada para onboarding. No contiene valores reales.
- El backend falla en arranque si `GOOGLE_API_KEY` no está configurado (Gemini) o `ANTHROPIC_API_KEY` (Anthropic).

---

## Ramas activas

| Rama | Descripción |
|------|-------------|
| `main` | Versión estable |
| `develop` | Integración — base para merge de features |
| `backend` | Motor IA (Gemini) + inferencia STG/DWH + generación .ktr + generación .kjb |
| `autenticacion` | Autenticación con Auth0 |
