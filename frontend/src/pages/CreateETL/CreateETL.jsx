import { useState, useEffect, useMemo, useRef } from "react";
import logo from "@/assets/Logo_blanco_esp.png";
import { useNavigate, useLocation, useBlocker } from "react-router-dom";
import { useForm, useWatch } from "react-hook-form";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import OrigenInput from "./components/Input/InputForm";
import ConfirmedTablesList from "./components/Tables/TableManagement/ConfirmedTablesList";
import EtlChecks from "./components/EtlChecks";
import BusinessRules from "./components/BussinesRules/BusinessRules";
import DescripcionObjetivo from "./components/Goal/GoalDescription";
import ConfirmModal from "@/components/ui/ConfirmModal";
import InferenceReview from "./components/InferenceReview/InferenceReview";
import DestinationConnections from "./components/Processing/DestinationConnections";
import { SAMPLE_ETL } from "./utils/sampleEtl";
import {
  inferStructures, refineInference, buildFromRaw,
  generateAsync, submitJobConnections, getJobStatus,
} from "@/services/etlService";
import { useToast } from "@/components/ui/Toast";
import { downloadEtlSkeleton, downloadLlmRaw, downloadLlmStage } from "@/utils/etlExport";
import { importEtlSkeleton, importModelResponse } from "@/utils/etlImport";
import { stagesArrayToMap, mergeProgressLogs } from "./utils/progressLog";
import CreateETLOptions from "./components/CreateETLOptions";
import "./css/createETL.css";

// Estados de la máquina:
// form → inferring → review → processing → (navigate)
const STEP = {
  FORM:       "form",
  INFERRING:  "inferring",
  REVIEW:     "review",
  PROCESSING: "processing",
};

