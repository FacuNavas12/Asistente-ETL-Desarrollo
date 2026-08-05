import { createContext, useContext, useState, useEffect } from "react";
import { listEtls, createEtl, updateEtl, deleteEtlById } from "../api/etls";
import { getJobStatus } from "../services/etlService";
import { useToast } from "../components/ui/Toast";

const ETLS_RETRY_MS = 5000;

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
  const [backendDown, setBackendDown] = useState(false);
  const { notifySystem } = useToast() ?? {};

  // Al montar (o cuando el backend estaba caído), reintenta cada ETLS_RETRY_MS
  // hasta que /api/etls responda — evita que el usuario tenga que refrescar
  // a mano después de levantar el backend con el front ya abierto.
  useEffect(() => {
    let cancelled = false;
    let timer = null;
    let wasDown = false;

    const tryLoad = async () => {
      try {
        const data = await listEtls();
        if (cancelled) return;
        setEtls(data);
        setBackendDown(false);
        if (wasDown) notifySystem?.("Conexión con el servidor restablecida.");
      } catch {
        if (cancelled) return;
        if (!wasDown) {
          wasDown = true;
          setBackendDown(true);
          notifySystem?.("No se pudo conectar con el servidor. Reintentando…");
        }
        timer = setTimeout(tryLoad, ETLS_RETRY_MS);
      }
    };

    tryLoad();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Draft (session-only) ────────────────────────────────────────────────
  const saveDraft = (data) => {
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ savedAt: Date.now(), data }));
    setDraftState(data);
  };

  const clearDraft = () => {
    sessionStorage.removeItem(DRAFT_KEY);
    setDraftState(null);
  };

  // ── Nombres únicos ──────────────────────────────────────────────────────
  // Chequeo en memoria (etls ya está cargado por listEtls al montar) — no
  // pega al backend. Dos usos distintos, a propósito (ver CreateETL.jsx y
  // EtlDetail.jsx): crear una fila nueva jamás bloquea (auto-sufijo, cubre
  // "Reutilizar" e imports); renombrar una fila existente sí bloquea, porque
  // ahí el usuario está eligiendo el nombre a propósito.
  const _normName = (s) => (s ?? "").trim().toLowerCase();

  const isNameTaken = (name, excludeId = null) =>
    etls.some(e => e.id !== excludeId && _normName(e.name) === _normName(name));

  const _uniqueName = (base, excludeId = null) => {
    const trimmed = (base ?? "").trim() || "ETL";
    if (!isNameTaken(trimmed, excludeId)) return trimmed;
    let n = 2;
    while (isNameTaken(`${trimmed} (${n})`, excludeId)) n += 1;
    return `${trimmed} (${n})`;
  };

  const _duplicateNameError = (name) => {
    const err = new Error(`Ya existe un ETL guardado con el nombre "${name}".`);
    err.duplicateName = true;
    return err;
  };

  // ── ETLs ────────────────────────────────────────────────────────────────
  // existingId: la fila en_proceso que _saveSnapshot ya creó antes de generar
  // (mismo id, se completa acá en vez de duplicar) — null = flujos sin
  // snapshot previo (ej. importar ETL en Home.jsx), donde sí hace falta crear.
  // Con existingId el nombre no se vuelve a validar acá: ya pasó por el
  // chequeo de saveInProgressEtl cuando se guardó la fila en_proceso.
  const addEtl = async (formData, apiResult, name, existingId = null) => {
    const record = existingId
      ? await updateEtl(existingId, { name: name || undefined, status: "done", formData, result: apiResult })
      : await createEtl({ name: _uniqueName(name || `ETL #${etls.length + 1}`), status: "done", formData, result: apiResult });
    setEtls(prev => existingId
      ? prev.map(e => e.id === existingId ? record : e)
      : [record, ...prev.filter(e => e.status !== "pending")]);
    clearDraft();
    return record.id;
  };

  const savePendingEtl = async (name, formData) => {
    const existing = etls.find(e => e.status === "pending");
    if (existing) {
      const finalName = (name || existing.name).trim();
      if (finalName !== existing.name.trim() && isNameTaken(finalName, existing.id)) {
        throw _duplicateNameError(finalName);
      }
      const record = await updateEtl(existing.id, {
        name: finalName,
        status: "pending",
        formData,
      });
      setEtls(prev => prev.map(e => e.id === existing.id ? record : e));
    } else {
      const record = await createEtl({
        name: _uniqueName(name || `ETL #${etls.length + 1}`),
        status: "pending",
        formData,
      });
      setEtls(prev => [record, ...prev]);
    }
  };

  const saveInProgressEtl = async (name, formData, id = null) => {
    const existing = id ? etls.find(e => e.id === id) : null;
    if (existing) {
      const finalName = (name || existing.name).trim();
      if (finalName !== existing.name.trim() && isNameTaken(finalName, existing.id)) {
        throw _duplicateNameError(finalName);
      }
      const record = await updateEtl(existing.id, {
        name: finalName,
        status: "en_proceso",
        formData,
      });
      setEtls(prev => prev.map(e => e.id === existing.id ? record : e));
      return { id: record.id, name: record.name, syncStatus: record.syncStatus };
    }
    const record = await createEtl({
      name: _uniqueName(name || `ETL #${etls.length + 1}`),
      status: "en_proceso",
      formData,
    });
    setEtls(prev => [record, ...prev]);
    // name devuelto puede diferir del pedido (auto-sufijo por colisión, ej.
    // "Reutilizar" desde EtlDetail) — el caller (CreateETL._saveSnapshot)
    // sincroniza el campo del formulario con esto, así los guardados
    // siguientes comparan contra el nombre real y no contra el original.
    return { id: record.id, name: record.name, syncStatus: record.syncStatus };
  };

  // Chequea (una sola vez, sin bloquear) si una fila "en_proceso" que quedó
  // huérfana — el usuario salió de CreateETL con el job todavía corriendo —
  // ya terminó del lado del backend. Job expirado/no encontrado (TTL 30 min)
  // se ignora: la fila se queda en_proceso, recuperable a mano reabriendo
  // la card (CreateETL retoma el polling — ver resumeJobIdRef).
  const syncStaleEtl = async (etl) => {
    const jobId = etl.formData?.jobId;
    if (etl.status !== "en_proceso" || !jobId) return;
    try {
      const jobStatus = await getJobStatus(jobId);
      if (jobStatus.build_status === "built") {
        const record = await updateEtl(etl.id, { status: "done", result: jobStatus.result });
        setEtls(prev => prev.map(e => e.id === etl.id ? record : e));
      }
    } catch {
      // expirado, no encontrado, o error de red — se deja como está
    }
  };

  /** Actualiza la copia en memoria de un ETL ya persistido, sin volver a pegarle
   *  al backend — para reflejar una mutación que otro endpoint ya guardó (ej.
   *  POST /api/etls/{id}/connections en ConnectionView, que devuelve el
   *  ETLGenerateResponse nuevo pero no el EtlRead completo). */
  const patchEtlLocal = (id, patch) => {
    setEtls(prev => prev.map(e => e.id === id ? { ...e, ...patch } : e));
  };

  /** Renombra un ETL ya persistido (ej. EtlDetail, sin estado "en_proceso" que
   *  lo respalde). Pega directo al backend — no hay borrador que perder. */
  const renameEtl = async (id, name) => {
    const trimmed = (name ?? "").trim();
    if (isNameTaken(trimmed, id)) throw _duplicateNameError(trimmed);
    const record = await updateEtl(id, { name: trimmed });
    setEtls(prev => prev.map(e => e.id === id ? record : e));
    return record;
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
      hideEtlLocally, deleteEtlPermanently, patchEtlLocal, renameEtl, isNameTaken, syncStaleEtl,
      clearAll, backendDown,
    }}>
      {children}
    </EtlContext.Provider>
  );
}

export const useEtl = () => useContext(EtlContext);
