import { useState } from "react";
import DestinationConnectionForm, {
  EMPTY_DESTINATION_CONNECTION,
  isDestinationConnectionComplete,
} from "../Input/DestinationConnectionForm";
import "./destinationConnections.css";

const _toPayload = (value) => ({ ...value, port: Number(value.port) });

// Se completa en paralelo con la llamada al modelo (ver CreateETL.jsx
// handleConfirm) pero NO manda nada al backend hasta que el usuario confirma
// con "Generar" — ni el modelo ni esta pantalla individualmente disparan el
// build (ver gate en _try_build). Cada capa (staging/DWH) es independiente:
// "Completar en Spoon" la deja como placeholder (host/port/base/usuario
// como variable ${VAR} en el .ktr, igual que hoy para una conexión sin
// resolver) — nunca se pide password acá, esta app no conecta de verdad
// contra staging/DWH.
export default function DestinationConnections({ onFinalize }) {
  const [stagingValue, setStagingValue] = useState(EMPTY_DESTINATION_CONNECTION);
  const [dwhValue,     setDwhValue]     = useState(EMPTY_DESTINATION_CONNECTION);
  const [stagingSkip,  setStagingSkip]  = useState(false);
  const [dwhSkip,       setDwhSkip]      = useState(false);
  const [sameForBoth,  setSameForBoth]  = useState(false);
  const [submitted,    setSubmitted]    = useState(false);

  const stagingReady = stagingSkip || isDestinationConnectionComplete(stagingValue);
  const dwhReady = sameForBoth || dwhSkip || isDestinationConnectionComplete(dwhValue);
  const canSubmit = stagingReady && dwhReady && !submitted;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onFinalize({
      conn_staging: stagingSkip ? undefined : _toPayload(stagingValue),
      conn_dwh: sameForBoth
        ? (stagingSkip ? undefined : _toPayload(stagingValue))
        : (dwhSkip ? undefined : _toPayload(dwhValue)),
    });
    setSubmitted(true);
  };

  if (submitted) {
    return (
      <div className="dest-connections">
        <p className="dest-connections__done">✓ Conexiones destino confirmadas — generando .ktr...</p>
      </div>
    );
  }

  return (
    <div className="dest-connections">
      <section className="dest-connections__section">
        <h3>Conexión de Staging</h3>
        <label className="dest-connections__same">
          <input
            type="checkbox"
            checked={stagingSkip}
            onChange={e => setStagingSkip(e.target.checked)}
          />
          Completar en Spoon (dejar host/usuario/base sin completar acá)
        </label>
        {!stagingSkip && (
          <DestinationConnectionForm value={stagingValue} onChange={setStagingValue} />
        )}
      </section>

      <label className="dest-connections__same">
        <input
          type="checkbox"
          checked={sameForBoth}
          onChange={e => setSameForBoth(e.target.checked)}
        />
        Usar la misma conexión para el DWH
      </label>

      {!sameForBoth && (
        <section className="dest-connections__section">
          <h3>Conexión de DWH</h3>
          <label className="dest-connections__same">
            <input
              type="checkbox"
              checked={dwhSkip}
              onChange={e => setDwhSkip(e.target.checked)}
            />
            Completar en Spoon (dejar host/usuario/base sin completar acá)
          </label>
          {!dwhSkip && (
            <DestinationConnectionForm value={dwhValue} onChange={setDwhValue} />
          )}
        </section>
      )}

      <button className="staging-add-btn" onClick={handleSubmit} disabled={!canSubmit}>
        Generar
      </button>
    </div>
  );
}
