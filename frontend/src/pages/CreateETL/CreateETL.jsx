import { useState, useEffect, useRef } from "react";
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
import { SAMPLE_ETL } from "./utils/sampleEtl";
import { inferStructures, refineInference, generateFromInferenceStream } from "@/services/etlService";
import { useToast } from "@/components/ui/Toast";
import { downloadEtlSkeleton } from "@/utils/etlExport";
import { importEtlSkeleton } from "@/utils/etlImport";
import "./css/createETL.css";
import "./css/etlError.css";

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

  // fresh: true → always open blank (navbar "Nueva Transformación" button)
  // initialFormData → load from prior ETL (Continuar / Reutilizar)
  const initSource  = location.state?.fresh
    ? null
    : (location.state?.initialFormData ?? draft);

  const defaultName = initSource?.etlName ?? "Nueva Transformación";

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
  const pendingNavigateRef      = useRef(null);
  const pendingClearStateRef    = useRef(false);
  const importInputRef          = useRef(null);
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
    }
  }, [origenTables]); // eslint-disable-line react-hooks/exhaustive-deps

  // Remove faded ktr log items after their CSS transition completes
  useEffect(() => {
    if (!ktrLogs.some(l => l.fading)) return;
    const t = setTimeout(() => setKtrLogs(prev => prev.filter(l => !l.fading)), 400);
    return () => clearTimeout(t);
  }, [ktrLogs]);

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
    if (trimmed) setValue("etlName", trimmed, { shouldDirty: true });
    else setNameInputVal(etlName);
    setIsEditingName(false);
  };

  const handleGuardar = async () => {
    const values = getValues();
    const id = await saveInProgressEtl(values.etlName, {
      ...values,
      inferResult,
      stg_definition: inferResult?.stg_definition ?? null,
      dwh_model:      inferResult?.dwh_model       ?? null,
    }, currentEtlIdRef.current);
    currentEtlIdRef.current = id;
    addToast("Transformación guardada");
    pendingNavigateRef.current = "/home";
    reset(values); // isDirty → false → useEffect fires → navigate
  };

  const handleGuardarFromReview = async () => {
    const values = getValues();
    const id = await saveInProgressEtl(values.etlName, {
      ...values,
      inferResult,
      stg_definition: inferResult?.stg_definition ?? null,
      dwh_model:      inferResult?.dwh_model       ?? null,
    }, currentEtlIdRef.current);
    currentEtlIdRef.current = id;
    addToast("Transformación guardada");
  };

  const handleLimpiar = () => {
    const empty = {
      etlName:             "Nueva Transformación",
      descripcionObjetivo: "",
      origenTables:        [],
      reglasNegocio:       "",
    };
    reset(empty);
    setNameInputVal("Nueva Transformación");
    setInferResult(null);
    setInferHistory([]);
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

  // ── DESDE REVISIÓN: confirmar y generar ETL ───────────────────────────────
  const handleConfirm = async () => {
    setErrors([]);
    setEtlPhase("waiting");
    setKtrLogs([]);
    setStep(STEP.PROCESSING);

    let apiResult = null;

    try {
      await generateFromInferenceStream(
        {
          descripcionObjetivo,
          origenTables,
          stg_definition: inferResult.stg_definition,
          dwh_model:      inferResult.dwh_model,
          reglasNegocio,
        },
        {
          onLlmDone: () => setEtlPhase("building"),
          onKtrLog: (msg) => setKtrLogs(prev => {
            const next = prev.map((l, i) =>
              prev.length >= 4 && i === 0 ? { ...l, fading: true } : l
            );
            return [...next, { id: Date.now() + Math.random(), message: msg, fading: false }];
          }),
          onResult: (data) => { apiResult = data; },
        },
      );

      if (!apiResult) throw new Error("No se recibió resultado del servidor.");

      const id = await addEtl({
        etlName,
        descripcionObjetivo,
        origenTables,
        reglasNegocio,
        stg_definition: inferResult?.stg_definition ?? "",
        dwh_model:      inferResult?.dwh_model       ?? "",
      }, apiResult, etlName);
      const dest = `/etl/${id}`;
      if (isDirty) {
        pendingNavigateRef.current = dest;
        reset(getValues());
      } else {
        navigate(dest);
      }
    } catch (err) {
      setStep(STEP.REVIEW);
      setErrors([`Error al generar el ETL: ${err.message}`]);
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
          {isEditingName ? (
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
          )}
          {step === STEP.REVIEW && (
            <div className="etl-header-actions">
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
              <button
                className="etl-clear-btn"
                onClick={() => importInputRef.current?.click()}
                title="Importar transformación desde archivo .json"
              >
                Importar
              </button>
              <button
                className="etl-clear-btn"
                onClick={handleDownload}
                title="Descargar transformación como archivo .json"
              >
                Descargar
              </button>
              <button
                className="etl-clear-btn"
                onClick={handleCargarEjemplo}
                title="Completar el formulario con un caso de ejemplo (ventas)"
              >
                Cargar ejemplo
              </button>
              <button className="etl-clear-btn" disabled={!isDirty} onClick={handleLimpiar}>
                Limpiar
              </button>
              <button
                className="etl-save-btn"
                disabled={!isDirty}
                onClick={handleGuardar}
              >
                Guardar
              </button>
              <button className="etl-infer-header-btn" onClick={handleInfer}>
                Inferir STG y DWH
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

        {step === STEP.PROCESSING && (
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
