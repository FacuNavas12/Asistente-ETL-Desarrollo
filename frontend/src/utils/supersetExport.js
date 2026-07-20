// Wrappers delgados: la construcción del ZIP de Superset (inferencia semántica,
// selección de charts, YAMLs, empaquetado) vive ahora en el backend
// (backend/app/services/superset_export/). Este archivo solo pide.
//
// El backend ya no persiste passwords de conexión (ver decisión de diseño),
// así que no puede verificar en vivo si el DWH ya tiene datos reales ni
// auto-configurar la conexión real en Superset — eso se hacía consultando
// conn_dwh directamente, y ya no hay password con el que abrir esa conexión.
// La conexión a la base de datos real en Superset se configura a mano, una
// sola vez, en Superset → Configuración → Conexiones a bases de datos.

/**
 * Pide al backend que arme el ZIP, lo importe en Superset y abre el dashboard
 * resultante. Ya no hay chequeo automático de "¿hay datos reales?" — se le
 * recuerda al usuario en un confirm antes de exportar, siempre (no solo
 * cuando se detecta falta de datos, porque ya no se puede detectar nada).
 * Cancelar aborta sin pegarle al backend.
 */
export async function exportEtlToSuperset(etl) {
  const proceed = window.confirm(
    "Antes de exportar: la conexión a la base de datos real del Data Warehouse " +
    "se configura a mano en Superset (Configuración → Conexiones a bases de datos) — " +
    "esta app no la configura por vos.\n\n" +
    "Si todavía no cargaste datos reales (corriendo el .ktr en Pentaho) o no conectaste " +
    "la base real en Superset, el dashboard se abre igual pero con datos de ejemplo.\n\n" +
    "¿Continuar con la exportación?"
  );
  if (!proceed) return;

  const apiBase = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
  const resp = await fetch(`${apiBase}/api/v1/etl/${etl.id}/superset/export`, {
    method: "POST",
  });

  if (!resp.ok) {
    const detail = await resp.json().catch(() => ({}));
    throw new Error(detail?.detail ?? `Error ${resp.status} al importar en Superset.`);
  }

  const { dashboard_url } = await resp.json();
  window.open(dashboard_url, "_blank", "noopener,noreferrer");
}
