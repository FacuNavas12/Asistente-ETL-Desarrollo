import { useState, useEffect, useRef } from "react";
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
import { downloadEtlSkeleton, downloadLlmRaw } from "@/utils/etlExport";
import { importEtlSkeleton, importLlmRaw } from "@/utils/etlImport";
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
  const { addToast } = useToast();

  // fresh: true → always open blank (navbar "Generación Nuevo ETL" button)
  // initialFormData → load from prior ETL (Continuar / Reutilizar)
  const initSource  = location.state?.fresh
    ? null
    : (location.state?.initialFormData ?? draft);

  const defaultName = initSource?.etlName ?? "";

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

  const [step,           setStep]           = useState(STEP.FORM);
  const [isEditingName,  setIsEditingName]  = useState(false);
  const [nameInputVal,   setNameInputVal]   = useState(defaultName);
  const [syncStatus,     setSyncStatus]     = useState(null); // null | "pending" | "synced" | "failed"
  const [inferResult,    setInferResult]    = useState(() => {
    if (initSource?.inferResult) return initSource.inferResult;
    if (initSource?.stg_definition || initSource?.dwh_model) {
      return { stg_definition: initSource.stg_definition ?? "", dwh_model: initSource.dwh_model ?? "" };
    }
    return null;
  });
  const [inferHistory,   setInferHistory]   = useState([]);
  const [isRefining,     setIsRefining]     = useState(false);
  const [errors,         setErrors]         = useState([]);
  const [etlPhase,       setEtlPhase]       = useState("waiting");
  const [ktrLogs,        setKtrLogs]        = useState([]);
  // Raw LLM response saved when build_ktr() fails server-side, so the (expensive) model
  // output isn't lost. null when there's nothing to reuse yet.
  const [rawLlmData,     setRawLlmData]     = useState(null);
  // job_id del flujo async (generate-async): el modelo corre en background mientras
  // el usuario completa las conexiones destino en paralelo (ver handleConfirm).
  const [jobId,          setJobId]          = useState(null);
  const connectionsMapRef       = useRef({});
  const pollTimeoutRef          = useRef(null);
  const pendingNavigateRef      = useRef(null);
  const pendingClearStateRef    = useRef(false);
  const importInputRef          = useRef(null);
  const importRawInputRef       = useRef(null);
  const currentEtlIdRef      = useRef(location.state?.etlId ?? null);
  // Track serialized tables to distinguish real changes from reference-only re-renders
  const origenTablesSerialRef = useRef(JSON.stringify(initSource?.origenTables ?? []));

  // Clear stale inferResult only when table content actually changes (not on reference-only re-renders).
  useEffect(() => {
    const curr = JSON.stringify(origenTables);
    if (curr === origenTablesSerialRef.current) return;
    origenTablesSerialRef.current = curr;
    if (inferResult) {
      setInferResult(null);
      setInferHistory([]);
      setRawLlmData(null);
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
      stg_definition: inferResult?.stg_definition ?? null,
      dwh_model:      inferResult?.dwh_model       ?? null,
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
      etlName:             "",
      descripcionObjetivo: "",
      origenTables:        [],
      reglasNegocio:       "",
    };
    reset(empty);
    setNameInputVal("");
    setInferResult(null);
    setInferHistory([]);
    setRawLlmData(null);
    clearDraft();
    setErrors([]);
    setStep(STEP.FORM);
  };

  const handleDownload = () => {
    downloadEtlSkeleton({
      ...getValues(),
      stg_definition: inferResult?.stg_definition ?? null,
      dwh_model:      inferResult?.dwh_model       ?? null,
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
      setInferResult(null);
      setInferHistory([]);
      setRawLlmData(null);
      setErrors([]);
      setStep(STEP.FORM);
    } catch (err) {
      setErrors([`Error al importar: ${err.message}`]);
    }
  };

  const handleCargarEjemplo = () => {
    setValue("descripcionObjetivo", SAMPLE_ETL.descripcionObjetivo, { shouldDirty: true });
    setValue("origenTables",        SAMPLE_ETL.origenTables,        { shouldDirty: true });
    setValue("reglasNegocio",       SAMPLE_ETL.reglasNegocio,       { shouldDirty: true });
    setErrors([]);
  };

  const serializeOrigen = () => JSON.stringify(origenTables, null, 2);

  // ── PASO 1 → PASO 2: llamar a /infer-structures ──────────────────────────
  const handleInfer = async () => {
    if (!origenTables.length) {
      setErrors(["Debe agregar al menos una tabla de origen."]);
      return;
    }
    if (!descripcionObjetivo.trim()) {
      setErrors(["Debe describir el objetivo del proceso."]);
      return;
    }
    if (!reglasNegocio.trim()) {
      setErrors(["Debe describir las reglas de negocio."]);
      return;
    }

    setErrors([]);
    setStep(STEP.INFERRING);

    try {
      const data = await inferStructures({
        source_structure:    serializeOrigen(),
        process_description: descripcionObjetivo,
        business_rules:      reglasNegocio,
      });
      setInferResult(data);
      setInferHistory([]);
      setStep(STEP.REVIEW);
    } catch (err) {
      setStep(STEP.FORM);
      setErrors([`Error al inferir estructuras: ${err.message}`]);
    }
  };

  // ── DESDE REVISIÓN: aplicar corrección ───────────────────────────────────
  const handleRefine = async (correction) => {
    setIsRefining(true);
    try {
      const data = await refineInference({
        source_structure:    serializeOrigen(),
        process_description: descripcionObjetivo,
        business_rules:      reglasNegocio,
        current_stg:         inferResult.stg_definition,
        current_dwh:         inferResult.dwh_model,
        correction,
        history:             inferHistory,
      });
      setInferHistory(prev => [
        ...prev,
        { correction, stg: inferResult.stg_definition, dwh: inferResult.dwh_model },
      ]);
      setInferResult(data);
    } catch (err) {
      setErrors([`Error al aplicar corrección: ${err.message}`]);
    } finally {
      setIsRefining(false);
    }
  };

  // ── Persiste el ETL generado y navega a su detalle ────────────────────────
  const _finishEtl = async (apiResult) => {
    const id = await addEtl({
      etlName,
      descripcionObjetivo,
      origenTables,
      reglasNegocio,
      stg_definition: inferResult?.stg_definition ?? "",
      dwh_model:      inferResult?.dwh_model       ?? "",
    }, apiResult, etlName);
    setRawLlmData(null);
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

        if (status.build_status === "built") {
          await _finishEtl(status.result);
          return;
        }
        if (status.build_status === "failed") {
          if (status.raw_llm_data) setRawLlmData(status.raw_llm_data);
          setStep(STEP.REVIEW);
          setErrors([`Error al generar el ETL: ${status.error ?? "fallo desconocido"}`]);
          return;
        }
      } catch (err) {
        setStep(STEP.REVIEW);
        setErrors([`Error al consultar el estado de la generación: ${err.message}`]);
        return;
      }
      if (attempts >= POLL_MAX_ATTEMPTS) {
        setStep(STEP.REVIEW);
        setErrors(["La generación del ETL tardó demasiado y fue cancelada. Intentá de nuevo."]);
        return;
      }
      pollTimeoutRef.current = setTimeout(tick, POLL_INTERVAL_MS);
    };
    tick();
  };

  // Se llama cada vez que una conexión destino (staging/DWH) termina de crearse
  // y testearse en DestinationConnections. Reenvía el mapa COMPLETO acumulado —
  // el endpoint reemplaza el mapa entero, no hace merge — sin importar si el
  // modelo ya terminó o no (la barrera del lado del servidor maneja el orden).
  const handleConnectionReady = (logicalName, connId) => {
    connectionsMapRef.current = { ...connectionsMapRef.current, [logicalName]: connId };
    if (!jobId) return;
    submitJobConnections(jobId, connectionsMapRef.current).catch(err => {
      setErrors([`Error al registrar la conexión: ${err.message}`]);
    });
  };

  // ── DESDE REVISIÓN: confirmar y generar ETL ──────────────────────────────
  // Dispara el modelo en background (generate-async) y arranca el formulario
  // de conexiones destino en paralelo — no se espera al modelo para empezar
  // a pedirlas. build_ktr() en el backend actúa de barrera entre ambos.
  const handleConfirm = async () => {
    setErrors([]);
    setEtlPhase("waiting");
    setKtrLogs([]);
    setRawLlmData(null);
    setJobId(null);
    connectionsMapRef.current = { conn_origen: _deriveOrigenConnectionId() };
    setStep(STEP.PROCESSING);

    try {
      const { job_id } = await generateAsync({
        descripcionObjetivo,
        origenTables,
        stg_definition: inferResult.stg_definition,
        dwh_model:      inferResult.dwh_model,
        reglasNegocio,
      });
      setJobId(job_id);

      if (connectionsMapRef.current.conn_origen) {
        submitJobConnections(job_id, connectionsMapRef.current).catch(() => {});
      }

      _pollJobStatus(job_id);
    } catch (err) {
      setStep(STEP.REVIEW);
      setErrors([`Error al generar el ETL: ${err.message}`]);
    }
  };

  // ── DESDE REVISIÓN: reutilizar una respuesta del modelo ya guardada ──────
  // Salta la llamada al LLM: reconstruye el .ktr en backend a partir de rawLlmData.
  const handleReuseResponse = async () => {
    if (!rawLlmData) return;
    setErrors([]);
    setEtlPhase("building");
    setKtrLogs([]);
    setJobId(null); // reconstrucción directa desde JSON guardado — sin flujo async / conexiones paralelas
    setStep(STEP.PROCESSING);

    try {
      const apiResult = await buildFromRaw(rawLlmData);
      await _finishEtl(apiResult);
    } catch (err) {
      if (err.rawLlmData) setRawLlmData(err.rawLlmData);
      setStep(STEP.REVIEW);
      setErrors([`Error al reconstruir el .ktr: ${err.message}`]);
    }
  };

  const handleDownloadRaw = () => {
    if (!rawLlmData) return;
    downloadLlmRaw(rawLlmData, etlName);
  };

  const handleImportRaw = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    try {
      const data = await importLlmRaw(file);
      setRawLlmData(data);
      setErrors([]);
    } catch (err) {
      setErrors([`Error al importar respuesta del modelo: ${err.message}`]);
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
          <div className="etl-header__title-block">
            <div className="etl-header__logo-row">
              <img src={logo} alt="Logo" className="etl-header__logo" />
              <h1 className="etl-title">Generación Nuevo ETL</h1>
            </div>
            <input
              className="etl-name-input"
              value={nameInputVal}
              onChange={e => setNameInputVal(e.target.value)}
              onBlur={handleNameConfirm}
              onKeyDown={e => { if (e.key === "Enter") e.target.blur(); }}
              placeholder="Agregue un nombre descriptivo a este proceso"
            />
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
            <div className="etl-header-actions">
              <input
                ref={importRawInputRef}
                type="file"
                accept=".json"
                style={{ display: "none" }}
                onChange={handleImportRaw}
              />
              <button className="etl-save-btn" onClick={handleGuardarFromReview}>
                Guardar
              </button>
            </div>
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
              <button className="etl-infer-header-btn" onClick={handleInfer}>
                Inferir
              </button>
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
              <DestinationConnections onConnectionReady={handleConnectionReady} />
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
            {errors.length > 0 && (
              <div className="etl-errors-box">
                <ul>{errors.map((e, i) => <li key={i}>{e}</li>)}</ul>
              </div>
            )}
            <InferenceReview
              inferResult={inferResult}
              onConfirm={handleConfirm}
              onRefine={handleRefine}
              onBack={() => setStep(STEP.FORM)}
              isRefining={isRefining}
              rawLlmData={rawLlmData}
              onReuseResponse={handleReuseResponse}
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

              {errors.length > 0 && (
                <div className="etl-errors-box">
                  <ul>{errors.map((err, i) => <li key={i}>{err}</li>)}</ul>
                </div>
              )}
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
