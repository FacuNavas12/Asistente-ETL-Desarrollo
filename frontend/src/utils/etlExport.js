/**
 * ETL export utilities.
 *
 * Three export modes:
 *   - downloadEtlSkeleton      → from CreateETL (formData only, no result)
 *   - downloadEtlDetailSkeleton → from EtlDetail (extracts formData from a completed ETL)
 *   - downloadEtlFull          → from EtlCard/Home (full ETL including result/ktr)
 *
 * Produced files use a versioned envelope so the importer can validate and
 * reject incompatible formats without silently loading garbage.
 */

import { deriveKeyword, timestamp as namingTimestamp } from "./llmRawNaming";

const EXPORT_VERSION = "1.0";

function triggerDownload(content, filename) {
  const blob = new Blob([content], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

// Omit null values — they carry no info (optional fields default to absent).
function serialize(obj) {
  return JSON.stringify(obj, (_, v) => (v === null ? undefined : v), 2);
}

function safeFilename(name) {
  return (name ?? "etl").replace(/[^a-z0-9_\-]/gi, "_").toLowerCase();
}

/**
 * Export from CreateETL wizard.
 * Captures Objetivo + Tablas de Origen (con canonical_schema) + Reglas de Negocio.
 * Does NOT include LLM result or KTR artifacts.
 *
 * @param {object} formData  — shape: { etlName, descripcionObjetivo, origenTables,
 *                             reglasNegocio, stg_definition?, dwh_model? }
 * @param {string} name      — display name for the ETL
 */
export function buildEtlSkeletonExport(formData, name) {
  const payload = {
    type: "etl_skeleton",
    version: EXPORT_VERSION,
    exportedAt: new Date().toISOString(),
    name: name ?? formData?.etlName ?? "sin-nombre",
    formData: {
      etlName:               formData?.etlName               ?? "",
      descripcionObjetivo:   formData?.descripcionObjetivo   ?? "",
      origenTables:          formData?.origenTables          ?? [],
      reglasNegocio:         formData?.reglasNegocio         ?? "",
      stg_definition:        formData?.stg_definition        ?? null,
      dwh_model:             formData?.dwh_model             ?? null,
    },
  };

  return {
    content: serialize(payload),
    filename: `etl-skeleton-${safeFilename(payload.name)}.json`,
  };
}

export function downloadEtlSkeleton(formData, name) {
  const { content, filename } = buildEtlSkeletonExport(formData, name);
  triggerDownload(content, filename);
}

/**
 * Export skeleton from EtlDetail (reuse completed ETL as starting point).
 * Same output format as downloadEtlSkeleton — importer treats them identically.
 *
 * @param {object} etl — full ETL object from EtlContext
 */
export function downloadEtlDetailSkeleton(etl) {
  downloadEtlSkeleton(etl.formData, etl.name);
}

/**
 * Export full ETL card from Home list.
 * Includes result (etapas, kjb_master, dwh_sample, lineage, etc.) so the card can be
 * reconstructed verbatim in another browser / instance.
 *
 * @param {object} etl — full ETL object from EtlContext
 */
export function downloadEtlFull(etl) {
  const payload = {
    type: "etl_full",
    version: EXPORT_VERSION,
    exportedAt: new Date().toISOString(),
    etl,
  };

  triggerDownload(
    serialize(payload),
    `etl-full-${safeFilename(etl.name)}.json`,
  );
}

/**
 * Export the raw LLM response captured when build_ktr() failed server-side.
 * Lets the user keep the (expensive) model output and retry .ktr construction
 * later via buildFromRaw() without calling the LLM again.
 *
 * Nombre de archivo (`raw-steps-<keyword>-<fecha_hora>.json`): misma palabra
 * identificadora y mismo formato de timestamp que usa el backend para los
 * .ktr/.kjb del mismo proceso (ver naming.py / llmRawNaming.js) — así el raw
 * dump queda rastreable junto a esos archivos. `rawLlmData.ktr_1/ktr_2` traen
 * proceso_etl.nombre porque son la respuesta cruda del LLM (mismo texto que
 * el backend usa como process_name) — se prioriza sobre `name` (el campo
 * "Nombre del ETL" del formulario, que puede no coincidir con lo que el LLM
 * eligió llamar a su propio proceso).
 *
 * @param {object} rawLlmData — { ktr_1, ktr_2 }, cada uno con proceso_etl/ktr crudos del modelo
 * @param {string} name       — display name para el ETL (fallback si el LLM no trae proceso_etl.nombre)
 */
export function downloadLlmRaw(rawLlmData, name) {
  const payload = {
    type: "etl_llm_raw",
    version: EXPORT_VERSION,
    exportedAt: new Date().toISOString(),
    name: name ?? "sin-nombre",
    raw_llm_data: rawLlmData,
  };

  const processName =
    rawLlmData?.ktr_1?.proceso_etl?.nombre ||
    rawLlmData?.ktr_2?.proceso_etl?.nombre ||
    payload.name;

  triggerDownload(
    serialize(payload),
    `raw-steps-${deriveKeyword(processName)}-${namingTimestamp()}.json`,
  );
}

/**
 * Export la respuesta cruda del modelo de UNA sola etapa (D31/D33,
 * docs/refactor/02-decisiones.md) — origen_stg o stg_dwh, por separado.
 *
 * Envelope propio ("etl_llm_stage"), distinto de "etl_llm_raw": reusar
 * downloadLlmRaw acá produciría un dict plano que build_etl_from_raw()
 * interpretaría como el shape legacy monolítico (1 KTR), no como una etapa
 * del flujo de 2 — se importaría sin error pero armaría algo distinto de lo
 * que el usuario espera.
 *
 * @param {object} stageData — el dict crudo de esa etapa (stages[].data)
 * @param {"origen_stg"|"stg_dwh"} stage
 * @param {string} name — display name for the ETL
 */
export function downloadLlmStage(stageData, stage, name) {
  const payload = {
    type: "etl_llm_stage",
    version: EXPORT_VERSION,
    exportedAt: new Date().toISOString(),
    name: name ?? "sin-nombre",
    stage,
    data: stageData,
  };

  triggerDownload(
    serialize(payload),
    `etl-llm-${stage}-${safeFilename(payload.name)}.json`,
  );
}
