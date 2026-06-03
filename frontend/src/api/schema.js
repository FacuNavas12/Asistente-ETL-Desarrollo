const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function parseResponse(res) {
  if (res.ok) return res.json();
  let msg;
  try {
    const body = await res.json();
    if (Array.isArray(body.detail)) {
      msg = body.detail.map(i => `${i.loc.slice(1).join(".")}: ${i.msg}`).join("; ");
    } else if (typeof body.detail === "string") {
      msg = body.detail;
    } else {
      msg = `HTTP ${res.status}`;
    }
  } catch {
    msg = `HTTP ${res.status}`;
  }
  throw new Error(msg);
}

/**
 * Upload a CSV or Excel file to the backend and receive a CanonicalSchema.
 * No raw row data travels in the response — only structural and statistical metadata.
 *
 * @param {File} file  — browser File object (.csv, .xlsx, .xls)
 * @returns {Promise<import("../types/canonical").CanonicalSchema>}
 */
export async function inferSchema(file) {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/schema/infer`, {
    method: "POST",
    body: form,
  });
  return parseResponse(res);
}

/**
 * Parse a DDL string (one or more CREATE TABLE statements) and receive one
 * CanonicalSchema per table. Unknown types map to UNKNOWN — no error thrown.
 *
 * @param {string} ddl      — raw CREATE TABLE SQL
 * @param {string} dialect  — "ansi" | "postgres" | "tsql" | "mysql"
 * @returns {Promise<import("../types/canonical").CanonicalSchema[]>}
 */
export async function parseDDL(ddl, dialect = "ansi") {
  const res = await fetch(`${BASE}/api/schema/from-ddl`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ddl, dialect }),
  });
  return parseResponse(res);
}

/**
 * Maps a CanonicalType string (from the backend) to the ColumnaOrigen.dataType
 * format expected by the rest of the ETL form.
 */
export function canonicalTypeToDataType(canonicalType) {
  switch (canonicalType) {
    case "integer":  return "int";
    case "number":   return "float";
    case "boolean":  return "bool";
    case "date":
    case "datetime":
    case "time":     return "date";
    default:         return "string";
  }
}

/**
 * Convert a CanonicalSchema (from /api/schema/infer) to the TablaOrigen format
 * stored in EtlContext, keeping the original CanonicalSchema in canonical_schema
 * so the context_builder can use the profile on the backend.
 *
 * @param {Object} canonicalSchema — CanonicalSchema from the backend
 * @returns {Object} TablaOrigen-shaped object
 */
export function canonicalSchemaToTablaOrigen(canonicalSchema) {
  const columns = (canonicalSchema.fields ?? []).map(field => ({
    name:       field.name,
    dataType:   canonicalTypeToDataType(field.type),
    dataFormat: field.format !== "default" ? field.format : "",
    role:       "atributo",
    data:       null,   // deprecated; stats live in canonical_schema.profile
  }));

  return {
    tableName:        canonicalSchema.source_name,
    columns,
    connection_id:    null,
    schema_name:      null,
    canonical_schema: canonicalSchema,   // kept for backend context_builder
  };
}
