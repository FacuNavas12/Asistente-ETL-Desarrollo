import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import ChartPanel from "@/components/ui/ChartPanel";
import DataChartPanel from "@/components/ui/DataChartPanel";
import "./EtlDetail.css";

const VALIDATION_LABELS = { error: "Error", warning: "Advertencia", info: "Info" };

function StepCard({ step }) {
  return (
    <div className="etl-step-card">
      <div className="etl-step-card__header">
        <span className="etl-step-num">{step.orden}</span>
        <span className="etl-step-type">{step.tipo_step_pdi}</span>
        <span className="etl-step-name">{step.nombre}</span>
      </div>
      <p className="etl-step-desc">{step.descripcion}</p>
      {step.justificacion && (
        <p className="etl-step-just"><strong>Por qué:</strong> {step.justificacion}</p>
      )}
    </div>
  );
}

function ValidationItem({ v }) {
  return (
    <div className={`etl-validation etl-validation--${v.tipo}`}>
      <span className="etl-validation__badge">{VALIDATION_LABELS[v.tipo] ?? v.tipo}</span>
      <span className="etl-validation__campo">{v.campo}</span>
      <span className="etl-validation__msg">{v.mensaje}</span>
    </div>
  );
}

export default function EtlDetail() {
  const { id } = useParams();
  const { etls } = useEtl();
  const navigate = useNavigate();
  const [chartView, setChartView] = useState("data");
  const etl = etls.find(e => e.id === id);

  if (!etl) {
    return (
      <Layout>
        <div className="etl-detail-notfound">
          ETL no encontrado.
          <button onClick={() => navigate("/home")}>Volver al inicio</button>
        </div>
      </Layout>
    );
  }

  const { proceso_etl, validaciones = [], documentacion = "", advertencias_buenas_practicas = [], ktr_xml = "", ktr_filename = "" } = etl.result ?? {};

  const handleDownloadKtr = () => {
    const blob = new Blob([ktr_xml], { type: "application/xml" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = ktr_filename || `${etl.name}.ktr`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Layout>
      <div className="etl-detail">
        <div className="etl-detail__header">
          <h1 className="etl-detail__title">{etl.name}</h1>
          <span className="etl-detail__date">
            {new Date(etl.createdAt).toLocaleDateString("es-AR", { dateStyle: "long" })}
          </span>
          <div className="etl-detail__actions">
            {ktr_xml ? (
              <button className="ktr-download-btn" onClick={handleDownloadKtr}>
                Descargar .ktr para Pentaho PDI
              </button>
            ) : (
              <span className="ktr-unavailable">No se pudo generar el .ktr</span>
            )}
          </div>
        </div>

        <div className="etl-detail__body">

          {proceso_etl?.descripcion && (
            <div className="etl-section">
              <h2 className="etl-section__title">Descripción</h2>
              <p className="etl-section__text">{proceso_etl.descripcion}</p>
            </div>
          )}

          {proceso_etl?.steps?.length > 0 && (
            <div className="etl-section">
              <div className="etl-chart-tabs">
                <button
                  className={`etl-chart-tab ${chartView === "data" ? "is-active" : ""}`}
                  onClick={() => setChartView("data")}
                >
                  Datos limpios
                </button>
                <button
                  className={`etl-chart-tab ${chartView === "process" ? "is-active" : ""}`}
                  onClick={() => setChartView("process")}
                >
                  Estadísticas del proceso
                </button>
              </div>
              {chartView === "data"
                ? <DataChartPanel
                    dwhSample={etl.result?.dwh_sample ?? {}}
                    origenTables={etl.formData?.origenTables ?? []}
                  />
                : <ChartPanel data={etl.result} />}
            </div>
          )}

          {proceso_etl?.steps?.length > 0 && (
            <div className="etl-section">
              <h2 className="etl-section__title">Steps del proceso ({proceso_etl.steps.length})</h2>
              <div className="etl-steps-list">
                {proceso_etl.steps.map(s => <StepCard key={s.orden} step={s} />)}
              </div>
            </div>
          )}

          {validaciones.length > 0 && (
            <div className="etl-section">
              <h2 className="etl-section__title">Validaciones</h2>
              <div className="etl-validations-list">
                {validaciones.map((v, i) => <ValidationItem key={i} v={v} />)}
              </div>
            </div>
          )}

          {documentacion && (
            <div className="etl-section">
              <h2 className="etl-section__title">Documentación</h2>
              <div className="etl-section__text etl-doc">
                {documentacion.split("\n\n").map((p, i) => <p key={i}>{p}</p>)}
              </div>
            </div>
          )}

          {advertencias_buenas_practicas.length > 0 && (
            <div className="etl-section">
              <h2 className="etl-section__title">Buenas prácticas</h2>
              <ul className="etl-warnings-list">
                {advertencias_buenas_practicas.map((w, i) => <li key={i}>{w}</li>)}
              </ul>
            </div>
          )}

        </div>
      </div>
    </Layout>
  );
}
