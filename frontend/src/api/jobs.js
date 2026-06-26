import { apiFetch, API } from "../services/api";

export const listJobs = () => apiFetch("/api/jobs/");

export const createJob = (payload) =>
  apiFetch("/api/jobs/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const updateJob = (id, payload) =>
  apiFetch(`/api/jobs/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

export const patchJobStatus = (id, status) =>
  apiFetch(`/api/jobs/${id}/status`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });

export const deleteJobById = async (id) => {
  const res = await fetch(`${API}/api/jobs/${id}`, { method: "DELETE" });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
    throw new Error(err.detail ?? `HTTP ${res.status}`);
  }
};
