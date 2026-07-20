import CollapsibleSection from "../components/CollapsibleSection";
import "../etlDetail-global.css";
import "./ConnectionView.css";

// Nombres lógicos que usa el backend (ver ktr_builder/connection.py) para
// resolver las conexiones reales al momento de generar el .ktr.
const ROLE_LABELS = {
  conn_origen: "Origen",
  conn_dwh: "Destino (DWH)",
};

// Esta app no persiste passwords de conexión (ver decisión de diseño) —
// el aviso de abajo es permanente, no un placeholder a completar después.
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
        <p className="etl-section__text">
          Esta app no guarda contraseñas de conexión — el .ktr descargado
          trae host/usuario/base de datos reales, pero el password hay que
          completarlo a mano en kettle.properties o en el conector de Spoon
          antes de ejecutarlo.
        </p>
        <p className="etl-section__text">
          Para exportar a Superset con datos reales, primero configurá la
          conexión al Data Warehouse a mano en Superset (Configuración →
          Conexiones a bases de datos) usando los datos de la conexión de
          arriba — esta app tampoco la configura automáticamente ahí.
        </p>
      </CollapsibleSection>
    </div>
  );
}
