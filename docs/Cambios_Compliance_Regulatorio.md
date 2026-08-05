# Cambios de Compliance Regulatorio — Sistema Acelerador de Procesos ETL

**Proyecto:** Acelerador de Procesos ETL  
**Fecha:** Junio 2026  
**Autores:** Iñaki Delgado Pérez, Juan Manuel Barboza Acosta, Facundo Nahuel Navas Barrios  
**Marco normativo:** AGESIC Marco de Ciberseguridad 5.0 · Ley N.º 18.331 · Decreto N.º 66/025

---

## Contexto: Por qué estos cambios son necesarios

Quanam opera principalmente como consultora de software para organismos del Estado uruguayo. Cuando un ente estatal contrata a Quanam para desarrollar o implantar un sistema, el contrato transfiere contractualmente la responsabilidad de cumplimiento normativo a lo largo de toda la cadena de proveedores (Artículo 18, Decreto N.º 66/025).

El sistema Acelerador de Procesos ETL, al ser desarrollado para implantarse en entornos estatales, debe poder demostrar adecuación a dos marcos normativos complementarios:

1. **Marco de Ciberseguridad AGESIC 5.0** (Decreto N.º 66/025): regula infraestructura, gestión de incidentes, controles de seguridad y auditorías periódicas. Organiza 72 requisitos en seis funciones: Gobernar, Identificar, Proteger, Detectar, Responder y Recuperar.

2. **Ley N.º 18.331 y Decreto N.º 414/009** (supervisión URCDP): regula el tratamiento de datos personales. Los metadatos de esquemas ETL (nombres de tablas y columnas como `dni_cliente`, `legajo_empleado`) son considerados información que describe el tratamiento de datos personales y quedan dentro del alcance de la ley.

**Sin estos controles, el sistema no puede pasar a producción en entornos de clientes estatales.**

Los cambios documentados en este archivo abordan cuatro brechas concretas identificadas en la auditoría de cumplimiento del sistema:

| # | Brecha identificada | Marco normativo afectado |
|---|---|---|
| 1 | Logs sin rotación ni política de retención | Ley 18.331 — Limitación de conservación |
| 2 | API sin autenticación (endpoints abiertos) | AGESIC 5.0 — Función Proteger |
| 3 | Metadatos de clientes en localStorage sin expiración ni limpieza | Ley 18.331 — Seguridad y Limitación de conservación |
| 4 | Ausencia de Evaluación de Impacto en Protección de Datos | URCDP — Buenas prácticas anticipatorias |

---

## Cambio 1 — Política de retención y rotación de logs del backend

### Archivos modificados
- `backend/app/main.py`

### Qué se cambió

Se reemplazó el `FileHandler` simple de Python (que escribe en un único archivo que crece indefinidamente) por un `TimedRotatingFileHandler` con las siguientes características:

```python
# Antes
logging.FileHandler(_log_dir / "generaciones.log", encoding="utf-8")

# Después
TimedRotatingFileHandler(
    _log_dir / "generaciones.log",
    when="midnight",    # rota a medianoche UTC
    interval=1,         # un nuevo archivo por día
    backupCount=90,     # conserva los últimos 90 archivos = 90 días
    encoding="utf-8",
    utc=True,
)
```

Los archivos rotados se nombran automáticamente con el sufijo de fecha: `generaciones.log.2026-06-03`, `generaciones.log.2026-06-04`, etc. Cuando se supera el límite de 90 archivos, Python elimina automáticamente el más antiguo.

### Qué implica técnicamente

- El archivo `generaciones.log` activo contiene siempre solo el día en curso.
- Los archivos de días anteriores se conservan hasta 90 días y luego se eliminan automáticamente.
- No se requiere ningún script ni tarea programada externa para la limpieza; el propio mecanismo de Python la gestiona.
- El contenido de los logs sigue siendo el mismo (modelo utilizado, tokens enviados/recibidos, latencia), lo que cambia es el ciclo de vida del archivo.

### Qué cumplimiento normativo se satisface

**Ley 18.331 — Principio de Limitación de Conservación (Art. 8):**
> "Los datos no pueden conservarse en forma que permita identificar a los titulares durante un período mayor al necesario para los fines del tratamiento."

El backend registra metadatos operacionales de cada llamada a la API de IA (no los prompts completos, que ya estaban excluidos por diseño). Estos metadatos describen indirectamente el esquema del cliente procesado. La norma exige que el período de retención esté definido y documentado; el sistema ahora lo tiene: **90 días**.

