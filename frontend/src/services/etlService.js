import { apiFetch, API } from "./api";

export async function inferStructures({ source_structure, process_description, business_rules }) {
  return apiFetch("/api/v1/etl/infer-structures", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_structure, process_description, business_rules }),
  });
}

export async function refineInference({
  source_structure,
  process_description,
  business_rules,
  current_stg,
  current_dwh,
  correction,
  history,
}) {
  return apiFetch("/api/v1/etl/infer-structures/refine", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_structure,
      process_description,
      business_rules,
      current_stg,
      current_dwh,
      correction,
      history,
    }),
  });
}

export async function generateFromInference({
  descripcionObjetivo,
  origenTables,
  stg_definition,
  dwh_model,
  reglasNegocio,
}) {
  return apiFetch("/api/v1/etl/generate-from-inference", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ descripcionObjetivo, origenTables, stg_definition, dwh_model, reglasNegocio }),
  });
}

export async function generateFromInferenceStream(
  { descripcionObjetivo, origenTables, stg_definition, dwh_model, reglasNegocio },
  { onLlmDone, onKtrLog, onResult, onError } = {},
) {
  const res = await fetch(`${API}/api/v1/etl/generate-from-inference/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ descripcionObjetivo, origenTables, stg_definition, dwh_model, reglasNegocio }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const text = line.slice(6).trim();
      if (!text) continue;

      let event;
      try { event = JSON.parse(text); } catch { continue; }

      if (event.type === "llm_done")  { onLlmDone?.(); }
      else if (event.type === "ktr_log") { onKtrLog?.(event.message); }
      else if (event.type === "result")  { onResult?.(event.data); }
      else if (event.type === "error")   {
        const err = new Error(event.message);
        onError?.(event.message);
        throw err;
      }
    }
  }
}
