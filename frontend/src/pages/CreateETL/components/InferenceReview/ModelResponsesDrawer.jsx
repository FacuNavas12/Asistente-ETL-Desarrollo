import "../../css/modelResponsesDrawer.css";

// D28 (docs/refactor/02-decisiones.md): orden y etiquetas canónicas de etapa
// — mismo criterio que utils/etlArtifacts.js.
const STAGE_ORDER = ["origen_stg", "stg_dwh"];
const STAGE_LABELS = { origen_stg: "Origen → STG", stg_dwh: "STG → DWH" };

function StatusDot({ stage }) {
  const kind = stage?.status === "failed" ? "error" : (stage?.data ? "ok" : "empty");
  return <span className={`mrd-dot mrd-dot--${kind}`} />;
}

function StatusLabel({ stage }) {
  switch (stage?.status) {
    case "done":    return <span className="mrd-card__status">guardada</span>;
    case "reused":  return <span className="mrd-card__status">reutilizada</span>;
    case "failed":  return <span className="mrd-card__status mrd-card__status--error">falló</span>;
    default:        return <span className="mrd-card__status">sin respuesta</span>;
  }
}

/**
 * D33 (docs/refactor/02-decisiones.md): drawer lateral con la respuesta
 * cruda del modelo por etapa. Reemplaza el banner + botón que antes vivían
 * pegados al textarea de corrección en InferenceReview.
 *
 * Dos acciones de fondo, no una sola deshabilitada: con las dos etapas
 * listas, "Reutilizar ambas" arma el .ktr sin llamar al modelo
 * (build-from-raw); con solo origen_stg, "Reintentar reusando" sí llama al
 * modelo (audita el DDL y genera STG→DWH de nuevo, D31).
 */
export default function ModelResponsesDrawer({
  open,
  onClose,
  modelStages,
  onDownloadStage,
  onDownloadAll,
  onImportClick,
  onReuseBoth,
  onRetryReusingStage1,
  disabled,
}) {
  if (!open) return null;

  const bothReady = STAGE_ORDER.every(k => modelStages[k]?.data);
  const stage1Only = !!modelStages.origen_stg?.data && !modelStages.stg_dwh?.data;

  return (
    <div className="mrd-overlay" onClick={onClose}>
      <div className="mrd-panel" onClick={(e) => e.stopPropagation()} role="dialog" aria-label="Respuestas del modelo">
        <div className="mrd-header">
          <h3 className="mrd-title">Respuestas del modelo</h3>
          <button className="mrd-close" onClick={onClose} aria-label="Cerrar">×</button>
        </div>

        <div className="mrd-body">
          {STAGE_ORDER.map((nombre) => {
            const stage = modelStages[nombre];
            return (
              <div key={nombre} className="mrd-card">
                <div className="mrd-card__row">
                  <StatusDot stage={stage} />
                  <span className="mrd-card__label">{STAGE_LABELS[nombre]}</span>
                  <StatusLabel stage={stage} />
                </div>
                {stage?.status === "failed" && stage.error && (
                  <p className="mrd-card__error">{stage.error}</p>
                )}
                {stage?.data && (
                  <div className="mrd-card__actions">
                    <button className="mrd-btn mrd-btn--sm" onClick={() => onDownloadStage(nombre)}>
                      ⬇ Descargar esta etapa
                    </button>
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <div className="mrd-footer">
          <div className="mrd-footer__row">
            <button className="mrd-btn mrd-btn--secondary" onClick={onImportClick} disabled={disabled}>
              ⬆ Importar una respuesta guardada
            </button>
            {bothReady && (
              <button className="mrd-btn mrd-btn--secondary" onClick={onDownloadAll}>
                ⬇ Descargar todo
              </button>
            )}
          </div>

          {bothReady && (
            <button
              className="mrd-btn mrd-btn--primary"
              onClick={onReuseBoth}
              disabled={disabled}
              title="Reconstruye el .ktr con las dos respuestas ya guardadas, sin llamar al modelo de nuevo"
            >
              ↻ Reutilizar ambas y armar el .ktr
            </button>
          )}

          {!bothReady && stage1Only && (
            <div className="mrd-retry">
              <button
                className="mrd-btn mrd-btn--primary"
                onClick={onRetryReusingStage1}
                disabled={disabled}
              >
                ↻ Reintentar reusando "{STAGE_LABELS.origen_stg}"
              </button>
              <p className="mrd-retry__hint">
                No se vuelve a llamar al modelo para esa etapa. Sí se audita el DDL y se genera {STAGE_LABELS.stg_dwh} de nuevo.
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
