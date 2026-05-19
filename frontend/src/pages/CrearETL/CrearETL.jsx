import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import OrigenInput from "./components/Input/InputForm";
import EtlChecks from "./components/EtlChecks";
import ReglasNegocio from "./components/BussinesRules/BussinesRulesForm";
import DescripcionObjetivo from "@/components/etl/DescripcionObjetivo";
import HomeModal from "./components/HomeModal";
import InferenceReview from "./components/InferenceReview/InferenceReview";
import "./CreateETL.css";
import "./etl-error.css";

const API = "http://localhost:8000";

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
  const { draft, saveDraft, clearDraft, addEtl } = useEtl();

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

  // Serializa origenTables a string JSON para el endpoint de inferencia
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
      const res = await fetch(`${API}/api/v1/etl/infer-structures`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_structure:    serializeOrigen(),
          process_description: descripcionObjetivo,
          business_rules:      reglasNegocio,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
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
      const res = await fetch(`${API}/api/v1/etl/infer-structures/refine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          source_structure:    serializeOrigen(),
          process_description: descripcionObjetivo,
          business_rules:      reglasNegocio,
          current_stg:         inferResult.stg_definition,
          current_dwh:         inferResult.dwh_model,
          correction,
          history:             inferHistory,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
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
      const res = await fetch(`${API}/api/v1/etl/generate-from-inference`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          descripcionObjetivo,
          origenTables,
          stg_definition: inferResult.stg_definition,
          dwh_model:      inferResult.dwh_model,
          reglasNegocio,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const apiResult = await res.json();
      const id = addEtl({ origenTables, reglasNegocio }, apiResult);
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
          onConfirm={() => navigate("/home")}
          onCancel={() => setShowModal(false)}
        />
      )}

      <div className="etl-page">
        <div className="etl-page__header">
          <h1 className="etl-title">Crear ETL</h1>
          {step === STEP.FORM && (
            <div className="etl-header-actions">
              <button className="etl-clear-btn" disabled={!dirty} onClick={handleLimpiar}>
                Limpiar
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
              <ReglasNegocio value={reglasNegocio} onChange={setReglasNegocio} />

              <button className="etl-submit-btn" onClick={handleInfer}>
                Inferir STG y DWH
              </button>

              {errors.length > 0 && (
                <div className="etl-errors-box">
                  <ul>{errors.map((err, i) => <li key={i}>{err}</li>)}</ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
