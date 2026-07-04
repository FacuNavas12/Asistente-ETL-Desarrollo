export const API = "http://localhost:8000";

export async function apiFetch(path, options = {}) {
  const res = await fetch(`${API}${path}`, options);
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
