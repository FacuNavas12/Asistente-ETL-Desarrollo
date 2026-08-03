import { useState } from "react";
import "../../css/inferenceReview.css";
import ModelResponsesDrawer from "./ModelResponsesDrawer";

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };

  return (
    <button className="infer-panel__copy-btn" onClick={handleCopy} title="Copiar al portapapeles">
      {copied ? "✓ Copiado" : "Copiar"}
    </button>
  );
}

export default function InferenceReview({
  inferResult, etlName, onConfirm, onRefine, onBack, onGuardar, isRefining,
  modelStages, modelResponsesOpen, onOpenModelResponses, onCloseModelResponses,
  onReuseResponse, onRetryReusingStage1, onDownloadStage, onDownloadRaw, onImportRaw,
}) {
  const [correction, setCorrection] = useState("");
  const stagesReady = ["origen_stg", "stg_dwh"].filter(k => modelStages?.[k]?.data).length;

  const handleRefine = () => {
    if (!correction.trim()) return;
    onRefine(correction.trim());
    setCorrection("");
  };

  return (
    <div className="infer-review">
      <div className="infer-review__header">
        <div className="infer-review__header-side infer-review__header-side--left">
          <button
            className="infer-btn infer-btn--back"
            onClick={onBack}
            disabled={isRefining}
          >
            ← Volver
          </button>
        </div>

        <div className="infer-review__header-center">
          <h2 className="infer-review__title">
            Estructuras generadas para <span className="infer-review__title-name">{etlName}</span>
          </h2>
          <p className="infer-review__subtitle">
            Revisalas y confirmá cuando estés listo, o indicá qué querés ajustar.
          </p>
          {inferResult.iteration_count > 1 && (
            <span className="infer-review__iter-badge">
              Iteración {inferResult.iteration_count}
            </span>
          )}
        </div>

        <div className="infer-review__header-side infer-review__header-side--right">
          <button
            className="infer-btn infer-btn--secondary"
            onClick={onOpenModelResponses}
            disabled={isRefining}
            title="Respuestas crudas del modelo guardadas por etapa, o importar una respuesta ya descargada"
          >
            Respuestas del modelo <span className="infer-btn__badge">{stagesReady}/2</span>
          </button>
          <button
            className="infer-btn infer-btn--secondary"
            onClick={onGuardar}
            disabled={isRefining}
          >
            Guardar
          </button>
          <button
            className="infer-btn infer-btn--primary"
            onClick={() => onConfirm()}
            disabled={isRefining}
          >
            Confirmar y Generar
          </button>
        </div>
      </div>

      <ModelResponsesDrawer
        open={modelResponsesOpen}
        onClose={onCloseModelResponses}
        modelStages={modelStages ?? { origen_stg: null, stg_dwh: null }}
        onDownloadStage={onDownloadStage}
        onDownloadAll={onDownloadRaw}
        onImportClick={onImportRaw}
        onReuseBoth={onReuseResponse}
        onRetryReusingStage1={onRetryReusingStage1}
        disabled={isRefining}
      />

      <div className="infer-review__panels">
        <div className="infer-panel">
          <div className="infer-panel__header">
            <h3 className="infer-panel__title">Tabla STG</h3>
            <CopyButton text={inferResult.stg_ddl} />
          </div>
          <pre className="infer-panel__ddl">{inferResult.stg_ddl}</pre>
          {inferResult.stg_rationale && (
            <p className="infer-panel__rationale">
              <span className="infer-panel__rationale-icon">💡</span>
              {inferResult.stg_rationale}
            </p>
          )}
        </div>

        <div className="infer-panel">
          <div className="infer-panel__header">
            <h3 className="infer-panel__title">Modelo DWH</h3>
            <CopyButton text={inferResult.dwh_ddl} />
          </div>
          <pre className="infer-panel__ddl">{inferResult.dwh_ddl}</pre>
          {inferResult.dwh_rationale && (
            <p className="infer-panel__rationale">
              <span className="infer-panel__rationale-icon">💡</span>
              {inferResult.dwh_rationale}
            </p>
          )}
        </div>
      </div>

      <div className="infer-review__correction">
        <label className="infer-review__correction-label">¿Querés ajustar algo?</label>
        <div className="infer-review__correction-row">
          <textarea
            className="infer-review__correction-input"
            placeholder='Ej: "Agregá una columna fecha_baja a dim_cliente" o "La fact table necesita la métrica cantidad_unidades"'
            rows={3}
            value={correction}
            onChange={(e) => setCorrection(e.target.value)}
            disabled={isRefining}
          />
        </div>
        <div className="infer-review__actions">
          <button
            className="infer-btn infer-btn--secondary"
            onClick={handleRefine}
            disabled={!correction.trim() || isRefining}
          >
            {isRefining ? "Aplicando corrección..." : "Aplicar corrección"}
          </button>
        </div>
      </div>
    </div>
  );
}
