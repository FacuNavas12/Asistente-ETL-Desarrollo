const BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000";

async function parseResponse(res) {
  if (res.ok) return res.json();
  let msg;
  try {
    const body = await res.json();
    if (typeof body.detail === "string") msg = body.detail;
    else msg = `HTTP ${res.status}`;
  } catch {
    msg = `HTTP ${res.status}`;
  }
  throw new Error(msg);
}

export async function computeLineage(ktrXml) {
  const res = await fetch(`${BASE}/api/ai/lineage-from-ktr`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ktr_xml: ktrXml }),
  });
  return parseResponse(res);
}
