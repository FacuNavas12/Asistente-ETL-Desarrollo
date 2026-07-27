import "../css/etlProcessing.css";

// D29 (docs/refactor/02-decisiones.md): los logs se muestran en las DOS
// fases, no solo en "building" — antes "waiting" escondía la lista entera,
// que es justo la fase donde ahora hay hitos reales que contar (auditoría de
// DDL, llamada al modelo, reintentos). El header cambia de texto según la
// fase, pero la lista de abajo es la misma.
export default function EtlChecks({ phase = "waiting", ktrLogs = [] }) {
  return (
    <div className="checks-container">
      <div className={phase === "waiting" ? "checks-waiting" : "checks-building-header"}>
        <span className={`checks-spinner${phase === "waiting" ? "" : " checks-spinner--sm"}`} />
        <span className={phase === "waiting" ? "checks-waiting-label" : "checks-building-label"}>
          {phase === "waiting" ? "Esperando al modelo" : "Creando KTR"}
        </span>
      </div>
      <div className="checks-logs">
        {ktrLogs.map((entry) => (
          <div
            key={entry.id}
            className={`checks-log-item checks-log-item--${entry.level ?? "info"}${entry.fading ? " checks-log-fade" : ""}`}
          >
            {entry.message}
          </div>
        ))}
      </div>
    </div>
  );
}
