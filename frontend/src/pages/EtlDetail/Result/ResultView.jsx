import ChartPanel from "@/components/ui/ChartPanel";
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
        <div className="etl-section">
          <h2 className="etl-section__title">Descripción</h2>
          <p className="etl-section__text">{proceso_etl.descripcion}</p>
        </div>
      )}

      {proceso_etl?.steps?.length > 0 && (
        <div className="etl-section">
          <h2 className="etl-section__title">Estadísticas del proceso</h2>
          <ChartPanel data={result} />
        </div>
      )}

      {validaciones.length > 0 && (
        <div className="etl-section">
          <h2 className="etl-section__title">Validaciones</h2>
          <div className="etl-validations-list">
            {validaciones.map((v, i) => <ValidationItem key={i} v={v} />)}
          </div>
        </div>
      )}

      {documentacion && (
        <div className="etl-section">
          <h2 className="etl-section__title">Documentación</h2>
          <div className="etl-section__text etl-doc">
            {documentacion.split("\n\n").map((p, i) => <p key={i}>{p}</p>)}
          </div>
        </div>
      )}

      {advertencias_buenas_practicas.length > 0 && (
        <div className="etl-section">
          <h2 className="etl-section__title">Buenas prácticas</h2>
          <ul className="etl-warnings-list">
            {advertencias_buenas_practicas.map((w, i) => <li key={i}>{w}</li>)}
          </ul>
        </div>
      )}

    </div>
  );
}
