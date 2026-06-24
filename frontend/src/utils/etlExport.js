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
export function downloadEtlSkeleton(formData, name) {
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

  triggerDownload(
    serialize(payload),
    `etl-skeleton-${safeFilename(payload.name)}.json`,
  );
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
 * Includes result (ktr_xml, kjb_xml, dwh_sample, etc.) so the card can be
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