**Marco de Ciberseguridad AGESIC 5.0 — Función Detectar:**
Los logs operacionales son el mecanismo principal para detectar anomalías de uso (accesos inusuales, patrones de llamadas sospechosos). La rotación garantiza que esta función no se degrade por archivos de log de tamaño inmanejable, y que haya evidencia forense disponible durante 90 días si se requiere una auditoría.

**Decreto N.º 66/025 — Art. 16 y 17 (Auditorías):**
Cuando AGESIC realice una auditoría, el sistema puede demostrar que la retención de registros operacionales está controlada y es proporcional a la necesidad.

---

## Cambio 2 — Autenticación JWT configurable en la API

### Archivos modificados / creados
- `backend/app/core/auth.py` *(nuevo)*
- `backend/app/core/config.py`
- `backend/app/routers/ai.py`
- `backend/app/routers/connections.py`
- `backend/requirements.txt`
- `backend/.env.example`
- `frontend/src/hooks/useAuthFetch.js` *(nuevo)*
- `frontend/src/auth0/AuthProvider.jsx`
- `frontend/src/pages/CreateETL/CreateETL.jsx`
- `frontend/src/pages/CreateJob/CrearJob.jsx`
- `frontend/.env.example`

### Qué se cambió

#### Problema previo
Los endpoints FastAPI (`/api/v1/etl/*`, `/api/connections/*`) no tenían ningún control de acceso. Cualquier persona que conociera la URL del servidor podía llamar al sistema directamente, sin autenticarse, generando costos y accediendo a los esquemas de bases de datos de los clientes. La autenticación con Auth0 existía solo en el frontend (navegador), pero no protegía la API en sí.

#### Diseño del nuevo sistema de autenticación

El sistema de autenticación se diseñó con tres principios guía:

**a) Intercambiable sin modificar código de negocio.** El prototipo usa Auth0. En producción, cada organización cliente usará su propio sistema de identidad (Azure Active Directory, Keycloak, LDAP, etc.). El mecanismo de autenticación se configura 100% por variables de entorno; cambiar de proveedor no requiere tocar ningún router ni componente.

**b) Activable progresivamente.** En desarrollo local, `AUTH_REQUIRED=false` (valor por defecto) desactiva la validación completamente. El prototipo sigue funcionando exactamente igual que antes. Cuando se despliega en producción, se activa con `AUTH_REQUIRED=true` y se configuran las variables del proveedor.

**c) Estándar abierto.** La implementación usa el protocolo OIDC/JWT estándar (tokens RS256 validados por JWKS), compatible con todos los proveedores de identidad modernos.

#### Backend: el módulo `auth.py`

```
backend/app/core/auth.py
```

Implementa una función `require_auth` que actúa como dependencia de FastAPI. Su lógica es:

1. Lee `AUTH_REQUIRED` de la configuración.
2. Si es `false`, retorna inmediatamente sin validar nada (modo desarrollo).
3. Si es `true`, extrae el Bearer token del header `Authorization`.
4. Si no hay token, retorna HTTP 401.
5. Descarga el JWKS (JSON Web Key Set) del proveedor configurado en `AUTH_JWKS_URL`.
6. Valida la firma del token, la audiencia (`AUTH_AUDIENCE`) y el emisor (`AUTH_ISSUER`).
7. Si la validación falla, retorna HTTP 401 con el motivo específico (expirado, audiencia inválida, firma incorrecta).
8. Si la validación pasa, retorna el payload del token (disponible para los handlers si lo necesitan).

El JWKS se cachea en memoria durante 10 minutos para no refetchar en cada request. Si el fetch del JWKS falla pero hay cache anterior, usa el cache (resiliencia ante indisponibilidad temporal del proveedor).

**Compatibilidad de proveedores de identidad por variable de entorno:**

| Proveedor | `AUTH_JWKS_URL` |
|---|---|
| Auth0 (prototipo) | `https://<tenant>.auth0.com/.well-known/jwks.json` |
| Azure AD / Entra ID (org corporativa) | `https://login.microsoftonline.com/<tenant>/discovery/v2.0/keys` |
| Keycloak (on-premise) | `https://<host>/realms/<realm>/protocol/openid-connect/certs` |
| Google Workspace | `https://www.googleapis.com/oauth2/v3/certs` |

