import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import "./EtlDetail.css";

const TIPO_BADGE = { error: "badge--error", warning: "badge--warning", info: "badge--info" };

export default function EtlDetail() {
  const { id } = useParams();
  const { etls } = useEtl();
  const navigate = useNavigate();
  const etl = etls.find(e => e.id === id);

  const [explanation, setExplanation] = useState(null);
  const [loadingExplanation, setLoadingExplanation] = useState(false);
  const [explanationError, setExplanationError] = useState(null);

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

  const { generateResponse } = etl;
  const proceso = generateResponse?.proceso_etl;
  const validaciones = generateResponse?.validaciones ?? [];
  const advertencias = generateResponse?.advertencias_buenas_practicas ?? [];
  const docGenerada = generateResponse?.documentacion ?? "";

  const handleExplanation = async () => {
    setLoadingExplanation(true);
    setExplanationError(null);
    try {
      const res = await fetch("http://localhost:8000/api/v1/etl/document", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proceso_etl: proceso }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const data = await res.json();
      setExplanation(data.documentacion);
    } catch (err) {
      setExplanationError(err.message);
    } finally {
      setLoadingExplanation(false);
    }
  };

  return (
    <Layout>
      <div className="etl-detail">
        <div className="etl-detail__header">
          <h1 className="etl-detail__title">{etl.name}</h1>
          <span className="etl-detail__date">
            {new Date(etl.createdAt).toLocaleDateString("es-AR", { dateStyle: "long" })}
          </span>
        </div>

        {proceso && (
          <div className="etl-detail__section">
            <p className="etl-detail__desc">{proceso.descripcion}</p>

            <h2 className="etl-detail__subtitle">Steps PDI</h2>
            <ol className="etl-steps">
              {proceso.steps.map(step => (
                <li key={step.orden} className="etl-step">
                  <div className="etl-step__header">
                    <span className="etl-step__badge">{step.tipo_step_pdi}</span>
                    <strong>{step.nombre}</strong>
                  </div>
                  <p className="etl-step__desc">{step.descripcion}</p>
                  <p className="etl-step__just">{step.justificacion}</p>
                </li>
              ))}
            </ol>
          </div>
        )}

        {validaciones.length > 0 && (
          <div className="etl-detail__section">
            <h2 className="etl-detail__subtitle">Validaciones</h2>
            <ul className="etl-validaciones">
              {validaciones.map((v, i) => (
                <li key={i} className="etl-validacion">
                  <span className={`badge ${TIPO_BADGE[v.tipo] ?? ""}`}>{v.tipo}</span>
                  <span className="etl-validacion__campo">{v.campo}</span>
                  <span>{v.mensaje}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {advertencias.length > 0 && (
          <div className="etl-detail__section">
            <h2 className="etl-detail__subtitle">Advertencias buenas prácticas</h2>
            <ul className="etl-advertencias">
              {advertencias.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </div>
        )}

        {docGenerada && (
          <div className="etl-detail__section">
            <h2 className="etl-detail__subtitle">Documentación generada</h2>
            <p className="etl-detail__doc">{docGenerada}</p>
          </div>
        )}

        <div className="etl-detail__actions">
          <button
            className="etl-explanation-btn"
            onClick={handleExplanation}
            disabled={loadingExplanation || !proceso}
          >
            {loadingExplanation ? "Generando..." : "Explicación"}
          </button>
        </div>

        {explanationError && (
          <div className="etl-detail__error">{explanationError}</div>
        )}

        {explanation && (
          <div className="etl-detail__section">
            <h2 className="etl-detail__subtitle">Explicación detallada</h2>
            <p className="etl-detail__doc">{explanation}</p>
          </div>
        )}
      </div>
    </Layout>
  );
}
