import { useState, useEffect, useRef } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import LineageView from "@/pages/EtlDetail/Lineage/LineageView";
import ResultView from "@/pages/EtlDetail/Result/ResultView";
import { computeLineage } from "@/api/lineage";
import { generateSupersetZip } from "@/utils/supersetExport";
import "./etlDetail-global.css";

export default function EtlDetail() {
  const { id } = useParams();
  const { etls } = useEtl();
  const navigate = useNavigate();
  const [pageTab, setPageTab]               = useState("resultado");
  const [lineageData, setLineageData]       = useState(null);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError]     = useState(null);
  const [supersetBusy, setSupersetBusy]     = useState(false);
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

  const {
    ktr_xml = "", ktr_filename = "",
    ktr2_xml = "", ktr2_filename = "",
    kjb_xml = "", kjb_filename = "",
  } = etl.result ?? {};
  const hasTwoKtrFlow = Boolean(ktr2_xml && kjb_xml);

  const downloadBlob = (content, mime, filename) => {
    const blob = new Blob([content], { type: mime });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleDownloadKtr = () => {
    downloadBlob(ktr_xml, "application/xml", ktr_filename || `${etl.name}.ktr`);
    // Flujo de 2 KTR + 1 .kjb (origen→STG / STG→DWH orquestados en secuencia).
    // Vacíos en el flujo monolítico legacy (build-from-raw) — solo baja el único .ktr.
    if (hasTwoKtrFlow) {
      downloadBlob(ktr2_xml, "application/xml", ktr2_filename || `${etl.name}_2.ktr`);
      downloadBlob(kjb_xml, "application/xml", kjb_filename || `${etl.name}_job.kjb`);
    }
  };

  // Mostrar el botón siempre que haya KTR — si dwh_sample está vacío,
  // generateSupersetZip usa el KTR como fallback para extraer el esquema.
  const canExportSuperset = Boolean(etl.result?.ktr_xml);

  const handleExportSuperset = async () => {
    setSupersetBusy(true);
    try {
      const blob = await generateSupersetZip(etl);
      const url  = URL.createObjectURL(blob);
      const a    = document.createElement("a");
      a.href     = url;
      a.download = `superset_${etl.name}.zip`;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      alert(err?.message ?? "No se pudo generar el archivo Superset.");
    } finally {
      setSupersetBusy(false);
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
                {hasTwoKtrFlow
                  ? "Descargar KTR_1 + KTR_2 + .kjb para Pentaho PDI"
                  : "Descargar .ktr para Pentaho PDI"}
              </button>
            ) : (
              <span className="ktr-unavailable">No se pudo generar el .ktr</span>
            )}
            {canExportSuperset && (
              <button
                className="superset-export-btn"
                onClick={handleExportSuperset}
                disabled={supersetBusy}
              >
                {supersetBusy ? "Generando..." : "Exportar dashboard Superset"}
              </button>
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
