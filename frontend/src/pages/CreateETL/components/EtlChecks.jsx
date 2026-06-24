import "../css/etlProcessing.css";

export default function EtlChecks({ phase = "waiting", ktrLogs = [] }) {
  return (
    <div className="checks-container">
      {phase === "waiting" ? (
        <div className="checks-waiting">
          <span className="checks-spinner" />
          <span className="checks-waiting-label">Esperando respuesta</span>
        </div>
      ) : (
        <>
          <div className="checks-building-header">
            <span className="checks-spinner checks-spinner--sm" />
            <span className="checks-building-label">Creando KTR</span>
          </div>
          <div className="checks-logs">
            {ktrLogs.map((entry) => (
              <div
                key={entry.id}
                className={`checks-log-item${entry.fading ? " checks-log-fade" : ""}`}
              >
                {entry.message}
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