#### Backend: aplicación a los routers

La protección se aplica al nivel del router completo, no endpoint por endpoint. Esto garantiza que cualquier nuevo endpoint que se agregue quede protegido automáticamente:

```python
# ai.py
router = APIRouter(tags=["ETL"], dependencies=[Depends(require_auth)])

# connections.py
router = APIRouter(prefix="/api/connections", tags=["connections"], dependencies=[Depends(require_auth)])
```

#### Frontend: el hook `useAuthFetch`

```
frontend/src/hooks/useAuthFetch.js
```

Envuelve la función nativa `fetch()` del navegador para incluir automáticamente el Bearer token en cada llamada a la API. Su comportamiento:

- Si `VITE_AUTH_REQUIRED=false` (desarrollo): llama a `fetch()` directamente, sin cambios.
- Si `VITE_AUTH_REQUIRED=true`: obtiene el token JWT del proveedor configurado y añade `Authorization: Bearer <token>` al header antes de la llamada.

Este hook abstrae completamente el mecanismo de obtención del token. En producción con org auth, solo hay que cambiar la implementación del hook (no los componentes que lo usan). Los 6 calls a la API en `CreateETL.jsx` y `CrearJob.jsx` usan `authFetch()` en lugar de `fetch()`.

#### Dependencia agregada

Se añadió `PyJWT==2.10.1` a `requirements.txt`. Esta librería valida tokens JWT RS256 usando el backend criptográfico `cryptography` que ya estaba instalado, por lo que no se agregan dependencias transitivas nuevas.

### Qué cumplimiento normativo se satisface

**Marco de Ciberseguridad AGESIC 5.0 — Función Proteger (PR):**
> "Implementar salvaguardas para garantizar la prestación de los servicios críticos."

Los requisitos de la función Proteger incluyen gestión de identidades y accesos (PR.AA), autenticación de usuarios (PR.AA-02) y protección de datos (PR.DS). Sin autenticación en la API, ninguno de estos requisitos puede demostrarse cumplido.

**Ley 18.331 — Principio de Seguridad (Art. 10):**
> "El responsable del tratamiento debe adoptar las medidas técnicas y organizativas necesarias para garantizar la seguridad de los datos."

Un endpoint de API sin autenticación que expone esquemas de bases de datos de clientes estatales es una violación directa de este principio. La autenticación JWT es la medida técnica estándar para proteger APIs REST.

**Decreto N.º 66/025 — Marco de Ciberseguridad obligatorio:**
El artículo 18 establece que los proveedores tercerizados (como Quanam) deben cumplir el Marco de Ciberseguridad. La función Proteger es uno de los seis pilares del marco; sin ella el sistema no puede considerarse conforme.

---

## Cambio 3 — Protección del almacenamiento local en el navegador

### Archivos modificados
- `frontend/src/context/EtlContext.jsx`
- `frontend/src/components/ui/LogoutButton.jsx`
- `frontend/src/components/ui/UserOptions.jsx`

### Qué se cambió

#### Problema previo
Los resultados de generación ETL y los jobs se guardaban en `localStorage` del navegador sin ningún límite de tiempo ni mecanismo de limpieza. El `localStorage` es persistente por diseño: los datos sobreviven al cierre del navegador, al reinicio del sistema operativo, y permanecen hasta que el usuario los borra manualmente o el sitio los elimina explícitamente.

Esto significaba que metadatos de esquemas de clientes (nombres de tablas y columnas como `nombre_beneficiario`, `dni_cliente`) podían permanecer indefinidamente en el dispositivo del consultor, incluso después de que el proyecto de cliente terminara, en texto plano visible en las herramientas de desarrollo del navegador.

#### Solución implementada: TTL de 30 días

Se modificó el formato de almacenamiento para incluir un envoltorio con timestamp:

```javascript
// Antes (sin control de tiempo)
localStorage.setItem(key, JSON.stringify(list))

// Después (con envoltorio TTL)
localStorage.setItem(key, JSON.stringify({ data: list, savedAt: Date.now() }))
```

Al cargar los datos, se verifica si superaron los 30 días. Si es así, se eliminan automáticamente:

```javascript
if (Date.now() - raw.savedAt > LIST_TTL) {  // LIST_TTL = 30 * 24 * 60 * 60 * 1000
    localStorage.removeItem(key);
    return [];
}
```

Los registros anteriores al cambio (sin envoltorio) se migran transparentemente sin perder datos: el código detecta el formato antiguo y lo trata como una lista directa.

