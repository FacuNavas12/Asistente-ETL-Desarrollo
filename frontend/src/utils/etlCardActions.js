import JSZip from "jszip";
import { buildEtlSkeletonExport } from "./etlExport";
import { readEtlArtifacts, buildZipEntries } from "./etlArtifacts";

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

/** Download los .ktr/.kjb (según etapas/kjb_master, D20) desde una ETL card. Tira si no hay nada para descargar. */
export function downloadKtrFromEtl(etl) {
  const art = readEtlArtifacts(etl.result);
  if (art.status !== "ok") throw new Error(art.message);
  for (const f of art.files) triggerDownload(f.xml, f.filename, "application/xml");
}

/** Download del/de los .ktr + .kjb en un único .zip — usado desde EtlDetail. Tira si no hay nada para descargar. */
export async function downloadKtrZipFromEtl(etl) {
  const art = readEtlArtifacts(etl.result);
  if (art.status !== "ok") throw new Error(art.message);

  const zip = new JSZip();
  for (const { path, content } of buildZipEntries(art)) zip.file(path, content);

  const blob = await zip.generateAsync({ type: "blob" });
  triggerDownload(blob, `${safeFilename(etl.name)}_ktr.zip`, "application/zip");
}

/**
 * Download the model-generated output as JSON.
 * Includes: proceso_etl, validaciones, documentacion, advertencias_buenas_practicas.
 * Excludes: etapas/kjb_master, dwh_sample, lineage (deduced from ktr).
 */
function buildModelOutputExport(etl) {
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

  return {
    content: JSON.stringify(payload, null, 2),
    filename: `etl-resultado-${safeFilename(etl.name)}.json`,
  };
}

export function downloadModelOutput(etl) {
  const { content, filename } = buildModelOutputExport(etl);
  triggerDownload(content, filename, "application/json");
}

/**
 * Download everything: .ktr + form skeleton + model output, bundled into one .zip.
 * No tira si falta el .ktr (skeleton/modelOutput siguen siendo válidos para
 * regenerar) — devuelve el motivo para que el llamador avise por toast.
 * @returns {string|null} mensaje si los .ktr no se incluyeron, null si sí.
 */
export async function downloadAll(etl) {
  const zip = new JSZip();

  const art = readEtlArtifacts(etl.result);
  if (art.status === "ok") {
    for (const { path, content } of buildZipEntries(art)) zip.file(path, content);
  }

  const skeleton = buildEtlSkeletonExport(etl.formData, etl.name);
  zip.file(skeleton.filename, skeleton.content);

  const modelOutput = buildModelOutputExport(etl);
  zip.file(modelOutput.filename, modelOutput.content);

  const blob = await zip.generateAsync({ type: "blob" });
  const url  = URL.createObjectURL(blob);
  const a    = document.createElement("a");
  a.href     = url;
  a.download = `etl-todo-${safeFilename(etl.name)}.zip`;
  a.click();
  URL.revokeObjectURL(url);

  return art.status === "ok" ? null : art.message;
}
