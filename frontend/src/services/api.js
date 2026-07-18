export const API = "http://localhost:8000";

// timeoutMs es opcional — sin él, fetch espera indefinidamente (comportamiento
// previo, usado por polling y flujos en background). Pasarlo en llamadas
// interactivas donde el usuario está mirando un spinner y necesita feedback
// si el LLM tarda demasiado (ej. saturación 503 con reintentos del backend).
export async function apiFetch(path, options = {}, { timeoutMs } = {}) {
  const controller = new AbortController();
  const timer = timeoutMs
    ? setTimeout(() => controller.abort(), timeoutMs)
    : null;

  let res;
  try {
    res = await fetch(`${API}${path}`, { ...options, signal: controller.signal });
  } catch (err) {
    if (err.name === "AbortError") {
      throw new Error(
        "El servidor no respondió a tiempo (el modelo de IA puede estar saturado). " +
        "Tu formulario no se perdió — podés reintentar."
      );
    }
    throw err;
  } finally {
    if (timer) clearTimeout(timer);
  }

  if (!res.ok) {
    const body = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    const detail = body.detail;
    const isObj = detail && typeof detail === "object";
    const err = new Error(isObj ? (detail.message ?? `HTTP ${res.status}`) : (detail ?? `HTTP ${res.status}`));
    if (isObj && "raw_llm_data" in detail) err.rawLlmData = detail.raw_llm_data;
    throw err;
  }
  return res.json();
}
