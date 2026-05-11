import { createContext, useContext, useState } from "react";

const EtlContext = createContext();

const DRAFT_KEY = "etl_draft";
const ETLS_KEY = "etl_list";
const DRAFT_TTL = 2 * 60 * 60 * 1000;

function loadEtls() {
  try { return JSON.parse(localStorage.getItem(ETLS_KEY)) || []; }
  catch { return []; }
}

function loadDraft() {
  try {
    const raw = JSON.parse(sessionStorage.getItem(DRAFT_KEY));
    if (!raw) return null;
    if (Date.now() - raw.savedAt > DRAFT_TTL) {
      sessionStorage.removeItem(DRAFT_KEY);
      return null;
    }
    return raw.data;
  } catch { return null; }
}

export function EtlProvider({ children }) {
  const [etls, setEtls] = useState(loadEtls);
  const [draft, setDraftState] = useState(loadDraft);

  const saveDraft = (data) => {
    const payload = { savedAt: Date.now(), data };
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
    setDraftState(data);
  };

  const clearDraft = () => {
    sessionStorage.removeItem(DRAFT_KEY);
    setDraftState(null);
  };

  const addEtl = (formData, apiResult) => {
    const newEtl = {
      id: crypto.randomUUID(),
      name: apiResult?.proceso_etl?.nombre ?? `ETL #${etls.length + 1}`,
      createdAt: new Date().toISOString(),
      formData,
      result: apiResult,
    };
    const updated = [newEtl, ...etls];
    setEtls(updated);
    localStorage.setItem(ETLS_KEY, JSON.stringify(updated));
    clearDraft();
    return newEtl.id;
  };

  return (
    <EtlContext.Provider value={{ etls, draft, saveDraft, clearDraft, addEtl }}>
      {children}
    </EtlContext.Provider>
  );
}

export const useEtl = () => useContext(EtlContext);
