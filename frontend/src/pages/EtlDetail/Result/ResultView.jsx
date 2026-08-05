import { useState } from "react";
import ChartPanel from "@/components/ui/ChartPanel";
import CollapsibleSection from "../components/CollapsibleSection";
import { readEtlArtifacts } from "@/utils/etlArtifacts";
import { unescapeDdl } from "@/utils/ddl";
import "../etlDetail-global.css";
import "@/pages/CreateETL/css/inferenceReview.css";
import "./ResultView.css";

const VALIDATION_LABELS = { error: "Error", warning: "Advertencia", info: "Info" };

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

function ValidationItem({ v }) {
  return (
    <div className={`etl-validation etl-validation--${v.tipo}`}>
      <span className="etl-validation__badge">{VALIDATION_LABELS[v.tipo] ?? v.tipo}</span>
      <span className="etl-validation__campo">{v.campo}</span>
      <span className="etl-validation__msg">{v.mensaje}</span>
    </div>
  );
}

function DdlSection({ title, ddl, description }) {
  if (!ddl) return null;
  const text = unescapeDdl(ddl);
  return (
    <CollapsibleSection title={title}>
      <div className="infer-panel">
        <div className="infer-panel__header">
          <p className="etl-section__text" style={{ margin: 0 }}>{description}</p>
          <CopyButton text={text} />
        </div>
        <pre className="infer-panel__ddl">{text}</pre>
      </div>
    </CollapsibleSection>
  );
}

function ArtifactsSection({ art }) {
  if (art.status !== "ok") {
    return <p className="etl-section__text">{art.message}</p>;
  }
  return (
    <ul className="etl-artifacts-list">
      {art.etapas.map((etapa) => (
        <li key={etapa.nombre} className="etl-artifacts-etapa">
          <span className="etl-artifacts-etapa__nombre">{etapa.nombre}</span>
          {etapa.split ? (
            <ul className="etl-artifacts-sublist">
              <li>{etapa.kjb.filename}</li>
              {etapa.files.map((f) => (
                <li key={f.filename} className="etl-artifacts-file--indent">{f.filename}</li>
              ))}
            </ul>
          ) : (
            <ul className="etl-artifacts-sublist">
              {etapa.files.map((f) => <li key={f.filename}>{f.filename}</li>)}
            </ul>
          )}
        </li>
      ))}
      {art.master && (
        <li className="etl-artifacts-etapa">
          <span className="etl-artifacts-etapa__nombre">{art.master.filename}</span>
        </li>
      )}
    </ul>
  );
}

export default function ResultView({ result }) {
  const {
    proceso_etl,
    validaciones = [],
    documentacion = "",
    advertencias_buenas_practicas = [],
    stg_ddl = "",
    dwh_ddl = "",
  } = result ?? {};

  const art = readEtlArtifacts(result);

  return (
    <div className="etl-detail__body">

      {proceso_etl?.descripcion && (
        <CollapsibleSection title="Descripción">
          <p className="etl-section__text">{proceso_etl.descripcion}</p>
        </CollapsibleSection>
      )}

      <CollapsibleSection title="Archivos generados">
        <ArtifactsSection art={art} />
      </CollapsibleSection>

      {proceso_etl?.steps?.length > 0 && (
        <CollapsibleSection title="Estadísticas del proceso">
          <ChartPanel data={result} />
        </CollapsibleSection>
      )}

      {validaciones.length > 0 && (
        <CollapsibleSection title="Validaciones">
          <div className="etl-validations-list">
            {validaciones.map((v, i) => <ValidationItem key={i} v={v} />)}
          </div>
        </CollapsibleSection>
      )}

      <DdlSection
        title="DDL final del STG"
        ddl={stg_ddl}
        description="Este es el DDL contra el que se generó el proceso — creá las tablas en tu staging antes de correr el .ktr."
      />

      <DdlSection
        title="DDL final del DWH"
        ddl={dwh_ddl}
        description="Este es el DDL contra el que se generó el proceso — creá las tablas en tu DWH antes de correr el .ktr."
      />

      {documentacion && (
        <CollapsibleSection title="Documentación">
          <div className="etl-section__text etl-doc">
            {documentacion.split("\n\n").map((p, i) => <p key={i}>{p}</p>)}
          </div>
        </CollapsibleSection>
      )}

      {advertencias_buenas_practicas.length > 0 && (
        <CollapsibleSection title="Buenas prácticas">
          <ul className="etl-warnings-list">
            {advertencias_buenas_practicas.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </CollapsibleSection>
      )}

    </div>
  );
}
