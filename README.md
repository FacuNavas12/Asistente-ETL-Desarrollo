# Asistente ETL

Sistema de asistencia para la generación de procesos ETL con Pentaho PDI, impulsado por IA (Google Gemini 2.5 Flash).
Desarrollado como trabajo de tesis — IAG ETL.

---

## ¿Qué hace?

1. El usuario describe su fuente de datos, el objetivo del proceso y las reglas de negocio
2. El modelo infiere automáticamente la estructura de la tabla **Staging (STG)** y el **modelo DWH** en DDL SQL (PostgreSQL)
3. El usuario revisa las estructuras generadas y puede corregirlas en lenguaje natural (iterativamente)
4. Al confirmar, el modelo genera el **proceso ETL completo** con sus steps de Pentaho PDI y descarga el archivo `.ktr` listo para usar en Spoon

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
│   │   │   └── ai.py                  # Todos los endpoints FastAPI
│   │   ├── schemas/
│   │   │   └── etl_schemas.py         # Modelos Pydantic request/response
│   │   └── services/
│   │       ├── etl_generator.py       # Generación del proceso ETL + .ktr
│   │       ├── structure_inferrer.py  # Inferencia y refinamiento de STG/DWH
│   │       ├── ktr_builder.py         # Serialización JSON → XML (.ktr Pentaho)
│   │       ├── validator.py           # Validación de calidad del ETL
│   │       └── documenter.py          # Generación de documentación
│   ├── prompts/
│   │   ├── system_etl.txt             # System prompt para generación ETL + .ktr
│   │   ├── system_inference.txt       # System prompt para inferencia STG/DWH
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
    │   │   ├── CrearETL/              # Formulario + flujo de inferencia
    │   │   │   ├── CrearETL.jsx       # Máquina de estados: form→infer→review→process
    │   │   │   └── components/
    │   │   │       ├── Input/         # InputFormulario (tablas de origen)
    │   │   │       ├── Staging/       # StagingForm
    │   │   │       ├── DWH/           # DwhForm
    │   │   │       ├── BussinesRules/ # ReglasNegocio
    │   │   │       ├── InferenceReview/ # Pantalla de revisión STG/DWH
    │   │   │       ├── EtlChecks.jsx  # Loading spinner con pasos
    │   │   │       └── HomeModal.jsx  # Modal de confirmación salida
    │   │   ├── EtlDetail/             # Resultados: proceso + validaciones + .ktr
    │   │   ├── Home/                  # Lista de ETLs generados
    │   │   ├── Login/
    │   │   └── Profile/
    │   ├── routes/
    │   │   └── AppRouter.jsx          # Rutas con PrivateRoute
    │   └── styles/                    # CSS global y tema
    └── vite.config.js                 # Puerto fijo 5173, alias @/
```

---

## Endpoints de la API

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| `POST` | `/api/v1/etl/infer-structures` | Inferir STG y DWH desde los 3 campos del usuario |
| `POST` | `/api/v1/etl/infer-structures/refine` | Refinar estructuras con corrección en lenguaje natural |
| `POST` | `/api/v1/etl/generate-from-inference` | Generar ETL completo + .ktr desde estructuras inferidas |
| `POST` | `/api/v1/etl/generate` | Generar ETL desde estructuras manuales (flujo legacy) |
| `POST` | `/api/v1/etl/validate` | Validar calidad del proceso ETL |
| `POST` | `/api/v1/etl/document` | Generar documentación en lenguaje natural |

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

## Ramas activas

| Rama | Descripción |
|------|-------------|
| `main` | Versión estable |
| `develop` | Integración — base para merge de features |
| `backend` | Motor IA (Gemini) + inferencia automática STG/DWH + generación .ktr |
| `autenticacion` | Autenticación con Auth0 |
