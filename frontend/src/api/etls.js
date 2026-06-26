import { apiFetch, API } from "../services/api";

export const listEtls = () => apiFetch("/api/etls/");

export const createEtl = (payload) =>
  apiFetch("/api/etls/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const updateEtl = (id, payload) =>
  apiFetch(`/api/etls/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const patchEtlStatus = (id, status) =>
  apiFetch(`/api/etls/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });

export const deleteEtlById = async (id) => {
  const res = await fetch(`${API}/api/etls/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
};
