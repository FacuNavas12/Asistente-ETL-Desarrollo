import { useState } from "react";
import ConnectionForm from "../Input/ConnectionForm";
import "./destinationConnections.css";

// Se completa en paralelo con la llamada al modelo (ver CreateETL.jsx
// handleConfirm). onConnectionReady(nombre_lógico, connId) se llama cada vez
// que una conexión termina de crearse y testearse — el padre acumula el mapa
// completo y lo reenvía entero a POST /{job_id}/connections en cada cambio,
// porque ese endpoint reemplaza el mapa completo (no hace merge).
export default function DestinationConnections({ onConnectionReady }) {
  const [stagingConnId, setStagingConnId] = useState(null);
  const [dwhConnId, setDwhConnId]         = useState(null);
  const [sameForBoth, setSameForBoth]     = useState(false);

  const handleStaging = (connId) => {
    setStagingConnId(connId);
    onConnectionReady("conn_staging", connId);
    if (sameForBoth) {
      setDwhConnId(connId);
      onConnectionReady("conn_dwh", connId);
    }
  };

  const handleDwh = (connId) => {
    setDwhConnId(connId);
    onConnectionReady("conn_dwh", connId);
  };

  const handleSameForBothChange = (checked) => {
    setSameForBoth(checked);
    if (checked && stagingConnId) {
      setDwhConnId(stagingConnId);
      onConnectionReady("conn_dwh", stagingConnId);
    } else if (!checked) {
      setDwhConnId(null);
      onConnectionReady("conn_dwh", null);
    }
  };

  return (
    <div className="dest-connections">
      <section className="dest-connections__section">
        <h3>Conexión de Staging</h3>
        {stagingConnId ? (
          <p className="dest-connections__done">✓ Conexión configurada</p>
        ) : (
          <ConnectionForm onConnected={handleStaging} submitLabel="Conectado" />
        )}
      </section>

      <label className="dest-connections__same">
        <input
          type="checkbox"
          checked={sameForBoth}
          onChange={e => handleSameForBothChange(e.target.checked)}
        />
        Usar la misma conexión para el DWH
      </label>

      {!sameForBoth && (
        <section className="dest-connections__section">
          <h3>Conexión de DWH</h3>
          {dwhConnId ? (
            <p className="dest-connections__done">✓ Conexión configurada</p>
          ) : (
            <ConnectionForm onConnected={handleDwh} submitLabel="Conectado" />
          )}
        </section>
      )}
    </div>
  );
}