#### Solución implementada: limpieza en logout

Se añadió la función `clearAll()` al contexto ETL. Esta función:
1. Elimina `etl_list` del `localStorage`
2. Elimina `job_list` del `localStorage`
3. Elimina `etl_draft` del `sessionStorage`
4. Limpia el estado React en memoria (las listas quedan vacías en la sesión activa)

Ambos componentes de logout del sistema (`LogoutButton.jsx` y `UserOptions.jsx`) llaman a `clearAll()` antes de ejecutar el logout de Auth0:

```javascript
const handleLogout = () => {
    clearAll();  // limpia datos antes de cerrar sesión
    logout({ logoutParams: { returnTo: window.location.origin } });
};
```

### Qué implica para el usuario

- Los ETLs y jobs generados siguen siendo visibles durante la sesión y hasta 30 días después.
- Al cerrar sesión (logout), los datos se eliminan inmediatamente del dispositivo.
- Si un consultor no usa el sistema durante más de 30 días, los datos expiran automáticamente la próxima vez que abra la aplicación.
- No hay pérdida de funcionalidad: el historial de trabajo reciente sigue disponible.

### Qué cumplimiento normativo se satisface

**Ley 18.331 — Principio de Seguridad (Art. 10):**
Los datos almacenados en el dispositivo del usuario son responsabilidad del sistema. Mantener metadatos de clientes en texto plano indefinidamente en el navegador no es una medida técnica adecuada de seguridad.

**Ley 18.331 — Principio de Limitación de Conservación (Art. 8):**
El período de 30 días es proporcional al ciclo de trabajo de un consultor que genera un ETL y lo entrega. Retener datos más tiempo no es necesario para los fines del tratamiento.

**Marco AGESIC 5.0 — Función Proteger (PR.DS — Protección de datos):**
Los datos deben estar protegidos en reposo. El `localStorage` sin expiración es datos en reposo sin control. La expiración automática y la limpieza en logout son controles proporcionales al nivel de sensibilidad de los metadatos tratados.

---

## Cambio 4 — Evaluación de Impacto en Protección de Datos (EIPD)

### Archivos creados
- `docs/EIPD.md`

### Qué es la EIPD y por qué es necesaria

La URCDP recomienda elaborar una Evaluación de Impacto en Protección de Datos antes de utilizar servicios de IA en la nube cuando existe posibilidad de que los datos procesados estén relacionados con personas. La EIPD no es actualmente una obligación legal explícita para proveedores privados en Uruguay, pero:

1. **Anticipa el marco regulatorio en evolución.** Las recomendaciones de AGESIC sobre IA Generativa (elaboradas en el marco del Art. 74 de la Ley 20.212) son buenas prácticas que probablemente se conviertan en obligaciones formales. Adoptarlas ahora reduce el riesgo de que el sistema requiera modificaciones significativas.

2. **Es evidencia ante auditorías.** Su valor no está en la complejidad del análisis, sino en que su existencia demuestra que el equipo evaluó el impacto antes del despliegue. Ante una inspección de la URCDP, es el documento que acredita que el responsable cumplió su deber de diligencia.

3. **Es una exigencia contractual implícita con clientes estatales.** Los entes estatales que contratan a Quanam están obligados por el Decreto 66/025 y transfieren esa obligación a sus proveedores. Una EIPD es parte de la documentación que un ente estatal puede solicitar antes de aprobar el despliegue del sistema en su infraestructura.

### Contenido de la EIPD creada

El documento `docs/EIPD.md` cubre los siguientes bloques, siguiendo el esquema de las guías de la URCDP:

**Sección 1 — Descripción del sistema y finalidad:** Define con precisión para qué se usan los datos (generación ETL) y qué queda fuera del alcance. La finalidad declarada es la base legal de todo el tratamiento.

**Sección 2 — Responsable y encargados:** Establece la cadena de responsabilidad bajo la Ley 18.331. Quanam es el responsable del tratamiento; Google y Anthropic son encargados cuando procesan los prompts. Incluye la tabla de instrumentos legales (DPAs) que formalizan esta relación.

**Sección 3 — Categorías de datos:** Distingue explícitamente entre lo que SÍ se envía (metadatos estructurales) y lo que NO se envía (datos reales de personas). Esta distinción es el argumento central ante la URCDP para justificar el bajo nivel de riesgo del sistema.

