import { apiFetch, API } from "./api";

export async function inferStructures({ source_schema_json, process_goal, business_rules }) {
  return apiFetch("/api/v1/etl/infer-structures", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_schema_json, process_goal, business_rules }),
  });
}

export async function refineInference({
  source_schema_json,
  process_goal,
  business_rules,
  previous_stg,
  previous_dwh,
  previous_dim_contracts,
  correction,
  correction_history,
}) {
  return apiFetch("/api/v1/etl/infer-structures/refine", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      source_schema_json,
      process_goal,
      business_rules,
      previous_stg,
      previous_dwh,
      previous_dim_contracts,
      correction,
      correction_history,
    }),
  });
}

export async function generateFromInference({
  descripcionObjetivo,
  origenTables,
  stg_definition,
  dwh_model,
  reglasNegocio,
  dim_contracts,
}) {
  return apiFetch("/api/v1/etl/generate-from-inference", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ descripcionObjetivo, origenTables, stg_definition, dwh_model, reglasNegocio, dim_contracts }),
  });
}

// ── Flujo async: modelo + conexiones destino en paralelo ─────────────────────
// generateAsync dispara el modelo en background y devuelve job_id de inmediato
// (no espera al modelo) para que el cliente arranque el formulario de
// conexiones al mismo tiempo. submitJobConnections se llama con el mapa
// COMPLETO acumulado hasta el momento (el endpoint reemplaza el mapa entero,
// no hace merge). getJobStatus se polea hasta build_status "built"/"failed".

// reuse_stage_1 (D31, docs/refactor/02-decisiones.md): salida cruda del
// modelo para origen→STG de un intento anterior, tal como llega en
// stages[].data de un status previo. Si se pasa, el backend saltea la
// llamada al modelo de esa etapa (y sus repairs) — pero NO saltea la
// auditoría de DDL ni la etapa STG→DWH. null (default) = flujo normal.
export async function generateAsync({
  descripcionObjetivo, origenTables, stg_definition, dwh_model, reglasNegocio,
  dim_contracts, reuse_stage_1 = null,
}) {
  return apiFetch("/api/v1/etl/generate-async", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      descripcionObjetivo, origenTables, stg_definition, dwh_model, reglasNegocio,
      dim_contracts, reuse_stage_1,
    }),
  });
}

export async function submitJobConnections(jobId, connections) {
  return apiFetch(`/api/v1/etl/${jobId}/connections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(connections),
  });
}

export async function getJobStatus(jobId) {
  return apiFetch(`/api/v1/etl/${jobId}/status`);
}

// Re-adapta la conexión destino (staging/DWH) de un ETL ya generado y
// persistido — reconstruye el .ktr desde el raw_data guardado (form_data.rawLlmData)
// sin volver a llamar al LLM. Mismo shape de body que submitJobConnections
// (conn_staging/conn_dwh como InlineConnection o ausentes = "Completar en Spoon").
export async function rebuildEtlConnections(etlId, connections) {
  return apiFetch(`/api/etls/${etlId}/connections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(connections),
  });
}

// connections_map (D-conexión-build-from-raw, docs/refactor/02-decisiones.md):
// antes este endpoint no tenía forma de recibir conexiones y "Reutilizar
// respuesta" siempre entregaba el .ktr con placeholder aunque el usuario ya
// las hubiera completado en el formulario. null (default) preserva el
// comportamiento histórico — mismo shape que submitJobConnections.
// stg_ddl/dwh_ddl: sin esto, "Reutilizar respuesta" entregaba el ETL sin
// DDL — ResultView (EtlDetail) oculta esa sección sin el texto. El caller
// ya lo tiene en memoria (inferResult.stg_ddl/dwh_ddl) desde la etapa de
// Inferencia; acá solo se reenvía.
export async function buildFromRaw(raw_llm_data, dim_contracts = [], connections_map = null, stg_ddl = null, dwh_ddl = null) {
  return apiFetch("/api/v1/etl/build-from-raw", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_llm_data, dim_contracts, connections_map, stg_ddl, dwh_ddl }),
  });
}

export async function generateFromInferenceStream(
  { descripcionObjetivo, origenTables, stg_definition, dwh_model, reglasNegocio, dim_contracts },
  { onLlmDone, onKtrLog, onResult, onError } = {},
) {
  const res = await fetch(`${API}/api/v1/etl/generate-from-inference/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ descripcionObjetivo, origenTables, stg_definition, dwh_model, reglasNegocio, dim_contracts }),
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
        err.rawLlmData = event.raw_llm_data ?? null;
        onError?.(event.message);
        throw err;
      }
    }
  }
}
