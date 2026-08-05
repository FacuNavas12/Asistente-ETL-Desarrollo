import { createContext, useContext, useState, useEffect } from "react";
import { listEtls, createEtl, updateEtl, deleteEtlById } from "../api/etls";

const EtlContext = createContext();

const DRAFT_KEY  = "etl_draft";
const DRAFT_TTL  = 2 * 60 * 60 * 1000;
const SCHEMA_VERSION = "1.0";
const HIDDEN_IDS_KEY = "etl_hidden_ids";

function loadHiddenIds() {
  try {
    const raw = JSON.parse(localStorage.getItem(HIDDEN_IDS_KEY));
    return Array.isArray(raw) ? raw : [];
  } catch { return []; }
}

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
  const [draft, setDraftState] = useState(loadDraft);
  const [hiddenIds, setHiddenIds] = useState(loadHiddenIds);

  useEffect(() => {
    listEtls().then(setEtls).catch(console.error);
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
  // existingId: la fila en_proceso que _saveSnapshot ya creó antes de generar
  // (mismo id, se completa acá en vez de duplicar) — null = flujos sin
  // snapshot previo (ej. importar ETL en Home.jsx), donde sí hace falta crear.
  const addEtl = async (formData, apiResult, name, existingId = null) => {
    const record = existingId
      ? await updateEtl(existingId, { name: name || undefined, status: "done", formData, result: apiResult })
      : await createEtl({ name: name || `ETL #${etls.length + 1}`, status: "done", formData, result: apiResult });
    setEtls(prev => existingId
      ? prev.map(e => e.id === existingId ? record : e)
      : [record, ...prev.filter(e => e.status !== "pending")]);
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
      return { id: record.id, syncStatus: record.syncStatus };
    }
    const record = await createEtl({
      name: name || `ETL #${etls.length + 1}`,
      status: "en_proceso",
      formData,
    });
    setEtls(prev => [record, ...prev]);
    return { id: record.id, syncStatus: record.syncStatus };
  };

  /** Actualiza la copia en memoria de un ETL ya persistido, sin volver a pegarle
   *  al backend — para reflejar una mutación que otro endpoint ya guardó (ej.
   *  POST /api/etls/{id}/connections en ConnectionView, que devuelve el
   *  ETLGenerateResponse nuevo pero no el EtlRead completo). */
  const patchEtlLocal = (id, patch) => {
    setEtls(prev => prev.map(e => e.id === id ? { ...e, ...patch } : e));
  };

  /** Oculta el ETL solo en este navegador (localStorage). No borra nada en el backend. */
  const hideEtlLocally = (id) => {
    setHiddenIds(prev => {
      if (prev.includes(id)) return prev;
      const next = [...prev, id];
      localStorage.setItem(HIDDEN_IDS_KEY, JSON.stringify(next));
      return next;
    });
  };

  /** Borra el ETL definitivamente: backend + fila en Supabase. Irreversible. */
  const deleteEtlPermanently = async (id) => {
    await deleteEtlById(id);
    setEtls(prev => prev.filter(e => e.id !== id));
    setHiddenIds(prev => {
      if (!prev.includes(id)) return prev;
      const next = prev.filter(hid => hid !== id);
      localStorage.setItem(HIDDEN_IDS_KEY, JSON.stringify(next));
      return next;
    });
  };

  const visibleEtls = etls.filter(e => !hiddenIds.includes(e.id));

  const clearAll = () => {
    clearAllStoredData();
    localStorage.removeItem(HIDDEN_IDS_KEY);
    setEtls([]);
    setDraftState(null);
    setHiddenIds([]);
  };

  return (
    <EtlContext.Provider value={{
      etls, visibleEtls, draft, saveDraft, clearDraft, addEtl, savePendingEtl, saveInProgressEtl,
      hideEtlLocally, deleteEtlPermanently, patchEtlLocal,
      clearAll,
    }}>
      {children}
    </EtlContext.Provider>
  );
}

export const useEtl = () => useContext(EtlContext);
