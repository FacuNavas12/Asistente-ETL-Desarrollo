// Wrappers delgados: la construcción del ZIP de Superset (inferencia semántica,
// selección de charts, YAMLs, empaquetado) vive ahora en el backend
// (backend/app/services/superset_export/). Este archivo solo pide.

/**
 * Estado real (existencia + row count, sin filas) de las tablas DWH esperadas
 * para este ETL, contra conn_dwh. available=false si el backend no puede
 * resolver conn_dwh (ETL viejo, o nunca se configuró) — nunca lanza, el
 * caller trata ese caso como "no se puede confirmar nada" y sigue de largo.
 */
export async function checkDwhStatus(etlId) {
  const apiBase = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";
  try {
    const resp = await fetch(`${apiBase}/api/v1/etl/${etlId}/superset/dwh-status`);
    if (!resp.ok) return { available: false, hasData: false, tables: [] };
    return await resp.json();
  } catch {
    return { available: false, hasData: false, tables: [] };
  }
}

/**
 * Pide al backend que arme el ZIP, lo importe en Superset y abre el dashboard
 * resultante. Chequeo on-click (no gatea el botón): si conn_dwh está configurada
 * y las tablas DWH todavía no tienen filas reales, confirma con el usuario antes
 * de abrir en modo demo — cancelar aborta sin pegarle al backend.
 */
export async function exportEtlToSuperset(etl) {
  const status = await checkDwhStatus(etl.id);
  if (status.available && !status.hasData) {
    const proceed = window.confirm(
      "Todavía no se encontraron datos reales en las tablas del DWH (¿corriste el job en Pentaho?).\n\n¿Abrir igual en modo demo, con datos de ejemplo?"
    );
    if (!proceed) return;
  }

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
