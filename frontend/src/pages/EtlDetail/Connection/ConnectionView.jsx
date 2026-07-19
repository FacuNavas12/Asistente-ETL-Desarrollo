import CollapsibleSection from "../components/CollapsibleSection";
import "../etlDetail-global.css";
import "./ConnectionView.css";

// Nombres lógicos que usa el backend (ver ktr_builder/connection.py) para
// resolver las conexiones reales al momento de generar el .ktr.
const ROLE_LABELS = {
  conn_origen: "Origen",
  conn_dwh: "Destino (DWH)",
};

// Placeholder informativo — diseño final a definir.
export default function ConnectionView({ formData }) {
  const entries = Object.entries(formData?.connectionsMap ?? {})
    .filter(([, connId]) => Boolean(connId));

  return (
    <div className="etl-detail__body">
      <CollapsibleSection title="Conexiones utilizadas">
        {entries.length > 0 ? (
          <ul className="etl-connections-list">
            {entries.map(([logicalName, connId]) => (
              <li key={logicalName} className="etl-connection-item">
                <span className="etl-connection-item__role">
                  {ROLE_LABELS[logicalName] ?? logicalName}
                </span>
                <span className="etl-connection-item__id">{connId}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="etl-section__text">
            Este ETL no tiene conexiones a bases de datos asociadas.
          </p>
        )}
      </CollapsibleSection>
    </div>
  );
}