export default function CreateETL() {
  const navigate  = useNavigate();
  const location  = useLocation();
  const { draft, saveDraft, clearDraft, addEtl, saveInProgressEtl } = useEtl();
  const { addToast, notifySystem } = useToast();

  // fresh: true → always open blank (navbar "Nuevo ETL" button)
  // initialFormData → load from prior ETL (Continuar / Reutilizar)
  const initSource  = location.state?.fresh
    ? null
    : (location.state?.initialFormData ?? draft);

  const defaultName = initSource?.etlName ?? "Generar ETL";

  const { control, setValue, reset, getValues, formState: { isDirty } } = useForm({
    defaultValues: {
      etlName:             defaultName,
      descripcionObjetivo: initSource?.descripcionObjetivo ?? "",
      origenTables:        initSource?.origenTables        ?? [],
      reglasNegocio:       initSource?.reglasNegocio       ?? "",
    },
  });

  const etlName             = useWatch({ control, name: "etlName" });
  const descripcionObjetivo = useWatch({ control, name: "descripcionObjetivo" });
  const origenTables        = useWatch({ control, name: "origenTables" });
  const reglasNegocio       = useWatch({ control, name: "reglasNegocio" });

  // Requisitos mínimos para poder inferir: al menos una tabla de origen, el
  // objetivo del proceso y las reglas de negocio. El botón Inferir queda
  // deshabilitado hasta cumplirlos.
  const missingToInfer = [
    (!Array.isArray(origenTables) || origenTables.length === 0) && "una tabla de origen",
    !descripcionObjetivo?.trim() && "el objetivo del proceso",
    !reglasNegocio?.trim() && "las reglas de negocio",
  ].filter(Boolean);
  const canInfer = missingToInfer.length === 0;

  const [step,           setStep]           = useState(STEP.FORM);
  const [isEditingName,  setIsEditingName]  = useState(false);
  const [nameInputVal,   setNameInputVal]   = useState(defaultName);
  const [syncStatus,     setSyncStatus]     = useState(null); // null | "pending" | "synced" | "failed"
  const [inferResult,    setInferResult]    = useState(() => {
    if (initSource?.inferResult) return initSource.inferResult;
    if (initSource?.stg_definition || initSource?.dwh_model) {
      return { stg_ddl: initSource.stg_definition ?? "", dwh_ddl: initSource.dwh_model ?? "" };
    }
    return null;
  });
  const [inferHistory,   setInferHistory]   = useState([]);
  const [isRefining,     setIsRefining]     = useState(false);
  const [etlPhase,       setEtlPhase]       = useState("waiting");
  const [ktrLogs,        setKtrLogs]        = useState([]);
  // D30/D32/D33 (docs/refactor/02-decisiones.md): respuesta cruda del modelo
  // por etapa — { origen_stg: {status,data,error}|null, stg_dwh: {...}|null }.
  // Poblado desde status.stages en cada tick del poll, sobrevive un fallo
  // parcial (solo una etapa lista) a diferencia del rawLlmData de antes.
  const [modelStages,    setModelStages]    = useState({ origen_stg: null, stg_dwh: null });
  const [modelResponsesOpen, setModelResponsesOpen] = useState(false);
  // job_id del flujo async (generate-async): el modelo corre en background mientras
  // el usuario completa las conexiones destino en paralelo (ver handleConfirm).
  const [jobId,          setJobId]          = useState(null);
  const connectionsMapRef       = useRef({});
  const pollTimeoutRef          = useRef(null);
  // D29: último seq de progreso ya volcado a ktrLogs — el poll solo agrega
  // los eventos nuevos, no reconstruye la lista entera en cada tick.
  const lastProgressSeqRef      = useRef(-1);
  const pendingNavigateRef      = useRef(null);
  const pendingClearStateRef    = useRef(false);
  const importInputRef          = useRef(null);
  const importRawInputRef       = useRef(null);
  const currentEtlIdRef      = useRef(location.state?.etlId ?? null);
  // Track serialized tables to distinguish real changes from reference-only re-renders
  const origenTablesSerialRef = useRef(JSON.stringify(initSource?.origenTables ?? []));

  // D32: derivado con el shape {ktr_1, ktr_2} completo (o null) que consumen
  // buildFromRaw/_finishEtl/downloadLlmRaw — nunca una etapa en null. Solo
  // "completo" cuando las DOS etapas están done/reused.
  const rawLlmData = useMemo(() => {
    const a = modelStages.origen_stg?.data;
    const b = modelStages.stg_dwh?.data;
    return (a && b) ? { ktr_1: a, ktr_2: b } : null;
  }, [modelStages]);

  // Clear stale inferResult only when table content actually changes (not on reference-only re-renders).
  useEffect(() => {
    const curr = JSON.stringify(origenTables);
    if (curr === origenTablesSerialRef.current) return;
    origenTablesSerialRef.current = curr;
    if (inferResult) {
      setInferResult(null);
      setInferHistory([]);
      setModelStages({ origen_stg: null, stg_dwh: null });
    }
  }, [origenTables]); // eslint-disable-line react-hooks/exhaustive-deps

  // Remove faded ktr log items after their CSS transition completes
  useEffect(() => {
    if (!ktrLogs.some(l => l.fading)) return;
    const t = setTimeout(() => setKtrLogs(prev => prev.filter(l => !l.fading)), 400);
    return () => clearTimeout(t);
  }, [ktrLogs]);

  // Stop polling /status if the component unmounts mid-generation
  useEffect(() => {
    return () => {
      if (pollTimeoutRef.current) clearTimeout(pollTimeoutRef.current);
    };
  }, []);

  // Block all route navigation (Back button, links, programmatic) while form is dirty
  const blocker = useBlocker(isDirty);

  // When fresh:true arrives (new mount OR same-route re-nav from Navbar after blocker),
  // reset the form. Defer the location-state cleanup via pendingClearStateRef so it only
  // fires once isDirty=false — calling navigate() while isDirty=true would re-trigger
  // the blocker and show the UnsavedChangesModal a second time.
  useEffect(() => {
    if (location.state?.fresh) {
      handleLimpiar();
      pendingClearStateRef.current = true;
    } else if (location.state?.initialFormData) {
      navigate(location.pathname, { replace: true, state: {} });
    }
  }, [location.state?.fresh, location.state?.initialFormData]); // eslint-disable-line react-hooks/exhaustive-deps

  // Warn on tab close / reload while dirty
  useEffect(() => {
    if (!isDirty) return;
    const handler = (e) => { e.preventDefault(); };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  }, [isDirty]);

  // Navigate after reset to avoid race with useBlocker (isDirty must be false first)
  useEffect(() => {
    if (!isDirty) {
      if (pendingNavigateRef.current) {
        const dest = pendingNavigateRef.current;
        pendingNavigateRef.current = null;
        navigate(dest);
      } else if (pendingClearStateRef.current) {
        pendingClearStateRef.current = false;
        navigate(location.pathname, { replace: true, state: {} });
      }
    }
  }, [isDirty, navigate]); // eslint-disable-line react-hooks/exhaustive-deps

  // Draft autosave on every change (includes inferResult so session refresh preserves it)
  useEffect(() => {
    saveDraft({ etlName, descripcionObjetivo, origenTables, reglasNegocio, inferResult });
  }, [etlName, descripcionObjetivo, origenTables, reglasNegocio, inferResult]); // eslint-disable-line react-hooks/exhaustive-deps

  const handleNameConfirm = () => {
    const trimmed = nameInputVal.trim();
    setValue("etlName", trimmed || "Nuevo ETL", { shouldDirty: true });
    setIsEditingName(false);
  };

  const _saveSnapshot = async () => {
    const values = getValues();
    const { id, syncStatus: ss } = await saveInProgressEtl(values.etlName, {
      ...values,
      inferResult,
      stg_definition: inferResult?.stg_ddl ?? null,
      dwh_model:      inferResult?.dwh_ddl ?? null,
    }, currentEtlIdRef.current);
    currentEtlIdRef.current = id;
    setSyncStatus(ss);
    return values;
  };

  const handleGuardar = async () => {
    const values = await _saveSnapshot();
    addToast("Guardado");
    pendingNavigateRef.current = "/home";
    reset(values); // isDirty → false → useEffect fires → navigate
  };

  const handleGuardarFromReview = async () => {
    await _saveSnapshot();
  };

  const handleRetrySync = async () => {
    await _saveSnapshot();
  };

  const handleLimpiar = () => {
    const empty = {
      etlName:             "Generar ETL",
      descripcionObjetivo: "",
      origenTables:        [],
      reglasNegocio:       "",
    };
    reset(empty);
    setNameInputVal("Generar ETL");
    setInferResult(null);
    setInferHistory([]);
    setModelStages({ origen_stg: null, stg_dwh: null });
    clearDraft();
    setStep(STEP.FORM);
  };

  const handleDownload = () => {
    downloadEtlSkeleton({
      ...getValues(),
      stg_definition: inferResult?.stg_ddl ?? null,
      dwh_model:      inferResult?.dwh_ddl ?? null,
    }, etlName);
  };

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    try {
      const formData = await importEtlSkeleton(file);
      const name = formData.etlName || "Transformación importada";
      setValue("etlName",             name,                          { shouldDirty: true });
      setValue("descripcionObjetivo", formData.descripcionObjetivo ?? "", { shouldDirty: true });
      setValue("origenTables",        formData.origenTables        ?? [], { shouldDirty: true });
      setValue("reglasNegocio",       formData.reglasNegocio       ?? "", { shouldDirty: true });
      setNameInputVal(name);
      // Sync ref BEFORE render so the stale-inferResult-clearing effect (which
      // fires on any origenTables change) doesn't immediately undo the
      // inferResult restore below — it'd see origenTables changed and wipe it.
      origenTablesSerialRef.current = JSON.stringify(formData.origenTables ?? []);
      setInferResult(
        formData.stg_definition || formData.dwh_model
          ? { stg_ddl: formData.stg_definition ?? "", dwh_ddl: formData.dwh_model ?? "" }
          : null
      );
      setInferHistory([]);
      setModelStages({ origen_stg: null, stg_dwh: null });
      setStep(STEP.FORM);
    } catch (err) {
      notifySystem(`Error al importar: ${err.message}`);
    }
  };

  const handleCargarEjemplo = () => {
    setValue("descripcionObjetivo", SAMPLE_ETL.descripcionObjetivo, { shouldDirty: true });
    setValue("origenTables",        SAMPLE_ETL.origenTables,        { shouldDirty: true });
    setValue("reglasNegocio",       SAMPLE_ETL.reglasNegocio,       { shouldDirty: true });
  };

  const serializeOrigen = () => JSON.stringify(origenTables, null, 2);

  // ── PASO 1 → PASO 2: llamar a /infer-structures ──────────────────────────
  const handleInfer = async () => {
    // Los requisitos mínimos se validan deshabilitando el botón (ver canInfer);
    // este guard es solo una red de seguridad, sin mensajes en pantalla.
    if (!canInfer) return;

    setStep(STEP.INFERRING);

    try {
      const data = await inferStructures({
        source_schema_json: serializeOrigen(),
        process_goal:        descripcionObjetivo,
        business_rules:      reglasNegocio,
      });
      setInferResult(data);
      setInferHistory([]);
      setStep(STEP.REVIEW);
    } catch (err) {
      setStep(STEP.FORM);
      notifySystem(`Error al inferir estructuras: ${err.message}`);
    }
  };

  // ── DESDE REVISIÓN: aplicar corrección ───────────────────────────────────
  const handleRefine = async (correction) => {
    setIsRefining(true);
    try {
      const data = await refineInference({
        source_schema_json:      serializeOrigen(),
        process_goal:            descripcionObjetivo,
        business_rules:          reglasNegocio,
        previous_stg:            inferResult.stg_ddl,
        previous_dwh:            inferResult.dwh_ddl,
        previous_dim_contracts:  inferResult.dim_contracts ?? [],
        correction,
        correction_history:      inferHistory,
      });
      setInferHistory(prev => [
        ...prev,
        { correction, stg_ddl: inferResult.stg_ddl, dwh_ddl: inferResult.dwh_ddl },
      ]);
      setInferResult(data);
      // Parte 4 (bloque B): un refinamiento que modifica el contrato de una
      // dimensión existente invalida cualquier respuesta cruda guardada de un
      // intento anterior — reutilizarla armaría el .ktr con steps pensados
      // para el contrato viejo. Forzar regeneración de las dos etapas.
      if (data.assumptions?.some(a => a.startsWith("CONTRATO MODIFICADO"))) {
        setModelStages({ origen_stg: null, stg_dwh: null });
      }
    } catch (err) {
      notifySystem(`Error al aplicar corrección: ${err.message}`);
    } finally {
      setIsRefining(false);
    }
  };

  // ── Persiste el ETL generado y navega a su detalle ────────────────────────
  const _finishEtl = async (apiResult, rawLlmDataUsed) => {
    const id = await addEtl({
      etlName,
      descripcionObjetivo,
      origenTables,
      reglasNegocio,
      stg_definition: inferResult?.stg_ddl ?? "",
      dwh_model:      inferResult?.dwh_ddl ?? "",
      // connections_map se pierde junto con el KtrBuildJob (TTL) — lo persistimos
      // acá para que el ETL guardado pueda resolver conn_dwh más adelante
      // (ej. validación de estado del DWH antes de exportar a Superset).
      connectionsMap: connectionsMapRef.current,
      // ktr_1/ktr_2 crudos (pre-XML) — el KtrBuildJob que los tenía expira a
      // los 30 min. Sin esto, la pestaña "Conexión" de EtlDetail no podría
      // reconstruir el .ktr con una conexión destino distinta más adelante
      // (ver POST /api/etls/{id}/connections).
      rawLlmData: rawLlmDataUsed ?? null,
    }, apiResult, etlName);
    setModelStages({ origen_stg: null, stg_dwh: null });
    const dest = `/etl/${id}`;
    if (isDirty) {
      pendingNavigateRef.current = dest;
      reset(getValues());
    } else {
      navigate(dest);
    }
  };

  // Si todas las tablas de origen comparten la misma conexión, se usa automático
  // (conn_origen) — el usuario no vuelve a cargarla en el paso de confirmación.
  const _deriveOrigenConnectionId = () => {
    const ids = [...new Set(
      (Array.isArray(origenTables) ? origenTables : [])
        .map(t => t.connection_id)
        .filter(Boolean)
    )];
    return ids.length === 1 ? ids[0] : null;
  };

  // Techo de polling alineado con _JOB_TTL_MINUTES del backend (30 min): si el
  // job nunca llega a un build_status terminal en ese lapso, algo se colgó del
  // lado del servidor — no tiene sentido seguir poleando indefinidamente.
  const POLL_INTERVAL_MS = 1200;
  const POLL_MAX_ATTEMPTS = Math.ceil((30 * 60 * 1000) / POLL_INTERVAL_MS);

  const _pollJobStatus = (job_id) => {
    let attempts = 0;
    const tick = async () => {
      attempts += 1;
      try {
        const status = await getJobStatus(job_id);
        if (status.model_status === "done") setEtlPhase("building");

        // D29: solo los eventos nuevos desde el último tick — el spinner de
        // "Esperando respuesta" pasa a mostrar hitos reales (auditoría de
        // DDL, llamadas al modelo, reintentos, reparación de steps).
        const events = status.progress ?? [];
        const nuevos = events.filter(e => e.seq > lastProgressSeqRef.current);
        if (nuevos.length) {
          lastProgressSeqRef.current = events[events.length - 1].seq;
          setKtrLogs(prev => mergeProgressLogs(prev, nuevos));
        }

        // D30/D32: se actualiza en CADA tick, no solo al terminar — así el
        // drawer de respuestas ya muestra "origen_stg lista" apenas se
        // checkpointeó, sin esperar a que la etapa 2 también termine.
        const stagesMap = stagesArrayToMap(status.stages);
        setModelStages(stagesMap);

        if (status.build_status === "built") {
          const raw = (stagesMap.origen_stg?.data && stagesMap.stg_dwh?.data)
            ? { ktr_1: stagesMap.origen_stg.data, ktr_2: stagesMap.stg_dwh.data }
            : null;
          await _finishEtl(status.result, raw);
          return;
        }
        if (status.build_status === "failed") {
          setStep(STEP.REVIEW);
          notifySystem(`Error al generar el ETL: ${status.error ?? "fallo desconocido"}`);
          return;
        }
      } catch (err) {
        setStep(STEP.REVIEW);
        notifySystem(`Error al consultar el estado de la generación: ${err.message}`);
        return;
      }
      if (attempts >= POLL_MAX_ATTEMPTS) {
        setStep(STEP.REVIEW);
        notifySystem("La generación del ETL tardó demasiado y fue cancelada. Intentá de nuevo.");
        return;
      }
      pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS);
    };
    tick();
  };

  // Se llama una sola vez, cuando el usuario confirma el formulario de
  // conexiones destino en DestinationConnections (botón "Generar" — cada
  // capa ya decidida como metadata completa o "Completar en Spoon"). Es la
  // única llamada a /connections de todo el flujo: antes de esto
  // connections_map es None y _try_build() nunca arma el .ktr, sin importar
  // si el modelo ya terminó (ver gate en _try_build, backend).
  const handleFinalizeConnections = (destMap) => {
    const fullMap = { ...connectionsMapRef.current, ...destMap };
    connectionsMapRef.current = fullMap;
    submitJobConnections(jobId, fullMap).catch(err => {
      notifySystem(`Error al registrar las conexiones: ${err.message}`);
    });
  };

  // ── DESDE REVISIÓN: confirmar y generar ETL ──────────────────────────────
  // Dispara el modelo en background (generate-async) y arranca el formulario
  // de conexiones destino en paralelo — no se espera al modelo para empezar
  // a pedirlas. build_ktr() en el backend no arma nada hasta que el usuario
  // confirma el formulario (ver handleFinalizeConnections).
  //
  // D31: reuseStage1, si viene (desde el drawer de respuestas), reenvía la
  // respuesta cruda ya guardada de origen→STG — el backend saltea esa
  // llamada al modelo (no la auditoría de DDL ni la etapa STG→DWH).
  const handleConfirm = async ({ reuseStage1 = null } = {}) => {
    setEtlPhase("waiting");
    setKtrLogs([]);
    lastProgressSeqRef.current = -1;
    setModelStages(prev => (
      reuseStage1 ? { ...prev, stg_dwh: null } : { origen_stg: null, stg_dwh: null }
    ));
    setJobId(null);
    connectionsMapRef.current = { conn_origen: _deriveOrigenConnectionId() };
    setStep(STEP.PROCESSING);

    try {
      const { job_id } = await generateAsync({
        descripcionObjetivo,
        origenTables,
        stg_definition: inferResult.stg_ddl,
        dwh_model:      inferResult.dwh_ddl,
        reglasNegocio,
        dim_contracts:  inferResult.dim_contracts ?? [],
        reuse_stage_1:  reuseStage1,
      });
      setJobId(job_id);

      _pollJobStatus(job_id);
    } catch (err) {
      setStep(STEP.REVIEW);
      notifySystem(`Error al generar el ETL: ${err.message}`);
    }
  };

  // ── DESDE EL DRAWER: reintentar reusando "Origen → STG" ──────────────────
  // A diferencia de handleReuseResponse (cero LLM), esto SÍ llama al modelo
  // — solo se salta la etapa 1 (D31/D33).
  const handleRetryReusingStage1 = () => {
    const stage1Data = modelStages.origen_stg?.data;
    if (!stage1Data) return;
    handleConfirm({ reuseStage1: stage1Data });
  };

  // ── DESDE EL DRAWER: reutilizar las dos respuestas ya guardadas ──────────
  // Salta la llamada al LLM por completo: reconstruye el .ktr en backend a
  // partir de rawLlmData (D33 — solo habilitado con las 2 etapas listas).
  const handleReuseResponse = async () => {
    if (!rawLlmData) return;
    setEtlPhase("building");
    setKtrLogs([]);
    setJobId(null); // reconstrucción directa desde JSON guardado — sin flujo async / conexiones paralelas
    setStep(STEP.PROCESSING);

    try {
      const apiResult = await buildFromRaw(rawLlmData, inferResult?.dim_contracts ?? []);
      await _finishEtl(apiResult, rawLlmData);
    } catch (err) {
      if (err.rawLlmData) {
        setModelStages({
          origen_stg: { status: "done", data: err.rawLlmData.ktr_1 ?? null, error: null },
          stg_dwh:    { status: "done", data: err.rawLlmData.ktr_2 ?? null, error: null },
        });
      }
      setStep(STEP.REVIEW);
      notifySystem(`Error al reconstruir el .ktr: ${err.message}`);
    }
  };

  // Descarga una sola etapa (D31/D33) — distinto de "Descargar todo", que
  // exporta el envelope etl_llm_raw completo y solo tiene sentido con las 2.
  const handleDownloadStage = (nombre) => {
    const data = modelStages[nombre]?.data;
    if (!data) return;
    downloadLlmStage(data, nombre, etlName);
  };

  const handleDownloadRaw = () => {
    if (!rawLlmData) return;
    downloadLlmRaw(rawLlmData, etlName);
  };

  // Acepta tanto un archivo completo (etl_llm_raw) como uno de una sola
  // etapa (etl_llm_stage, D31) — un solo input de archivo para el drawer.
  const handleImportModelResponse = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    try {
      const parsed = await importModelResponse(file);
      if (parsed.kind === "full") {
        setModelStages({
          origen_stg: { status: "done", data: parsed.raw_llm_data.ktr_1 ?? null, error: null },
          stg_dwh:    { status: "done", data: parsed.raw_llm_data.ktr_2 ?? null, error: null },
        });
      } else {
        setModelStages(prev => ({
          ...prev,
          [parsed.stage]: { status: "done", data: parsed.data, error: null },
        }));
      }
    } catch (err) {
      notifySystem(`Error al importar respuesta del modelo: ${err.message}`);
    }
  };

  return (
    <Layout>
      {blocker.state === "blocked" && (
        <ConfirmModal
          title="Tenés cambios sin guardar"
          message="Si salís ahora, se descartarán todos los cambios no guardados."
          confirmLabel="Descartar y salir"
          cancelLabel="Cancelar"
          onConfirm={() => blocker.proceed()}
          onCancel={() => blocker.reset()}
        />
      )}

      <div className="etl-page">
        <div className="etl-page__header">
          <div className="etl-header__logo-row">
            <img src={logo} alt="Logo" className="etl-header__logo" />
            {step === STEP.FORM && (
              isEditingName ? (
                <input
                  className="etl-title-input"
                  value={nameInputVal}
                  onChange={e => setNameInputVal(e.target.value)}
                  onBlur={handleNameConfirm}
                  onFocus={e => e.target.select()}
                  onKeyDown={e => {
                    if (e.key === "Enter") handleNameConfirm();
                    if (e.key === "Escape") { setNameInputVal(etlName); setIsEditingName(false); }
                  }}
                  autoFocus
                />
              ) : (
                <h1
                  className="etl-title etl-title--editable"
                  onClick={() => { setNameInputVal(etlName); setIsEditingName(true); }}
                >
                  {etlName}
                  <span className="etl-title-edit-hint">Editar</span>
                </h1>
              )
            )}
            {step !== STEP.FORM && step !== STEP.REVIEW && (
              <h1 className="etl-title">{etlName}</h1>
            )}
          </div>
          {syncStatus && (
            <span className={`etl-sync-badge etl-sync-badge--${syncStatus}`}>
              {syncStatus === "pending" && "Guardando…"}
              {syncStatus === "synced"  && "✓ Guardado"}
              {syncStatus === "failed"  && (
                <button className="etl-sync-retry" onClick={handleRetrySync}>
                  ⚠ Error de sync · Reintentar
                </button>
              )}
            </span>
          )}

          {step === STEP.REVIEW && (
            <input
              ref={importRawInputRef}
              type="file"
              accept=".json"
              style={{ display: "none" }}
              onChange={handleImportModelResponse}
            />
          )}

          {step === STEP.FORM && (
            <div className="etl-header-actions">
              <input
                ref={importInputRef}
                type="file"
                accept=".json"
                style={{ display: "none" }}
                onChange={handleImport}
              />
              <CreateETLOptions
                importInputRef={importInputRef}
                onDescargar={handleDownload}
                onLimpiar={handleLimpiar}
                onCargarEjemplo={handleCargarEjemplo}
              />
              <button
                className="etl-save-btn"
                disabled={!isDirty}
                onClick={handleGuardar}
              >
                Guardar
              </button>
              <span
                className="etl-infer-btn-wrap"
                title={canInfer ? undefined : `Faltan requisitos para inferir: ${missingToInfer.join(", ")}.`}
              >
                <button
                  className="etl-infer-header-btn"
                  onClick={handleInfer}
                  disabled={!canInfer}
                >
                  Inferir
                </button>
              </span>
              {inferResult && (
                <button
                  className="etl-infer-header-btn etl-infer-header-btn--next"
                  onClick={() => setStep(STEP.REVIEW)}
                >
                  Siguiente →
                </button>
              )}
            </div>
          )}
        </div>

        {step === STEP.INFERRING && (
          <div className="etl-processing">
            <EtlChecks message="Analizando origen e infiriendo estructuras STG y DWH..." />
          </div>
        )}

        {step === STEP.PROCESSING && jobId && (
          <div className="etl-processing etl-processing--split">
            <div className="etl-processing__connections">
              <DestinationConnections onFinalize={handleFinalizeConnections} />
            </div>
            <div className="etl-processing__checks">
              <EtlChecks phase={etlPhase} ktrLogs={ktrLogs} />
            </div>
          </div>
        )}

        {step === STEP.PROCESSING && !jobId && (
          <div className="etl-processing">
            <EtlChecks phase={etlPhase} ktrLogs={ktrLogs} />
          </div>
        )}

        {step === STEP.REVIEW && (
          <div className="etl-body">
            <InferenceReview
              inferResult={inferResult}
              etlName={etlName}
              onConfirm={handleConfirm}
              onRefine={handleRefine}
              onBack={() => setStep(STEP.FORM)}
              onGuardar={handleGuardarFromReview}
              isRefining={isRefining}
              modelStages={modelStages}
              modelResponsesOpen={modelResponsesOpen}
              onOpenModelResponses={() => setModelResponsesOpen(true)}
              onCloseModelResponses={() => setModelResponsesOpen(false)}
              onReuseResponse={handleReuseResponse}
              onRetryReusingStage1={handleRetryReusingStage1}
              onDownloadStage={handleDownloadStage}
              onDownloadRaw={handleDownloadRaw}
              onImportRaw={() => importRawInputRef.current?.click()}
            />
          </div>
        )}

        {step === STEP.FORM && (
          <div className="etl-body">
            <div className="etl-form-side">
              <DescripcionObjetivo
                value={descripcionObjetivo}
                onChange={(v) => setValue("descripcionObjetivo", v, { shouldDirty: true })}
              />
              <OrigenInput
                value={origenTables}
                onChange={(v) => setValue("origenTables", v, { shouldDirty: true })}
              />
              <ConfirmedTablesList
                tables={Array.isArray(origenTables) ? origenTables : []}
                onChange={(v) => setValue("origenTables", v, { shouldDirty: true })}
              />
            </div>

            <BusinessRules
              value={reglasNegocio}
              onChange={(v) => setValue("reglasNegocio", v, { shouldDirty: true })}
            />
          </div>
        )}
      </div>
    </Layout>
  );
}
