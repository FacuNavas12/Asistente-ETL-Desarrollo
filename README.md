# Asistente ETL

Sistema de asistencia para la generación de procesos ETL con Pentaho PDI, usando inteligencia artificial (Gemini 2.5 Flash) como motor de generación.

---

## Requisitos previos

- **Python 3.11+**
- **Node.js 18+** y **npm**
- **API Key de Google Gemini** (se obtiene en [Google AI Studio](https://aistudio.google.com/))

---

## Levantar el backend

### 1. Crear y activar el entorno virtual

```bash
cd backend
python -m venv venv
```

**Windows:**
```bash
venv\Scripts\activate
```

**Mac / Linux:**
```bash
source venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 3. Configurar variables de entorno

Copiar el archivo de ejemplo y completarlo con la API key real:

```bash
cp .env.example .env
```

Abrir `.env` y reemplazar el valor de `GOOGLE_API_KEY`:

```
GOOGLE_API_KEY=tu_api_key_aqui
```

### 4. Iniciar el servidor

```bash
uvicorn app.main:app --reload
```

El backend queda disponible en: **http://localhost:8000**

Para verificar que está corriendo: http://localhost:8000/health

Documentación interactiva de la API: http://localhost:8000/docs

---

## Levantar el frontend

### 1. Instalar dependencias

```bash
cd frontend
npm install
```

### 2. Iniciar el servidor de desarrollo

```bash
npm run dev
```

El frontend queda disponible en: **http://localhost:5173**

Abrí esa URL en el navegador para usar la aplicación.

---

## Levantar ambos al mismo tiempo

Abrí **dos terminales** separadas desde la raíz del proyecto:

**Terminal 1 — Backend:**
```bash
cd backend
venv\Scripts\activate
uvicorn app.main:app --reload
```

**Terminal 2 — Frontend:**
```bash
cd frontend
npm run dev
```

Luego abrí **http://localhost:5173** en el navegador.

---

## Estructura del proyecto

```
Asistente-ETL-Desarrollo/
├── backend/
│   ├── app/
│   │   ├── core/         # Configuración (settings, env vars)
│   │   ├── models/       # Cliente Gemini
│   │   ├── routers/      # Endpoints FastAPI
│   │   ├── schemas/      # Modelos Pydantic (request/response)
│   │   └── services/     # Lógica de generación, validación y documentación
│   ├── prompts/          # System prompts del modelo IA
│   ├── requirements.txt
│   └── .env.example
└── frontend/
    ├── src/
    │   ├── components/   # Componentes reutilizables
    │   ├── context/      # Estado global (EtlContext)
    │   ├── views/        # Páginas principales
    │   ├── css/          # Estilos
    │   └── validation/   # Validaciones del formulario
    └── package.json
```

---

## Ramas activas

| Rama | Descripción |
|------|-------------|
| `main` | Versión estable |
| `develop` | Integración — base para merge de features |
| `backend` | Motor de IA (Gemini) + integración con formulario |
| `formulario` | Formulario de creación ETL |
| `autenticacion` | Autenticación con Auth0 |
