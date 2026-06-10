import { apiFetch } from "./api";

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
