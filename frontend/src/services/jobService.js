import { apiFetch } from "./api";

export async function analyzeJob({ ktrFiles, job_description, business_rules }) {
  const formData = new FormData();
  ktrFiles.forEach((f) => formData.append("ktr_files", f));
  formData.append("job_description", job_description);
  if (business_rules?.trim()) formData.append("business_rules", business_rules);

  return apiFetch("/api/v1/job/analyze", {
    method: "POST",
    body: formData,
  });
}

export async function refineJob({
  session_id,
  job_description,
  business_rules,
  current_job_plan,
  correction,
  history,
}) {
  return apiFetch("/api/v1/job/refine", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id,
      job_description,
      business_rules,
      current_job_plan,
      correction,
      history,
    }),
  });
}

export async function generateJob({ session_id, job_plan }) {
  return apiFetch("/api/v1/job/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id, job_plan }),
  });
}
