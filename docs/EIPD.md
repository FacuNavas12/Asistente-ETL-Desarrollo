# Evaluación de Impacto en la Protección de Datos (EIPD)
## Sistema Acelerador de Procesos ETL

**Responsable del tratamiento:** Quanam S.A.  
**Elaborado por:** Equipo de Proyecto — Iñaki Delgado Pérez, Juan Manuel Barboza Acosta, Facundo Nahuel Navas Barrios  
**Fecha de elaboración:** Junio 2026  
**Versión:** 1.0  
**Marco normativo:** Ley N.º 18.331, Decreto N.º 414/009, Guías URCDP 2024

---

## 1. Descripción del sistema y finalidad del tratamiento

El sistema Acelerador de Procesos ETL es una herramienta de asistencia inteligente que ayuda a equipos técnicos a diseñar procesos de integración de datos (ETL) para Pentaho Data Integration (PDI). El sistema utiliza modelos de inteligencia artificial de terceros para analizar esquemas de bases de datos y proponer automáticamente estructuras de transformación y scripts de procesamiento.

**Finalidad declarada:** Generar propuestas de procesos ETL (estructuras staging, modelos DWH y scripts .ktr/.kjb para Pentaho PDI) a partir de metadatos de esquemas de bases de datos proporcionados por el usuario. Los metadatos se procesan exclusivamente para esta finalidad y no se reutilizan para otros fines.

**Usuarios del sistema:** Consultores técnicos de Quanam que trabajan en proyectos de integración de datos para clientes, principalmente organismos del Estado uruguayo.

---

## 2. Responsable y encargados del tratamiento

### 2.1 Responsable del tratamiento

| Campo | Detalle |
|---|---|
| Entidad | Quanam S.A. |
| Rol | Responsable del tratamiento (define finalidad y medios) |
| Actividad | Consultora de software para organismos del Estado uruguayo |
| Obligación | Responde ante la URCDP por toda vulneración, independientemente de la causa técnica |

### 2.2 Encargados del tratamiento

Los siguientes proveedores procesan los prompts enviados por el sistema en nombre de Quanam. Actúan como encargados del tratamiento bajo la Ley 18.331.

| Proveedor | Rol | Instrumento legal | Garantías relevantes |
|---|---|---|---|
| Google LLC (Cloud / Vertex AI) | Encargado — modelo IA principal | Google Cloud Data Processing Addendum (DPA) | No entrena modelos con datos de la API enterprise; retención acotada; región configurable |
| Anthropic PBC | Encargado — modelo IA alternativo (opción 1) | Anthropic Commercial API DPA | No entrena con datos de API comercial; retención 7 días; inferencia región CA configurable |

**Nota sobre el prototipo actual:** El prototipo utiliza la API consumer de Google (Google AI Studio). Para entornos de producción con clientes estatales se debe migrar a Google Cloud / Vertex AI para activar el DPA enterprise y el control de región geográfica.

---

## 3. Categorías de datos tratados

### 3.1 Datos que SÍ se envían a las APIs de IA

Los prompts enviados a los modelos de IA contienen exclusivamente **metadatos estructurales** del esquema de base de datos del cliente:

- Nombres de tablas (ej: `ventas`, `clientes`, `beneficiarios`)
- Nombres de columnas (ej: `dni_cliente`, `nombre_beneficiario`, `legajo_empleado`)
- Tipos de datos (ej: `VARCHAR(50)`, `INTEGER`, `DATE`)
- Reglas de transformación en texto natural (ej: "normalizar a mayúsculas")
- Descripción del objetivo del proceso en lenguaje natural

### 3.2 Datos que NO se envían

- Registros de producción con datos reales de personas
- Valores almacenados en las bases de datos del cliente
- Información personal identificable directa (nombres de personas, documentos, emails reales)
- Credenciales de acceso a bases de datos

### 3.3 Evaluación del carácter personal de los metadatos

La Ley 18.331 define dato personal como "toda información referida a personas físicas o jurídicas determinadas o determinables". Los nombres de columnas como `dni_cliente`, `nombre_beneficiario` o `legajo_empleado` son metadatos que describen la estructura de datos personales, no los datos en sí.

