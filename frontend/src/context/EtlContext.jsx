import { createContext, useContext, useState } from "react";

const EtlContext = createContext();

const DRAFT_KEY      = "etl_draft";
const ETLS_KEY       = "etl_list";
const JOBS_KEY       = "job_list";
const DRAFT_TTL      = 2 * 60 * 60 * 1000;
const SCHEMA_VERSION = "1.0";

/**
 * Validate that file-sourced tables in a saved ETL entry use the current schema_version.
 * If any table has a canonical_schema with a version other than SCHEMA_VERSION, the entry
 * is considered stale and must be discarded rather than silently used.
 *
 * Tables from DB connections (connection_id set) have no canonical_schema and are always valid.
 * Tables from files (canonical_schema set) must carry schema_version === SCHEMA_VERSION.
 * Tables with no canonical_schema (manual form entry) are always valid.
 *
 * Returns true if the entry is valid, false if it should be discarded.
 */
function isSchemaVersionValid(formData) {
  const tables = formData?.origenTables ?? [];
  for (const t of tables) {
    if (t.canonical_schema != null) {
      if (t.canonical_schema.schema_version !== SCHEMA_VERSION) {
        return false;
      }
    }
  }
  return true;
}

function loadItems(key) {
  try {
    const items = JSON.parse(localStorage.getItem(key)) || [];
    // Filter out items with stale schema versions; show a console warning.
    return items.filter(item => {
      if (!isSchemaVersionValid(item.formData)) {
        console.warn(
          `[EtlContext] Entrada descartada (schema_version obsoleto): "${item.name}". ` +
          "Volvé a cargar los archivos para regenerar el esquema."
        );
        return false;
      }
      return true;
    });
  } catch { return []; }
}

function loadDraft() {
  try {
    const raw = JSON.parse(sessionStorage.getItem(DRAFT_KEY));
    if (!raw) return null;
    if (Date.now() - raw.savedAt > DRAFT_TTL) {
      sessionStorage.removeItem(DRAFT_KEY);
      return null;
    }
    if (!isSchemaVersionValid(raw.data)) {
      sessionStorage.removeItem(DRAFT_KEY);
      console.warn(
        "[EtlContext] Borrador descartado (schema_version obsoleto). " +
        "Volvé a cargar los archivos para regenerar el esquema."
      );
      return null;
    }
    return raw.data;
  } catch { return null; }
}

function persist(key, list, setter) {
  setter(list);
  localStorage.setItem(key, JSON.stringify(list));
}

export function EtlProvider({ children }) {
  const [etls, setEtls] = useState(() => loadItems(ETLS_KEY));
  const [draft, setDraftState] = useState(loadDraft);
  const [jobs, setJobs] = useState(() => loadItems(JOBS_KEY));

  // ── Draft (session-only) ────────────────────────────────────────────────
  const saveDraft = (data) => {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ savedAt: Date.now(), data }));
    setDraftState(data);
  };

  const clearDraft = () => {
    sessionStorage.removeItem(DRAFT_KEY);
    setDraftState(null);
  };

  // ── ETLs ────────────────────────────────────────────────────────────────
  const addEtl = (formData, apiResult) => {
    const newEtl = {
      id: crypto.randomUUID(),
      name: apiResult?.proceso_etl?.nombre ?? `ETL #${etls.length + 1}`,
      createdAt: new Date().toISOString(),
      status: "done",
      formData,
      result: apiResult,
    };
    // Remove any pending ETL when a completed one is saved
    const updated = [newEtl, ...etls.filter(e => e.status !== "pending")];
    persist(ETLS_KEY, updated, setEtls);
    clearDraft();
    return newEtl.id;
  };

  const savePendingEtl = (name, formData) => {
    const existing = etls.find(e => e.status === "pending");
    const entry = {
      id: existing?.id ?? crypto.randomUUID(),
      name: name || `ETL #${etls.length + 1}`,
      createdAt: existing?.createdAt ?? new Date().toISOString(),
      status: "pending",
      formData,
      result: null,
    };
    const updated = existing
      ? etls.map(e => (e.id === existing.id ? entry : e))
      : [entry, ...etls];
    persist(ETLS_KEY, updated, setEtls);
  };

  // ── Jobs ────────────────────────────────────────────────────────────────
  const addJob = (formData, apiResult) => {
    const newJob = {
      id: crypto.randomUUID(),
      name: apiResult?.job_plan?.job_name ?? `Job #${jobs.length + 1}`,
      createdAt: new Date().toISOString(),
      status: "done",
      formData,
      result: apiResult,
    };
    // Remove any pending Job when a completed one is saved
    const updated = [newJob, ...jobs.filter(j => j.status !== "pending")];
    persist(JOBS_KEY, updated, setJobs);
    return newJob.id;
  };

  const savePendingJob = (name, formData) => {
    const existing = jobs.find(j => j.status === "pending");
    const entry = {
      id: existing?.id ?? crypto.randomUUID(),
      name: name || `Job #${jobs.length + 1}`,
      createdAt: existing?.createdAt ?? new Date().toISOString(),
      status: "pending",
      formData,
      result: null,
    };
    const updated = existing
      ? jobs.map(j => (j.id === existing.id ? entry : j))
      : [entry, ...jobs];
    persist(JOBS_KEY, updated, setJobs);
  };

  return (
    <EtlContext.Provider value={{
      etls, draft, saveDraft, clearDraft, addEtl, savePendingEtl,
      jobs, addJob, savePendingJob,
    }}>
      {children}
    </EtlContext.Provider>
  );
}

export const useEtl = () => useContext(EtlContext);
