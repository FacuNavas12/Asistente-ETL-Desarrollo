/**
 * ETL import utilities.
 *
 * Two import modes:
 *   - importEtlSkeleton  → returns formData ready to populate CreateETL wizard
 *   - importEtlFull      → returns a full ETL object ready to persist via EtlContext
 *
 * Both throw on invalid/incompatible files so callers can surface errors to the user.
 *
 * Generic helper:
 *   - parseEtlFile → { type: "skeleton"|"full", formData?, etl? }
 *     Use this when the UI accepts both file types from a single input.
 */

import { readEtlArtifacts } from "./etlArtifacts";

const SUPPORTED_VERSIONS = ["1.0"];
const SCHEMA_VERSION = "1.0";

// ── File reading ─────────────────────────────────────────────────────────────

function readFileAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => resolve(e.target.result);
    reader.onerror = () => reject(new Error("Error al leer el archivo"));
    reader.readAsText(file, "utf-8");
  });
}

async function parseJSON(file) {
  const text = await readFileAsText(file);
  try {
    return JSON.parse(text);
  } catch {
    throw new Error("El archivo no es JSON válido");
  }
}

// ── Validation helpers ────────────────────────────────────────────────────────

function checkVersion(data) {
  if (!SUPPORTED_VERSIONS.includes(data.version)) {
    throw new Error(
      `Versión de archivo "${data.version}" no soportada (soportadas: ${SUPPORTED_VERSIONS.join(", ")})`
    );
  }
}

function checkType(data, expected) {
  if (data.type !== expected) {
    throw new Error(
      `Tipo de archivo incorrecto: esperado "${expected}", recibido "${data.type}"`
    );
  }
}

/**
 * Validates that all origenTables with canonical_schema use SCHEMA_VERSION "1.0".
 * Mirrors the same check in EtlContext.isSchemaVersionValid.
 */
function checkSchemaVersion(formData) {
  const tables = formData?.origenTables ?? [];
  for (const t of tables) {
    if (t.canonical_schema != null && t.canonical_schema.schema_version !== SCHEMA_VERSION) {
      throw new Error(
        `canonical_schema de tabla "${t.nombre ?? t.alias ?? "?"}" usa versión ` +
        `"${t.canonical_schema.schema_version}" (esperada: "${SCHEMA_VERSION}"). ` +
        "Re-exportá desde una versión actualizada del sistema."
      );
    }
  }
}

/**
 * D28 (docs/refactor/02-decisiones.md) — rechazo explícito de result en el
 * shape viejo (ktr_xml/ktr2_xml/kjb_xml, pre-D20). Un result "none" (build
 * fallido nuevo) sí se importa — el detalle ya explica que no hay .ktr.
 */
function checkResultShape(result) {
  if (readEtlArtifacts(result).status === "legacy") {
    throw new Error(
      "El archivo trae un resultado en el formato anterior (ktr_xml/kjb_xml). " +
      "Regenerá el ETL y volvé a exportarlo."
    );
  }
}

function validateFormData(formData) {
  if (!formData || typeof formData !== "object") {
    throw new Error("Falta formData en el archivo");
  }
  if (!Array.isArray(formData.origenTables) || formData.origenTables.length === 0) {
    throw new Error("El archivo no contiene tablas de origen (origenTables vacío)");
  }
  checkSchemaVersion(formData);
}

// ── Public API ────────────────────────────────────────────────────────────────

/**
 * Import a skeleton file (from CreateETL or EtlDetail skeleton export).
 * Returns formData ready to inject into CreateETL wizard state.
 *
 * @param {File} file
 * @returns {Promise<object>} formData
 * @throws {Error} with human-readable message on any validation failure
 */
export async function importEtlSkeleton(file) {
  const data = await parseJSON(file);

  if (!["etl_skeleton", "etl_full"].includes(data.type)) {
    throw new Error(
      `Tipo de archivo no reconocido: "${data.type}". ` +
      "Usá un archivo exportado desde CrearTransformación o EtlDetail."
    );
  }

  checkVersion(data);

  const formData = data.type === "etl_full" ? data.etl?.formData : data.formData;
  validateFormData(formData);

  return formData;
}

/**
 * Import a full ETL file (from EtlCard export).
 * Returns the ETL object with a new UUID — avoids ID collision when importing
 * into a context that already has the original.
 *
 * @param {File} file
 * @returns {Promise<object>} etl (with fresh id)
 * @throws {Error} with human-readable message on any validation failure
 */
export async function importEtlFull(file) {
  const data = await parseJSON(file);

  checkType(data, "etl_full");
  checkVersion(data);

  const etl = data.etl;

  if (!etl || typeof etl !== "object") {
    throw new Error("Falta el objeto ETL en el archivo");
  }
  if (!etl.result) {
    throw new Error(
      "El archivo no contiene resultado ETL (result). " +
      "Si solo querés importar el esqueleto, usá importEtlSkeleton."
    );
  }
  checkResultShape(etl.result);

  validateFormData(etl.formData);

  // New UUID prevents collision with a pre-existing ETL of the same origin.
  return {
    ...etl,
    id: crypto.randomUUID(),
    importedAt: new Date().toISOString(),
  };
}

/**
 * Generic parser — accepts both skeleton and full files.
 * Use when the UI offers a single file picker for both types.
 *
 * @param {File} file
 * @returns {Promise<{ type: "skeleton"|"full", formData?: object, etl?: object }>}
 * @throws {Error} on validation failure
 */
export async function parseEtlFile(file) {
  const data = await parseJSON(file);

  if (!["etl_skeleton", "etl_full"].includes(data.type)) {
    throw new Error(`Tipo de archivo no reconocido: "${data.type}"`);
  }

  checkVersion(data);

  if (data.type === "etl_full") {
    const etl = data.etl;
    if (!etl?.result) throw new Error("Archivo etl_full sin result");
    checkResultShape(etl.result);
    validateFormData(etl.formData);
    return {
      type: "full",
      etl: { ...etl, id: crypto.randomUUID(), importedAt: new Date().toISOString() },
      formData: etl.formData,
    };
  }

  validateFormData(data.formData);
  return { type: "skeleton", formData: data.formData };
}

/**
 * Import a raw LLM response file (from downloadLlmRaw, saved after a build_ktr failure).
 * Returns the raw dict ready to pass to buildFromRaw() to retry .ktr construction
 * without calling the LLM again.
 *
 * @param {File} file
 * @returns {Promise<object>} raw_llm_data
 * @throws {Error} with human-readable message on any validation failure
 */
export async function importLlmRaw(file) {
  const data = await parseJSON(file);

  checkType(data, "etl_llm_raw");
  checkVersion(data);

  if (!data.raw_llm_data || typeof data.raw_llm_data !== "object") {
    throw new Error("El archivo no contiene raw_llm_data");
  }

  return data.raw_llm_data;
}
