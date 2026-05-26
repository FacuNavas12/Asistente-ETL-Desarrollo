import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import EtlChecks from "../CreateETL/components/EtlChecks";
import HomeModal from "../CreateETL/components/HomeModal";
import JobForm from "./components/JobForm";
import JobReview from "./components/JobReview";
import JobResult from "./components/JobResult";
import "./crearJob.css";

const API = "http://localhost:8000";

const STEP = {
  FORM:       "form",
  ANALYZING:  "analyzing",
  REVIEW:     "review",
  GENERATING: "generating",
  RESULT:     "result",
};

export default function CrearJob() {
  const navigate = useNavigate();
  const { jobs, addJob, savePendingJob } = useEtl();

  const [step, setStep]           = useState(STEP.FORM);
  const [showModal, setShowModal] = useState(false);

  // Formulario
  const [ktrFiles,       setKtrFiles]       = useState([]);
  const [jobDescription, setJobDescription] = useState("");
  const [businessRules,  setBusinessRules]  = useState("");

  // Flujo de análisis/refinamiento
  const [analyzeResult, setAnalyzeResult] = useState(null);
  const [sessionId,     setSessionId]     = useState(null);
  const [jobHistory,    setJobHistory]    = useState([]);
  const [isRefining,    setIsRefining]    = useState(false);
  const [jobResult,     setJobResult]     = useState(null);
  const [errors,        setErrors]        = useState([]);

  const dirty = ktrFiles.length > 0 || jobDescription.trim().length > 0;

  const handleLimpiar = () => {
    setKtrFiles([]);
    setJobDescription("");
    setBusinessRules("");
    setAnalyzeResult(null);
    setSessionId(null);
    setJobHistory([]);
    setJobResult(null);
    setErrors([]);
    setStep(STEP.FORM);
  };

  const handleKtrAdd = (newFiles) => {
    setKtrFiles((prev) => {
      const existingNames = new Set(prev.map((f) => f.name));
      const unique = newFiles.filter((f) => !existingNames.has(f.name));
      return [...prev, ...unique];
    });
  };

  const handleKtrRemove = (index) => {
    setKtrFiles((prev) => prev.filter((_, i) => i !== index));
  };

  // ── PASO 1 → PASO 2: analizar job ────────────────────────────────────────
  const handleAnalyze = async () => {
    if (!ktrFiles.length) {
      setErrors(["Debe subir al menos un archivo .ktr."]);
      return;
    }
    if (!jobDescription.trim()) {
      setErrors(["Debe describir el job."]);
      return;
    }

    setErrors([]);
    setStep(STEP.ANALYZING);

    try {
      const formData = new FormData();
      ktrFiles.forEach((f) => formData.append("ktr_files", f));
      formData.append("job_description", jobDescription);
      if (businessRules.trim()) formData.append("business_rules", businessRules);

      const res = await fetch(`${API}/api/v1/job/analyze`, {
        method: "POST",
        body: formData,
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setAnalyzeResult(data);
      setSessionId(data.session_id);
      setJobHistory([]);
      setStep(STEP.REVIEW);
    } catch (err) {
      setStep(STEP.FORM);
      setErrors([`Error al analizar el job: ${err.message}`]);
    }
  };

  // ── DESDE REVISIÓN: aplicar corrección ───────────────────────────────────
  const handleRefine = async (correction) => {
    setIsRefining(true);
    try {
      const res = await fetch(`${API}/api/v1/job/refine`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id:       sessionId,
          job_description:  jobDescription,
          business_rules:   businessRules || null,
          current_job_plan: analyzeResult.job_plan,
          correction,
          history:          jobHistory,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setJobHistory((prev) => [
        ...prev,
        { correction, job_plan: analyzeResult.job_plan },
      ]);
      setAnalyzeResult(data);
    } catch (err) {
      setErrors([`Error al aplicar corrección: ${err.message}`]);
    } finally {
      setIsRefining(false);
    }
  };

  // ── DESDE REVISIÓN: confirmar y generar .kjb ─────────────────────────────
  const handleConfirm = async () => {
    setErrors([]);
    setStep(STEP.GENERATING);

    try {
      const res = await fetch(`${API}/api/v1/job/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          session_id: sessionId,
          job_plan:   analyzeResult.job_plan,
        }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setJobResult(data);
      addJob({ jobDescription, businessRules }, data);
      setStep(STEP.RESULT);
    } catch (err) {
      setStep(STEP.REVIEW);
      setErrors([`Error al generar el job: ${err.message}`]);
    }
  };

  return (
    <Layout onHomeClick={() => setShowModal(true)}>
      {showModal && (
        <HomeModal
          onConfirm={() => {
            if (dirty) {
              const name = (jobDescription.trim().split("\n")[0] || `Job #${jobs.length + 1}`).slice(0, 50);
              savePendingJob(name, { jobDescription, businessRules });
            }
            navigate("/home");
          }}
          onCancel={() => setShowModal(false)}
        />
      )}

      <div className="job-page">
        <div className="job-page__header">
          <h1 className="job-title">Crear Job PDI</h1>
          {(step === STEP.FORM || step === STEP.REVIEW) && (
            <button
              className="job-clear-btn"
              disabled={!dirty && step === STEP.FORM}
              onClick={handleLimpiar}
            >
              Limpiar
            </button>
          )}
        </div>

        {step === STEP.ANALYZING && (
          <div className="job-processing">
            <EtlChecks message="Analizando transformaciones e infiriendo orden de ejecución..." />
          </div>
        )}

        {step === STEP.GENERATING && (
          <div className="job-processing">
            <EtlChecks message="Generando el archivo .kjb para Pentaho PDI..." />
          </div>
        )}

        {step === STEP.FORM && (
          <JobForm
            ktrFiles={ktrFiles}
            onKtrAdd={handleKtrAdd}
            onKtrRemove={handleKtrRemove}
            jobDescription={jobDescription}
            onJobDescription={setJobDescription}
            businessRules={businessRules}
            onBusinessRules={setBusinessRules}
            onSubmit={handleAnalyze}
            onLimpiar={handleLimpiar}
            dirty={dirty}
            errors={errors}
          />
        )}

        {step === STEP.REVIEW && analyzeResult && (
          <JobReview
            analyzeResult={analyzeResult}
            onConfirm={handleConfirm}
            onRefine={handleRefine}
            isRefining={isRefining}
            errors={errors}
          />
        )}

        {step === STEP.RESULT && jobResult && (
          <JobResult result={jobResult} onNew={handleLimpiar} />
        )}
      </div>
    </Layout>
  );
}
