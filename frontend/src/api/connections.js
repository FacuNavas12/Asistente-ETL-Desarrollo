const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function parseResponse(res) {
  if (res.ok) return res.json();
  let msg;
  try {
    const body = await res.json();
    if (Array.isArray(body.detail)) {
      msg = body.detail
        .map(item => `${item.loc.slice(1).join(".")}: ${item.msg}`)
        .join("; ");
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

export async function createConnection(payload) {
  const res = await fetch(`${BASE}/api/connections`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return parseResponse(res);
}

// Nota: /test devuelve 200 OK incluso cuando la conexión falla.
// Leer body.success, NO el status HTTP.
export async function testConnection(id) {
  const res = await fetch(`${BASE}/api/connections/${id}/test`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
  return parseResponse(res);
}

export async function listTables(id) {
  const res = await fetch(`${BASE}/api/connections/${id}/schema/tables`, {
    headers: { "Content-Type": "application/json" },
  });
  return parseResponse(res);
}

export async function getTableData(id, schema, table, page = 1, pageSize = 100, exactCount = false) {
  const params = new URLSearchParams({
    schema,
    table,
    page,
    page_size: pageSize,
    exact_count: exactCount,
  });
  const res = await fetch(`${BASE}/api/connections/${id}/schema/table-data?${params}`);
  return parseResponse(res);
}

export async function getColumns(id, tableName) {
  const res = await fetch(`${BASE}/api/connections/${id}/schema/tables/${encodeURIComponent(tableName)}/columns`);
  return parseResponse(res);
}

/**
 * Returns a CanonicalSchema for the table: structural info (types, PK, FK)
 * + statistical profile (null_pct, distinct_count, format_hint).
 * No raw row values are included in the response.
 */
export async function getTableProfile(id, tableName) {
  const res = await fetch(
    `${BASE}/api/connections/${id}/schema/tables/${encodeURIComponent(tableName)}/profile`,
  );
  return parseResponse(res);
}
