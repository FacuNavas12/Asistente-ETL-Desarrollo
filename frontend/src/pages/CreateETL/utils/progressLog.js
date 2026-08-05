/**
 * D29 (docs/refactor/02-decisiones.md): helpers puros para el progreso del
 * job async — separados de CreateETL.jsx para poder testearlos con vitest
 * sin montar el componente (mismo criterio que utils/etlArtifacts.js).
 */

// Cuántas entradas "info" recientes se mantienen visibles antes de empezar a
// desvanecerlas. warning/error nunca se desvanecen — un aviso de reintento o
// un fallo de etapa es justo lo que el usuario tiene que seguir viendo.
const KEEP_RECENT_INFO = 6;

/**
 * D30/D32: mapea status.stages (array de {nombre,status,data,error}) a un
 * dict indexado por nombre — más cómodo de leer que iterar el array cada vez.
 *
 * @param {Array<{nombre: string, status: string, data: object|null, error: string|null}>} stagesArray
 * @returns {{origen_stg: object|null, stg_dwh: object|null}}
 */
export function stagesArrayToMap(stagesArray) {
  const map = { origen_stg: null, stg_dwh: null };
  for (const s of stagesArray ?? []) {
    map[s.nombre] = { status: s.status, data: s.data ?? null, error: s.error ?? null };
  }
  return map;
}

/**
 * Agrega eventos de progreso nuevos a la lista de logs ya mostrada en
 * EtlChecks, y recalcula qué entradas "info" quedan afuera de la ventana
 * reciente (se marcan fading — el caller las retira tras la transición CSS).
 *
 * @param {Array<{id: string, message: string, level: string, fading: boolean}>} prev
 * @param {Array<{seq: number, message: string, level: string}>} nuevos — eventos de ProgressEvent
 * @returns {Array<{id: string, message: string, level: string, fading: boolean}>}
 */
export function mergeProgressLogs(prev, nuevos) {
  const nuevosMapped = nuevos.map(e => ({
    id: `p${e.seq}`,
    message: e.message,
    level: e.level,
    fading: false,
  }));
  const merged = [...prev.map(l => ({ ...l, fading: false })), ...nuevosMapped];

  const infoPositions = merged
    .map((l, i) => (l.level === "info" ? i : -1))
    .filter(i => i !== -1);
  const fadeCount = infoPositions.length - KEEP_RECENT_INFO;
  for (let k = 0; k < fadeCount; k++) {
    merged[infoPositions[k]].fading = true;
  }

  return merged;
}
