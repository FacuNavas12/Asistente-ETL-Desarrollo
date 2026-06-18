import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import { useAuthFetch } from "@/hooks/useAuthFetch";
import Layout from "@/components/layout/Layout";
import OrigenInput from "./components/Input/InputForm";
import EtlChecks from "./components/EtlChecks";
import BusinessRules from "./components/BussinesRules/BusinessRules";
import DescripcionObjetivo from "./components/Goal/GoalDescription";
import HomeModal from "./components/HomeModal";
import InferenceReview from "./components/InferenceReview/InferenceReview";
import { SAMPLE_ETL } from "./utils/sampleEtl";
import { inferStructures, refineInference, generateFromInference } from "@/services/etlService";
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

function isDirty(origenTables, reglasNegocio, descripcionObjetivo) {
  return (
    origenTables.length > 0 ||
    reglasNegocio.trim().length > 0 ||
    descripcionObjetivo.trim().length > 0
  );
}

export default function CreateETL() {
  const navigate   = useNavigate();
  const { draft, saveDraft, clearDraft, addEtl, savePendingEtl, etls } = useEtl();
  const authFetch  = useAuthFetch();

  const [step, setStep]       = useState(STEP.FORM);
  const [showModal, setShowModal] = useState(false);
  // Campos del formulario (3)
  const [descripcionObjetivo, setDescripcionObjetivo] = useState(draft?.descripcionObjetivo ?? "");
  const [origenTables,        setOrigenTables]        = useState(draft?.origenTables ?? []);
  const [reglasNegocio,       setReglasNegocio]       = useState(draft?.reglasNegocio ?? "");

  // Estado del flujo de inferencia
  const [inferResult,      setInferResult]      = useState(null);
  const [inferHistory,     setInferHistory]     = useState([]);
  const [isRefining,       setIsRefining]       = useState(false);
  const [errors,           setErrors]           = useState([]);

  useEffect(() => {
    saveDraft({ descripcionObjetivo, origenTables, reglasNegocio });
  }, [descripcionObjetivo, origenTables, reglasNegocio]);

  const dirty = isDirty(origenTables, reglasNegocio, descripcionObjetivo);

  const handleLimpiar = () => {
    setDescripcionObjetivo("");
    setOrigenTables([]);
    setReglasNegocio("");
    setInferResult(null);
    setInferHistory([]);
    clearDraft();
    setErrors([]);
    setStep(STEP.FORM);
  };

  const handleCargarEjemplo = () => {
    setDescripcionObjetivo(SAMPLE_ETL.descripcionObjetivo);
    setOrigenTables(SAMPLE_ETL.origenTables);
    setReglasNegocio(SAMPLE_ETL.reglasNegocio);
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
    setStep(STEP.PROCESSING);

    try {
      const apiResult = await generateFromInference({
        descripcionObjetivo,
        origenTables,
        stg_definition: inferResult.stg_definition,
        dwh_model:      inferResult.dwh_model,
        reglasNegocio,
      });
      const id = addEtl({
        origenTables,
        reglasNegocio,
        stg_definition: inferResult?.stg_definition ?? "",
        dwh_model: inferResult?.dwh_model ?? "",
      }, apiResult);
      navigate(`/etl/${id}`);
    } catch (err) {
      setStep(STEP.REVIEW);
      setErrors([`Error al generar el ETL: ${err.message}`]);
    }
  };

  return (
    <Layout onHomeClick={() => setShowModal(true)}>
      {showModal && (
        <HomeModal
          onConfirm={() => {
            if (dirty) {
              const name = (descripcionObjetivo.trim().split("\n")[0] || `ETL #${etls.length + 1}`).slice(0, 50);
              savePendingEtl(name, { descripcionObjetivo, origenTables, reglasNegocio });
            }
            navigate("/home");
          }}
          onCancel={() => setShowModal(false)}
        />
      )}

      <div className="etl-page">
        <div className="etl-page__header">
          <h1 className="etl-title">Crear Transformación</h1>
          {step === STEP.FORM && (
            <div className="etl-header-actions">
              <button
                className="etl-clear-btn"
                onClick={handleCargarEjemplo}
                title="Completar el formulario con un caso de ejemplo (ventas)"
              >
                Cargar ejemplo
              </button>
              <button className="etl-clear-btn" disabled={!dirty} onClick={handleLimpiar}>
                Limpiar
              </button>
              <button className="etl-infer-header-btn" onClick={handleInfer}>
                Inferir STG y DWH
              </button>
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
            <EtlChecks />
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
              isRefining={isRefining}
            />
          </div>
        )}

        {step === STEP.FORM && (
          <div className="etl-body">
            <div className="etl-form-side">
              <DescripcionObjetivo value={descripcionObjetivo} onChange={setDescripcionObjetivo} />
              <OrigenInput value={origenTables} onChange={setOrigenTables} />

              {errors.length > 0 && (
                <div className="etl-errors-box">
                  <ul>{errors.map((err, i) => <li key={i}>{err}</li>)}</ul>
                </div>
              )}
            </div>

            <BusinessRules value={reglasNegocio} onChange={setReglasNegocio} />
          </div>
        )}
      </div>
    </Layout>
  );
}
