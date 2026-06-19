import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import LineageView from "@/pages/EtlDetail/Lineage/LineageView";
import ResultView from "@/pages/EtlDetail/Result/ResultView";
import { computeLineage } from "@/api/lineage";
import "./etlDetail-global.css";

export default function EtlDetail() {
  const { id } = useParams();
  const { etls } = useEtl();
  const navigate = useNavigate();
  const [pageTab, setPageTab]               = useState("resultado");
  const [lineageData, setLineageData]       = useState(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError]     = useState(null);
  const loadedForId = useRef(null);

  const etl = etls.find(e => e.id === id);

  useEffect(() => {
    if (pageTab !== "linaje") return;
    if (!etl) return;

    if (etl.result?.lineage) {
      setLineageData(etl.result.lineage);
      return;
    }

    if (loadedForId.current === etl.id) return;

    const ktrXml = etl.result?.ktr_xml;
    if (!ktrXml) return;

    loadedForId.current = etl.id;
    setLineageLoading(true);
    setLineageError(null);

    computeLineage(ktrXml)
      .then(data => {
        setLineageData(data);
        setLineageLoading(false);
      })
      .catch(err => {
        setLineageError(err.message ?? "Error al calcular el linaje.");
        setLineageLoading(false);
        loadedForId.current = null;
      });
  }, [pageTab, etl]);

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

  const isPending = etl.status === "pending";
  const hasKtr    = Boolean(etl.result?.ktr_xml);
  const lineage   = lineageData ?? etl.result?.lineage ?? null;

  const { ktr_xml = "", ktr_filename = "" } = etl.result ?? {};

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
            {etl.status === "done" && (
              <button
                className="etl-reuse-btn"
                onClick={() => navigate("/etl-create", {
                  state: { initialFormData: { ...etl.formData, etlName: etl.name } },
                })}
              >
                Reutilizar
              </button>
            )}
            {ktr_xml ? (
              <button className="ktr-download-btn" onClick={handleDownloadKtr}>
                Descargar .ktr para Pentaho PDI
              </button>
            ) : (
              <span className="ktr-unavailable">No se pudo generar el .ktr</span>
            )}
          </div>
        </div>

        {/* ── Pestañas de página ────────────────────────────────────────── */}
        <div className="etl-page-tabs">
          <button
            className={`etl-page-tab${pageTab === "resultado" ? " is-active" : ""}`}
            onClick={() => setPageTab("resultado")}
          >
            Resultado
          </button>
          <button
            className={`etl-page-tab${pageTab === "linaje" ? " is-active" : ""}`}
            onClick={() => !isPending && hasKtr && setPageTab("linaje")}
            disabled={isPending || !hasKtr}
            title={isPending ? "Generando ETL…" : !hasKtr ? "Sin KTR disponible" : undefined}
          >
            Linaje
            {isPending && <span className="etl-page-tab__hint">generando…</span>}
          </button>
        </div>

        {/* ── Pestaña: Resultado ────────────────────────────────────────── */}
        {pageTab === "resultado" && (
          <ResultView result={etl.result} formData={etl.formData} />
        )}

        {/* ── Pestaña: Linaje ───────────────────────────────────────────── */}
        {pageTab === "linaje" && (
          <div className="etl-lineage-body">
            {lineageLoading && (
              <div className="etl-lineage-loading">Calculando linaje…</div>
            )}
            {lineageError && (
              <div className="etl-lineage-error">{lineageError}</div>
            )}
            {!lineageLoading && !lineageError && lineage && (
              <LineageView
                lineage={lineage}
                steps={etl.result?.proceso_etl?.steps ?? []}
              />
            )}
          </div>
        )}

      </div>
    </Layout>
  );
}
