import { downloadEtlSkeleton } from "./etlExport";

function triggerDownload(content, filename, mimeType) {
  const blob = new Blob([content], { type: mimeType });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

function safeFilename(name) {
  return (name ?? "etl").replace(/[^a-z0-9_\-]/gi, "_").toLowerCase();
}

/** Download the .ktr XML file from a completed ETL card. */
export function downloadKtrFromEtl(etl) {
  const { ktr_xml = "", ktr_filename = "" } = etl.result ?? {};
  if (!ktr_xml) return;
  triggerDownload(ktr_xml, ktr_filename || `${etl.name}.ktr`, "application/xml");
}

/**
 * Download the model-generated output as JSON.
 * Includes: proceso_etl, validaciones, documentacion, advertencias_buenas_practicas.
 * Excludes: ktr_xml, dwh_sample, lineage (deduced from ktr).
 */
export function downloadModelOutput(etl) {
  const {
    proceso_etl,
    validaciones = [],
    documentacion = "",
    advertencias_buenas_practicas = [],
  } = etl.result ?? {};

  const payload = {
    type: "etl_model_output",
    version: "1.0",
    exportedAt: new Date().toISOString(),
    name: etl.name,
    modelOutput: {
      proceso_etl: proceso_etl ?? null,
      validaciones,
      documentacion,
      advertencias_buenas_practicas,
    },
  };

  triggerDownload(
    JSON.stringify(payload, null, 2),
    `etl-resultado-${safeFilename(etl.name)}.json`,
    "application/json",
  );
}

/**
 * Download everything: .ktr + form skeleton + model output.
 * Three separate files triggered in sequence.
 */
export function downloadAll(etl) {
  downloadKtrFromEtl(etl);
  downloadEtlSkeleton(etl.formData, etl.name);
  downloadModelOutput(etl);
}
