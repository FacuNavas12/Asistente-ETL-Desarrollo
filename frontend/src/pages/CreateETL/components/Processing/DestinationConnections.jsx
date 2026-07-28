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
// build (ver gate en _try_build). Cada capa (origen/staging/DWH) es
// independiente: "Completar en Spoon" la deja como placeholder (host/port/
// base/usuario como variable ${VAR} en el .ktr, ya no aborta el build — D15,
// docs/refactor/02-decisiones.md) — nunca se pide password acá, esta app no
// conecta de verdad contra staging/DWH ni contra un origen sin fila
// Connection guardada.
//
// origenConnectionId: id ya derivado de una Connection guardada (ver
// _deriveOrigenConnectionId en CreateETL.jsx) — si viene, el origen no se
// vuelve a preguntar acá (se resuelve con ese id, no se manda conn_origen en
// destMap para no pisarlo). Si es null (origen por CSV/Excel/DDL/formulario,
// o varias tablas con conexiones distintas), se pregunta con el mismo patrón
// checkbox + formulario que staging/DWH.
// origenConnectionStale: true cuando CreateETL.jsx derivó un id único de
// Connection para el origen pero ya no resuelve contra el backend (fila
// borrada, de otro owner) — ver _resolveOrigenConnection en CreateETL.jsx.
// Distingue "nunca hubo conexión guardada" (CSV/DDL/formulario, mensaje
// genérico) de "había una y dejó de existir" (aviso puntual).
export default function DestinationConnections({ onFinalize, origenConnectionId = null, origenConnectionStale = false }) {
  const [origenValue,  setOrigenValue]  = useState(EMPTY_DESTINATION_CONNECTION);
  const [origenSkip,   setOrigenSkip]   = useState(false);
  const [stagingValue, setStagingValue] = useState(EMPTY_DESTINATION_CONNECTION);
  const [dwhValue,     setDwhValue]     = useState(EMPTY_DESTINATION_CONNECTION);
  const [stagingSkip,  setStagingSkip]  = useState(false);
  const [dwhSkip,       setDwhSkip]      = useState(false);
  const [sameForBoth,  setSameForBoth]  = useState(false);
  const [submitted,    setSubmitted]    = useState(false);

  const needsOrigenForm = !origenConnectionId;
  const origenReady = !needsOrigenForm || origenSkip || isDestinationConnectionComplete(origenValue);
  const stagingReady = stagingSkip || isDestinationConnectionComplete(stagingValue);
  const dwhReady = sameForBoth || dwhSkip || isDestinationConnectionComplete(dwhValue);
  const canSubmit = origenReady && stagingReady && dwhReady && !submitted;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onFinalize({
      // Si origenConnectionId ya existe, NO se manda la clave (ni siquiera en
      // undefined): connectionsMapRef ya lo tiene y un merge con la clave
      // presente-pero-undefined lo pisaría y lo perdería al serializar.
      ...(needsOrigenForm ? { conn_origen: origenSkip ? undefined : _toPayload(origenValue) } : {}),
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
        <h3>Conexión de Origen</h3>
        {needsOrigenForm ? (
          <>
            {origenConnectionStale && (
              <p className="dest-connections__warning">
                ⚠ La conexión guardada del origen ya no existe — completá los datos a mano.
              </p>
            )}
            <label className="dest-connections__same">
              <input
                type="checkbox"
                checked={origenSkip}
                onChange={e => setOrigenSkip(e.target.checked)}
              />
              Completar en Spoon (dejar host/usuario/base sin completar acá)
            </label>
            {!origenSkip && (
              <DestinationConnectionForm value={origenValue} onChange={setOrigenValue} />
            )}
          </>
        ) : (
          <p className="dest-connections__readonly">
            Conexión configurada (id {origenConnectionId}) — resuelta desde las tablas de origen.
          </p>
        )}
      </section>

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
