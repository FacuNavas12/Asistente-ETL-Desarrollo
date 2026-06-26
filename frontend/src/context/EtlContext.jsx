import { createContext, useContext, useState, useEffect } from "react";
import { listEtls, createEtl, updateEtl, deleteEtlById } from "../api/etls";
import { listJobs, createJob, updateJob } from "../api/jobs";

const EtlContext = createContext();

const DRAFT_KEY  = "etl_draft";
const DRAFT_TTL  = 2 * 60 * 60 * 1000;
const SCHEMA_VERSION = "1.0";

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

/** Elimina el borrador de sesión del usuario.
 *  Debe llamarse en el logout para cumplir el principio de minimización de
 *  datos de la Ley 18.331. Los registros persistentes viven en el backend. */
export function clearAllStoredData() {
  sessionStorage.removeItem(DRAFT_KEY);
}

export function EtlProvider({ children }) {
  const [etls, setEtls] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [draft, setDraftState] = useState(loadDraft);

  useEffect(() => {
    listEtls().then(setEtls).catch(console.error);
    listJobs().then(setJobs).catch(console.error);
  }, []);

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
  const addEtl = async (formData, apiResult, name) => {
    const record = await createEtl({
      name: name || `ETL #${etls.length + 1}`,
      status: "done",
      formData,
      result: apiResult,
    });
    setEtls(prev => [record, ...prev.filter(e => e.status !== "pending")]);
    clearDraft();
    return record.id;
  };

  const savePendingEtl = async (name, formData) => {
    const existing = etls.find(e => e.status === "pending");
    if (existing) {
      const record = await updateEtl(existing.id, {
        name: name || existing.name,
        status: "pending",
        formData,
      });
      setEtls(prev => prev.map(e => e.id === existing.id ? record : e));
    } else {
      const record = await createEtl({
        name: name || `ETL #${etls.length + 1}`,
        status: "pending",
        formData,
      });
      setEtls(prev => [record, ...prev]);
    }
  };

  const saveInProgressEtl = async (name, formData, id = null) => {
    const existing = id ? etls.find(e => e.id === id) : null;
    if (existing) {
      const record = await updateEtl(existing.id, {
        name: name || existing.name,
        status: "en_proceso",
        formData,
      });
      setEtls(prev => prev.map(e => e.id === existing.id ? record : e));
      return record.id;
    }
    const record = await createEtl({
      name: name || `ETL #${etls.length + 1}`,
      status: "en_proceso",
      formData,
    });
    setEtls(prev => [record, ...prev]);
    return record.id;
  };

  const deleteEtl = async (id) => {
    await deleteEtlById(id);
    setEtls(prev => prev.filter(e => e.id !== id));
  };

  // ── Jobs ────────────────────────────────────────────────────────────────
  const addJob = async (formData, apiResult) => {
    const record = await createJob({
      name: apiResult?.job_plan?.job_name ?? `Job #${jobs.length + 1}`,
      status: "done",
      formData,
      result: apiResult,
    });
    setJobs(prev => [record, ...prev.filter(j => j.status !== "pending")]);
    return record.id;
  };

  const savePendingJob = async (name, formData) => {
    const existing = jobs.find(j => j.status === "pending");
    if (existing) {
      const record = await updateJob(existing.id, {
        name: name || existing.name,
        status: "pending",
        formData,
      });
      setJobs(prev => prev.map(j => j.id === existing.id ? record : j));
    } else {
      const record = await createJob({
        name: name || `Job #${jobs.length + 1}`,
        status: "pending",
        formData,
      });
      setJobs(prev => [record, ...prev]);
    }
  };

  const clearAll = () => {
    clearAllStoredData();
    setEtls([]);
    setJobs([]);
    setDraftState(null);
  };

  return (
    <EtlContext.Provider value={{
      etls, draft, saveDraft, clearDraft, addEtl, savePendingEtl, saveInProgressEtl, deleteEtl,
      jobs, addJob, savePendingJob,
      clearAll,
    }}>
      {children}
    </EtlContext.Provider>
  );
}

export const useEtl = () => useContext(EtlContext);
