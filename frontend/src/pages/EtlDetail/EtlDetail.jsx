import { useEffect, useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import LineageView from "@/pages/EtlDetail/Lineage/LineageView";
import ResultView from "@/pages/EtlDetail/Result/ResultView";
import ConnectionView from "@/pages/EtlDetail/Connection/ConnectionView";
import { downloadKtrZipFromEtl } from "@/utils/etlCardActions";
import { readEtlArtifacts } from "@/utils/etlArtifacts";
import "./etlDetail-global.css";

export default function EtlDetail() {
  const { id } = useParams();
  const { etls, renameEtl } = useEtl();
  const navigate = useNavigate();
  const [pageTab, setPageTab] = useState("resultado");
  const [showScrollTop, setShowScrollTop] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [nameInputVal, setNameInputVal] = useState("");
  const [isSavingName, setIsSavingName] = useState(false);

  useEffect(() => {
    const onScroll = () => setShowScrollTop(window.scrollY > 400);
    window.addEventListener("scroll", onScroll);
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

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

  const isPending = etl.status === "pending";
  const lineage   = etl.result?.lineage ?? null;
  const art       = readEtlArtifacts(etl.result);
  // Fase 0 (S-14, docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md):
  // un Validacion tipo="error" (integridad de campos/contrato entre KTR/catálogo
  // de errores/validación pre-emisión) no bloquea la descarga (D15) pero exige
  // reconocimiento explícito antes de bajar el .ktr — ya no alcanza con que
  // viva distinguido en el panel de "Validaciones".
  const errorValidations = (etl.result?.validaciones ?? []).filter(v => v.tipo === "error");

  const startEditingName = () => {
    setNameInputVal(etl.name);
    setIsEditingName(true);
  };

  const cancelEditingName = () => {
    setIsEditingName(false);
    setNameInputVal(etl.name);
  };

  const handleRenameConfirm = async () => {
    const trimmed = nameInputVal.trim();
    if (!trimmed || trimmed === etl.name) {
      cancelEditingName();
      return;
    }
    setIsSavingName(true);
    try {
      await renameEtl(etl.id, trimmed);
      setIsEditingName(false);
    } catch (err) {
      alert(err.duplicateName
        ? `${err.message} Elegí otro nombre o tocá ✕ para descartar el cambio.`
        : (err?.message ?? "No se pudo renombrar el ETL."));
      // se queda en modo edición (isEditingName sigue true) — el usuario
      // puede corregir el nombre ahí mismo, o cancelar con ✕.
    } finally {
      setIsSavingName(false);
    }
  };

  const handleDownloadKtr = async () => {
    if (errorValidations.length > 0) {
      const proceed = window.confirm(
        `Este ETL tiene ${errorValidations.length} validación(es) de tipo error ` +
        "(ver sección «Validaciones» más abajo) — pueden causar que el .ktr falle " +
        "o produzca datos incorrectos en Spoon/Kitchen/Pan.\n\n" +
        "¿Descargar de todas formas?"
      );
      if (!proceed) return;
    }
    try {
      await downloadKtrZipFromEtl(etl);
    } catch (err) {
      alert(err?.message ?? "No se pudo descargar el .ktr.");
    }
  };

  return (
    <Layout>
      <div className={`etl-detail${pageTab === "linaje" ? " etl-detail--fill" : ""}`}>

        <div className="etl-detail__header">
          {isEditingName ? (
            <div className="etl-detail__title-edit">
              <input
                className="etl-detail__title-input"
                value={nameInputVal}
                onChange={e => setNameInputVal(e.target.value)}
                onFocus={e => e.target.select()}
                onKeyDown={e => {
                  if (e.key === "Enter") handleRenameConfirm();
                  if (e.key === "Escape") cancelEditingName();
                }}
                autoFocus
                disabled={isSavingName}
              />
              <button
                type="button"
                className="etl-detail__title-btn etl-detail__title-btn--confirm"
                onClick={handleRenameConfirm}
                disabled={isSavingName}
                title="Confirmar nombre"
              >
                {isSavingName ? "…" : "✓"}
              </button>
              <button
                type="button"
                className="etl-detail__title-btn etl-detail__title-btn--cancel"
                onClick={cancelEditingName}
                disabled={isSavingName}
                title="Cancelar"
              >
                ✕
              </button>
            </div>
          ) : (
            <h1
              className="etl-detail__title etl-detail__title--editable"
              onClick={startEditingName}
              title="Editar nombre"
            >
              {etl.name}
              <span className="etl-detail__title-edit-hint">Editar</span>
            </h1>
          )}
          <span className="etl-detail__date">
            {new Date(etl.createdAt).toLocaleDateString("es-AR", { dateStyle: "long" })}
          </span>
          <div className="etl-detail__actions">
            {etl.status === "done" && (
              <button
                className="ktr-download-btn"
                title="Reutilizar este ETL como base para uno nuevo"
                onClick={() => navigate("/etl-create", {
                  state: { initialFormData: { ...etl.formData, etlName: etl.name } },
                })}
              >
                Reutilizar
              </button>
            )}
            {art.status === "ok" ? (
              <button
                className="ktr-download-btn"
                onClick={handleDownloadKtr}
                title={art.splitEtapas.length > 0
                  ? `Zip: ${art.etapas.length} etapa(s), la etapa «${art.splitEtapas[0].nombre}» se dividió en ${art.splitEtapas[0].files.length} transformaciones — van en una carpeta junto a su .kjb`
                  : "Zip con el/los .ktr y el .kjb orquestador"}
              >
                {art.etapas.length > 1 || art.splitEtapas.length > 0
                  ? "Descargar Proceso Completo"
                  : "Descargar Transformación"}
              </button>
            ) : (
              <span className="ktr-unavailable" title={art.message}>
                {art.message}
              </span>
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
            onClick={() => !isPending && lineage && setPageTab("linaje")}
            disabled={isPending || !lineage}
            title={isPending ? "Generando ETL…" : !lineage ? "Este ETL no trae linaje — regeneralo" : undefined}
          >
            Linaje
            {isPending && <span className="etl-page-tab__hint">generando…</span>}
          </button>
          <button
            className={`etl-page-tab${pageTab === "conexion" ? " is-active" : ""}`}
            onClick={() => setPageTab("conexion")}
          >
            Conexión
          </button>
        </div>

        {/* ── Pestaña: Resultado ────────────────────────────────────────── */}
        {pageTab === "resultado" && (
          <ResultView result={etl.result} formData={etl.formData} />
        )}

        {/* ── Pestaña: Conexión ─────────────────────────────────────────── */}
        {pageTab === "conexion" && (
          <ConnectionView etl={etl} />
        )}

        {/* ── Pestaña: Linaje ───────────────────────────────────────────── */}
        {pageTab === "linaje" && (
          <div className="etl-lineage-body">
            {lineage && (
              <LineageView
                lineage={lineage}
                steps={etl.result?.proceso_etl?.steps ?? []}
              />
            )}
          </div>
        )}

      </div>

      {showScrollTop && (
        <button
          type="button"
          className="etl-scroll-top"
          onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
          aria-label="Subir al inicio de la página"
          title="Subir al inicio"
        >
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="18" height="18">
            <path d="M18 15l-6-6-6 6" />
          </svg>
        </button>
      )}
    </Layout>
  );
}