**Conclusión:** El riesgo real bajo la Ley 18.331 es **bajo**. Los metadatos estructurales no identifican a ninguna persona directa ni indirectamente. Sin embargo, su existencia evidencia que el sistema del cliente maneja datos personales, por lo que corresponde documentar y controlar su tratamiento.

---

## 4. Bases legales del tratamiento

| Base legal (Art. 9 Ley 18.331) | Aplicación al sistema ETL |
|---|---|
| Consentimiento del titular | No aplica (no se tratan datos de personas, sino metadatos de esquemas) |
| Ejecución de contrato | Aplica: el tratamiento es necesario para prestar el servicio de consultoría ETL contratado por el cliente |
| Interés legítimo | Aplica subsidiariamente: los metadatos de esquema son información técnica del sistema del cliente, no de sus usuarios finales |

---

## 5. Transferencias internacionales de datos

### 5.1 Opción activa: API Google AI Studio (prototipo)

| Aspecto | Detalle |
|---|---|
| País receptor | Estados Unidos |
| Reconocimiento de adecuación UE | No tiene reconocimiento formal |
| Instrumento de transferencia | Términos de servicio de Google (no DPA enterprise) |
| Riesgo URCDP | Medio — se debe documentar la base de transferencia |
| Mitigación | Metadatos no son PII directa; Google TOS incluye cláusulas de privacidad |

### 5.2 Opción producción recomendada: Google Cloud / Vertex AI

| Aspecto | Detalle |
|---|---|
| País receptor | Configurable: `us-central1`, `europe-west4` (UE), etc. |
| Para clientes estatales | Antel GDC — infraestructura en Uruguay (sin transferencia internacional) |
| Instrumento de transferencia | Google Cloud DPA enterprise (firmado por Quanam) |
| Riesgo URCDP | Bajo con DPA firmado; eliminado con Antel GDC |

### 5.3 Opción Anthropic (cuando se activa)

| Aspecto | Detalle |
|---|---|
| País receptor | Canadá (cuando se configura `inference_geo="ca"`) |
| Reconocimiento UE | Canadá tiene reconocimiento de adecuación PIPEDA equivalente a Uruguay |
| Instrumento de transferencia | Anthropic Commercial API DPA |
| Riesgo URCDP | Bajo — jurisdicción con adecuación equivalente; no sujeto a US CLOUD Act de igual forma |

---

## 6. Evaluación de riesgos y medidas técnicas implementadas

### 6.1 Matriz de riesgos

| Riesgo | Probabilidad | Impacto | Nivel | Medida implementada |
|---|---|---|---|---|
| Exposición de metadatos de esquema a terceros no autorizados | Baja | Medio | Bajo | API keys en variables de entorno; TLS en tránsito; Auth API en producción |
| Acceso no autorizado a la API del sistema | Media | Alto | Medio | Middleware de autenticación JWT configurable (AUTH_REQUIRED) |
| Credenciales de BD del cliente expuestas en logs | Baja | Alto | Medio | PasswordFilter redacta credenciales antes de escribir logs |
| Retención excesiva de metadatos en logs del sistema | Media | Medio | Medio | Rotación diaria de logs; retención 90 días; sin prompts en logs |
| Retención excesiva de datos en navegador del usuario | Media | Bajo | Bajo | TTL 30 días en localStorage; limpieza automática al logout |
| Accidente de integridad: envío accidental de datos reales | Baja | Alto | Medio | El sistema solicita metadatos de esquema, no datos de registros |
| Fuga por vulnerabilidad en proveedor externo | Muy baja | Alto | Bajo | DPA enterprise con proveedor; no se envía PII directa |

### 6.2 Controles técnicos implementados

