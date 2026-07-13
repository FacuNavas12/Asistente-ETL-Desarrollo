import JSZip from "jszip";
import { buildEtlSkeletonExport } from "./etlExport";

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

function buildKtrExport(etl) {
  const { ktr_xml = "", ktr_filename = "" } = etl.result ?? {};
  if (!ktr_xml) return null;
  return { content: ktr_xml, filename: ktr_filename || `${etl.name}.ktr` };
}

// Flujo de 2 KTR + 1 .kjb (origen→STG / STG→DWH orquestados en secuencia).
// null en el flujo monolítico legacy (build-from-raw) — no hay KTR_2/.kjb que exportar.
function buildKtr2Export(etl) {
  const { ktr2_xml = "", ktr2_filename = "" } = etl.result ?? {};
  if (!ktr2_xml) return null;
  return { content: ktr2_xml, filename: ktr2_filename || `${etl.name}_2.ktr` };
}

function buildKjbExport(etl) {
  const { kjb_xml = "", kjb_filename = "" } = etl.result ?? {};
  if (!kjb_xml) return null;
  return { content: kjb_xml, filename: kjb_filename || `${etl.name}_job.kjb` };
}

/** Download the .ktr XML file(s) — y el .kjb orquestador si el flujo es de 2 KTR — desde una ETL card. */
export function downloadKtrFromEtl(etl) {
  const file = buildKtrExport(etl);
  if (!file) return;
  triggerDownload(file.content, file.filename, "application/xml");

  const ktr2 = buildKtr2Export(etl);
  const kjb  = buildKjbExport(etl);
  if (ktr2) triggerDownload(ktr2.content, ktr2.filename, "application/xml");
  if (kjb)  triggerDownload(kjb.content, kjb.filename, "application/xml");
}

/**
 * Download the model-generated output as JSON.
 * Includes: proceso_etl, validaciones, documentacion, advertencias_buenas_practicas.
 * Excludes: ktr_xml, dwh_sample, lineage (deduced from ktr).
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
 */
export async function downloadAll(etl) {
  const zip = new JSZip();

  const ktr = buildKtrExport(etl);
  if (ktr) zip.file(ktr.filename, ktr.content);

  const ktr2 = buildKtr2Export(etl);
  if (ktr2) zip.file(ktr2.filename, ktr2.content);

  const kjb = buildKjbExport(etl);
  if (kjb) zip.file(kjb.filename, kjb.content);

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
}
