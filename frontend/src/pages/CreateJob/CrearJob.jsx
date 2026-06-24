import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import { useAuthFetch } from "@/hooks/useAuthFetch";
import Layout from "@/components/layout/Layout";
import EtlChecks from "../CreateETL/components/EtlChecks";
import ConfirmModal from "@/components/ui/ConfirmModal";
import JobForm from "./components/JobForm";
import JobReview from "./components/JobReview";
import JobResult from "./components/JobResult";
import { analyzeJob, refineJob, generateJob } from "@/services/jobService";
import { generateSupersetZip, extractDwhSchemaFromKtrs } from "@/utils/supersetExport";
import "./crearJob.css";

const STEP = {
  FORM:       "form",
  ANALYZING:  "analyzing",
  REVIEW:     "review",
  GENERATING: "generating",
  RESULT:     "result",
};

export default function CrearJob() {
  const navigate = useNavigate();
  const { etls, jobs, addJob, savePendingJob } = useEtl();
  const authFetch = useAuthFetch();

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
  const [supersetBusy,  setSupersetBusy]  = useState(false);

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
      const data = await analyzeJob({
        ktrFiles,
        job_description: jobDescription,
        business_rules:  businessRules,
      });
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
      const data = await refineJob({
        session_id:       sessionId,
        job_description:  jobDescription,
        business_rules:   businessRules || null,
        current_job_plan: analyzeResult.job_plan,
        correction,
        history:          jobHistory,
      });
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
      const data = await generateJob({
        session_id: sessionId,
        job_plan:   analyzeResult.job_plan,
      });
      setJobResult(data);
      addJob({ jobDescription, businessRules }, data);
      setStep(STEP.RESULT);
    } catch (err) {
      setStep(STEP.REVIEW);
      setErrors([`Error al generar el job: ${err.message}`]);
    }
  };

  const handleExportSuperset = async () => {
    setSupersetBusy(true);
    try {
      // Matchear los KTRs del job con ETLs guardados por ktr_filename (con y sin extensión)
      const jobFilenames = new Set(
        (jobResult.job_plan.execution_order ?? []).flatMap(e => [
          e.filename,
          e.filename?.replace(/\.ktr$/i, ""),
        ]).filter(Boolean)
      );
      const matchingEtls = etls.filter(e => {
        const ktr = e.result?.ktr_filename;
        if (!ktr) return false;
        return jobFilenames.has(ktr) || jobFilenames.has(ktr.replace(/\.ktr$/i, ""));
      });

      let dwh_sample = matchingEtls.reduce((acc, e) => ({ ...acc, ...(e.result?.dwh_sample ?? {}) }), {});

      // Fallback: extraer esquema directamente de los archivos KTR subidos
      if (!Object.keys(dwh_sample).length && ktrFiles.length > 0) {
        dwh_sample = await extractDwhSchemaFromKtrs(ktrFiles);
      }

      if (!Object.keys(dwh_sample).length) {
        alert(
          "No se encontraron tablas DWH en los archivos KTR.\n\n" +
          "Asegurate de que los archivos KTR incluyan pasos de tipo 'Table output' con las tablas de destino configuradas."
        );
        return;
      }

      const blob = await generateSupersetZip({
        name: jobResult.job_plan.job_name,
        result: { dwh_sample },
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `superset_${jobResult.job_plan.job_name}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err?.message ?? "No se pudo generar el archivo Superset.");
    } finally {
      setSupersetBusy(false);
    }
  };

  return (
    <Layout onHomeClick={() => setShowModal(true)}>
      {showModal && (
        <ConfirmModal
          title="Tenés cambios sin guardar"
          message="Si salís ahora, se descartarán todos los cambios no guardados."
          confirmLabel="Descartar y salir"
          cancelLabel="Cancelar"
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
          <JobResult
            result={jobResult}
            onNew={handleLimpiar}
            onExportSuperset={handleExportSuperset}
            supersetBusy={supersetBusy}
          />
        )}
      </div>
    </Layout>
  );
}