**Sección 4 — Bases legales del tratamiento:** Identifica los artículos de la Ley 18.331 que habilitan el tratamiento: ejecución del contrato de consultoría e interés legítimo.

**Sección 5 — Transferencias internacionales:** Evalúa cada opción de despliegue (Google AI Studio actual, Vertex AI para producción, Antel GDC para soberanía, Anthropic con región canadiense) desde la perspectiva del análisis de adecuación del país receptor que exige la URCDP.

**Sección 6 — Evaluación de riesgos y controles:** Matriz de riesgos con probabilidad, impacto y medida implementada para cada escenario. Tabla de todos los controles técnicos del sistema con su estado de implementación actual.

**Sección 7 — Principios Ley 18.331:** Verifica el cumplimiento de cada uno de los principios de la ley (Finalidad, Veracidad, Minimización, Seguridad, Responsabilidad, Limitación de conservación) con la evidencia de diseño que respalda cada afirmación.

**Sección 9 — Checklist de producción:** Lista de verificación que debe completarse antes de que el sistema entre en producción con un cliente estatal. Incluye ítems como DPA firmado, autenticación activa, HTTPS, CORS configurado y migración a Vertex AI o Antel GDC si el cliente lo requiere.

---

## Estado del cumplimiento normativo antes y después

### Marco de Ciberseguridad AGESIC 5.0

| Función | Requisito | Antes | Después |
|---|---|---|---|
| **Proteger** | Autenticación de acceso a la API | ❌ Sin autenticación | ✅ JWT configurable |
| **Proteger** | Datos protegidos en el cliente | ⚠️ Sin expiración | ✅ TTL 30 días + limpieza |
| **Detectar** | Logs operacionales disponibles | ⚠️ Sin retención definida | ✅ 90 días |
| **Gobernar** | Documentación de decisiones de diseño | ⚠️ Parcial | ✅ EIPD + este documento |
| **Proteger** | Credenciales cifradas | ✅ Fernet | ✅ Sin cambios |
| **Proteger** | Secrets en variables de entorno | ✅ pydantic-settings | ✅ Sin cambios |
| **Detectar** | Logs sin credenciales | ✅ PasswordFilter | ✅ Sin cambios |

### Ley 18.331 / URCDP

| Principio | Antes | Después |
|---|---|---|
| Finalidad | ✅ Solo metadatos estructurales | ✅ Sin cambios |
| Minimización | ✅ Solo campos necesarios en prompts | ✅ Sin cambios |
| Seguridad | ⚠️ API abierta, localStorage sin límite | ✅ Auth JWT + TTL + limpieza |
| Limitación de conservación | ❌ Logs infinitos, localStorage infinito | ✅ 90 días logs, 30 días cliente |
| Responsabilidad | ⚠️ Sin EIPD | ✅ EIPD elaborada |

---

## Lo que queda pendiente para producción

Estos cambios no eliminan todas las brechas. Lo siguiente permanece como requisito para el despliegue productivo con clientes estatales:

### Técnico
1. **Migrar de Google AI Studio (consumer API) a Google Cloud / Vertex AI.** El prototipo usa la API gratuita de Google que no tiene DPA enterprise. Para producción, se necesita la API de Vertex AI que incluye control de región y garantías contractuales de no-entrenamiento. El cambio en el código es mínimo (endpoint y método de autenticación del SDK).

2. **Configurar `AUTH_REQUIRED=true` en el entorno de producción.** El middleware existe y está implementado; solo hay que activarlo con las variables de entorno del proveedor de identidad del cliente.

3. **HTTPS obligatorio en producción.** Los cambios actuales funcionan sobre HTTP en desarrollo. En producción, TLS es un requisito del Marco AGESIC y de la Ley 18.331 para datos en tránsito.

4. **CORS con dominios específicos.** Actualmente configurado solo para `localhost:5173`. En producción, debe configurarse con el dominio real del frontend.

### Documental
5. **Firmar el DPA con Google Cloud** antes del primer despliegue productivo.
6. **Actualizar la EIPD** si cambia el proveedor de IA o la arquitectura de despliegue.
7. **Comunicar la política de uso aceptable del sistema** al equipo del cliente.

---

*Documento elaborado como parte del Sprint de compliance regulatorio del proyecto Acelerador de Procesos ETL — Universidad ORT Uruguay, Facultad de Ingeniería, Abril–Junio 2026.*