| Control | Ubicación | Estado |
|---|---|---|
| Gestión de API keys por variables de entorno | `backend/app/core/config.py` | ✅ Implementado |
| Exclusión de `.env` del repositorio | `.gitignore` raíz | ✅ Implementado |
| Cifrado Fernet de credenciales de BD | `backend/app/core/crypto.py` | ✅ Implementado |
| Redacción de credenciales en logs | `backend/app/core/log_filters.py` | ✅ Implementado |
| Logs sin contenido de prompts | `backend/app/models/gemini_client.py` | ✅ Implementado |
| Rotación y retención de logs (90 días) | `backend/app/main.py` | ✅ Implementado |
| Middleware de autenticación JWT (configurable) | `backend/app/core/auth.py` | ✅ Implementado (inactivo en dev) |
| TTL 30 días en localStorage del navegador | `frontend/src/context/EtlContext.jsx` | ✅ Implementado |
| Limpieza de datos locales en logout | `frontend/src/components/ui/LogoutButton.jsx` | ✅ Implementado |
| Validación de esquemas Pydantic en endpoints | `backend/app/schemas/` | ✅ Implementado |
| Protección SQL injection vía ORM | `backend/app/services/db_connector.py` | ✅ Implementado |
| CORS restringido a origen declarado | `backend/app/main.py` | ✅ Implementado |

---

## 7. Principios de la Ley 18.331 — cumplimiento por diseño

| Principio | Medida de cumplimiento | Estado |
|---|---|---|
| **Finalidad** | Los metadatos se envían exclusivamente para generación ETL. Documentado en esta EIPD y en la política de uso aceptable. | ✅ |
| **Veracidad** | El sistema no modifica ni almacena los metadatos de esquema recibidos; solo los reenvía al modelo IA. | ✅ |
| **Minimización** | Solo se incluyen en los prompts los campos de esquema necesarios para la generación ETL (nombre, tipo, regla). No se transmiten datos de registros ni atributos no relevantes. | ✅ |
| **Seguridad** | API keys en variables de entorno; credenciales cifradas; logs sin PII; autenticación JWT en producción; TLS en tránsito. | ✅ |
| **Responsabilidad** | Presente documento. Decisiones de diseño documentadas en código y CLAUDE.md. Proveedores con DPA enterprise para producción. | ✅ |
| **Limitación de conservación** | Logs: rotación diaria, retención 90 días. Datos en navegador: TTL 30 días, limpieza en logout. Proveedor IA: retención 7 días (Anthropic) / configurable (Google). | ✅ |

---

## 8. Derechos de los interesados

Los usuarios del sistema (consultores de Quanam) tienen los siguientes derechos bajo la Ley 18.331. Dado que el sistema no trata datos de los clientes finales de Quanam (solo metadatos de esquemas), los derechos de acceso, rectificación y supresión se ejercen a nivel de los datos de los consultores autenticados en el sistema.

| Derecho | Canal de ejercicio |
|---|---|
| Acceso | Solicitar a DPO o referente de privacidad de Quanam |
| Rectificación | Idem |
| Supresión | Idem; los datos en navegador se eliminan automáticamente al cerrar sesión |
| Oposición | Idem |

---

## 9. Checklist de aprobación previo al despliegue

Los siguientes controles deben verificarse antes de que el sistema entre en producción con un cliente estatal:

- [ ] DPA firmado con proveedor IA activo (Google Cloud DPA o Anthropic Commercial DPA)
- [ ] `AUTH_REQUIRED=true` configurado en el entorno de producción
- [ ] `AUTH_JWKS_URL`, `AUTH_AUDIENCE`, `AUTH_ISSUER` configurados para el proveedor de identidad del cliente
- [ ] API keys gestionadas como secretos en el sistema de secretos del entorno de producción (no en archivos `.env`)
- [ ] HTTPS activo en todos los endpoints
- [ ] CORS configurado con los dominios de producción del cliente (no wildcard)
- [ ] Para clientes con restricciones de soberanía: migración a Antel GDC o Vertex AI con región configurada
- [ ] Política de uso aceptable del sistema comunicada al equipo del cliente
- [ ] Esta EIPD revisada y actualizada si cambia el proveedor IA o la arquitectura de despliegue

---

## 10. Historial de revisiones

| Versión | Fecha | Cambio |
|---|---|---|
| 1.0 | Junio 2026 | Versión inicial — prototipo Sprint 1 con Google AI Studio y Auth0 |

---

*Este documento debe actualizarse ante cualquier cambio en: proveedor de IA, región de procesamiento, arquitectura de autenticación, o tipos de datos enviados en los prompts.*
