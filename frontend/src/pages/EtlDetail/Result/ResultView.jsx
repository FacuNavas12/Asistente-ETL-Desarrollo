import ChartPanel from "@/components/ui/ChartPanel";
import CollapsibleSection from "../components/CollapsibleSection";
import "../etlDetail-global.css";
import "./ResultView.css";

const VALIDATION_LABELS = { error: "Error", warning: "Advertencia", info: "Info" };

function ValidationItem({ v }) {
  return (
    <div className={`etl-validation etl-validation--${v.tipo}`}>
      <span className="etl-validation__badge">{VALIDATION_LABELS[v.tipo] ?? v.tipo}</span>
      <span className="etl-validation__campo">{v.campo}</span>
      <span className="etl-validation__msg">{v.mensaje}</span>
    </div>
  );
}

export default function ResultView({ result }) {
  const {
    proceso_etl,
    validaciones = [],
    documentacion = "",
    advertencias_buenas_practicas = [],
  } = result ?? {};

  return (
    <div className="etl-detail__body">

      {proceso_etl?.descripcion && (
        <CollapsibleSection title="Descripción">
          <p className="etl-section__text">{proceso_etl.descripcion}</p>
        </CollapsibleSection>
      )}

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
