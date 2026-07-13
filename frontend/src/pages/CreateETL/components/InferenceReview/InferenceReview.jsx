import { useState } from "react";
import "../../css/inferenceReview.css";

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
  rawLlmData, onReuseResponse, onDownloadRaw, onImportRaw,
}) {
  const [correction, setCorrection] = useState("");

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
            onClick={onGuardar}
            disabled={isRefining}
          >
            Guardar
          </button>
          <button
            className="infer-btn infer-btn--primary"
            onClick={onConfirm}
            disabled={isRefining}
          >
            Confirmar y Generar
          </button>
        </div>
      </div>

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

      {rawLlmData ? (
        <div className="infer-review__raw-banner">
          <p>
            El modelo ya respondió, pero la construcción del .ktr falló en un intento anterior.
            Podés descargar esa respuesta para no perderla, o reutilizarla directamente sin volver a llamar al modelo.
          </p>
          <div className="infer-review__raw-actions">
            <button className="infer-btn infer-btn--secondary" onClick={onDownloadRaw}>
              ⬇ Descargar respuesta
            </button>
            <button className="infer-btn infer-btn--secondary" onClick={onImportRaw}>
              ⬆ Importar otra respuesta
            </button>
          </div>
        </div>
      ) : (
        <button className="infer-review__raw-import-link" onClick={onImportRaw}>
          ⬆ Importar una respuesta del modelo guardada anteriormente
        </button>
      )}

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
          {rawLlmData && (
            <button
              className="infer-btn infer-btn--primary"
              onClick={onReuseResponse}
              disabled={isRefining}
              title="Reconstruye el .ktr con la respuesta ya guardada, sin llamar al modelo de nuevo"
            >
              ↻ Reutilizar respuesta
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
