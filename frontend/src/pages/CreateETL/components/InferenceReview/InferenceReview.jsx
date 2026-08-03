import { useState, useRef } from "react";
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

// El DDL a veces llega con los saltos de línea escapados como "\n" literal
// (según cómo lo serialice el backend). Los convertimos a saltos reales antes
// de renderizar/copiar/parsear.
function unescapeDdl(ddl) {
  return (ddl ?? "").replace(/\\r\\n/g, "\n").replace(/\\n/g, "\n").replace(/\\t/g, "\t");
}

// Nombres de tabla reales declarados en el DDL (para el subtítulo del panel).
function extractTableNames(ddl) {
  const re = /CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?["`]?([A-Za-z0-9_.]+)["`]?/gi;
  const names = [];
  let m;
  while ((m = re.exec(unescapeDdl(ddl))) !== null) names.push(m[1]);
  return names;
}

// Ícono decorativo (26x26) a la izquierda del título del panel.
const TABLE_ICON = (
  <svg width="14" height="14" viewBox="0 0 16 16" fill="none"
       stroke="var(--accent)" strokeWidth="1.4" strokeLinecap="round">
    <rect x="2" y="2.75" width="12" height="10.5" rx="1.5" />
    <line x1="2" y1="6.25" x2="14" y2="6.25" />
    <line x1="7" y1="6.25" x2="7" y2="13.25" />
  </svg>
);

// Syntax highlighting básico del DDL: palabras clave (CREATE TABLE IF NOT
// EXISTS, PRIMARY KEY, ...) en color de acento; tipos de datos en azul
// secundario. Tokeniza y devuelve nodos React (nunca dangerouslySetInnerHTML).
const KW_SRC =
  "CREATE\\s+TABLE(?:\\s+IF\\s+NOT\\s+EXISTS)?|PRIMARY\\s+KEY|FOREIGN\\s+KEY|REFERENCES|NOT\\s+NULL|DEFAULT|UNIQUE|CONSTRAINT|CHECK";
const TYPE_SRC =
  "(?:VARCHAR|CHAR|NUMERIC|DECIMAL)\\s*\\([^)]*\\)|BIGSERIAL|SMALLSERIAL|SERIAL|BIGINT|SMALLINT|INTEGER|INT|BOOLEAN|BOOL|TIMESTAMPTZ|TIMESTAMP|DATETIME|DATE|TIME|TEXT|UUID|JSONB|JSON|MONEY|DOUBLE\\s+PRECISION|REAL|FLOAT|NUMERIC|DECIMAL|VARCHAR|CHAR";

function DdlBlock({ ddl }) {
  const text = unescapeDdl(ddl);
  const re = new RegExp(`(${KW_SRC})|(${TYPE_SRC})`, "gi");
  const nodes = [];
  let last = 0;
  let key = 0;
  let m;
  while ((m = re.exec(text)) !== null) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    if (m[1]) nodes.push(<span key={key++} className="ddl-kw">{m[0]}</span>);
    else nodes.push(<span key={key++} className="ddl-type">{m[0]}</span>);
    last = re.lastIndex;
  }
  if (last < text.length) nodes.push(text.slice(last));

  return <pre className="infer-panel__ddl">{nodes}</pre>;
}

function Panel({ label, ddl, rationale }) {
  const tables = extractTableNames(ddl);
  return (
    <div className="infer-panel">
      <div className="infer-panel__header">
        <div className="infer-panel__heading">
          <span className="infer-panel__icon" aria-hidden="true">{TABLE_ICON}</span>
          <div className="infer-panel__titles">
            <h3 className="infer-panel__title">{label}</h3>
            {tables.length > 0 && (
              <span className="infer-panel__tables">{tables.join(" · ")}</span>
            )}
          </div>
        </div>
        <CopyButton text={unescapeDdl(ddl)} />
      </div>
      <DdlBlock ddl={ddl} />
      {rationale && (
        <div className="infer-panel__rationale">
          <span className="infer-panel__rationale-icon">💡</span>
          <span>{rationale}</span>
        </div>
      )}
    </div>
  );
}

export default function InferenceReview({
  inferResult, etlName, onRefine, isRefining,
  modelStages, modelResponsesOpen, onCloseModelResponses,
  onReuseResponse, onRetryReusingStage1, onDownloadStage, onDownloadRaw, onImportRaw,
}) {
  // Volver / Respuestas del modelo / Guardar / Confirmar viven en el header
  // de la página (CreateETL.jsx), no acá — ver comment en inferenceReview.css.
  const [correction, setCorrection] = useState("");
  const correctionRef = useRef(null);

  // Auto-resize del textarea de corrección (arranca en una línea y crece con
  // el contenido) — solo cosmético, la lógica de corrección no cambia.
  const autoGrow = (el) => {
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  };

  const handleCorrectionChange = (e) => {
    setCorrection(e.target.value);
    autoGrow(e.target);
  };

  const handleRefine = () => {
    if (!correction.trim()) return;
    onRefine(correction.trim());
    setCorrection("");
    if (correctionRef.current) correctionRef.current.style.height = "auto";
  };

  return (
    <div className="infer-review">
      <div className="infer-review__header">
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
        <Panel label="Tabla STG" ddl={inferResult.stg_ddl} rationale={inferResult.stg_rationale} />
        <Panel label="Modelo DWH" ddl={inferResult.dwh_ddl} rationale={inferResult.dwh_rationale} />
      </div>

      <div className="infer-review__correction">
        <label className="infer-review__correction-label">¿Querés ajustar algo?</label>
        <div className="infer-review__correction-row">
          <textarea
            ref={correctionRef}
            className="infer-review__correction-input"
            placeholder='Ej: "Agregá una columna fecha_baja a dim_cliente"'
            rows={1}
            value={correction}
            onChange={handleCorrectionChange}
            disabled={isRefining}
          />
          <button
            className="infer-btn infer-btn--primary infer-review__correction-btn"
            onClick={handleRefine}
            disabled={!correction.trim() || isRefining}
          >
            {isRefining ? "Aplicando…" : "Aplicar corrección"}
          </button>
        </div>
      </div>
    </div>
  );
}
