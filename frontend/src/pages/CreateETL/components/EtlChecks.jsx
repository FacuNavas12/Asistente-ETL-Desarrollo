import "./etlProcessing.css";

const DEFAULT_CHECKS = [
  "Validando campos...",
  "Aplicando reglas de limpieza...",
  "Generando modelo Staging...",
];

export default function EtlChecks({ done, message, checks = DEFAULT_CHECKS }) {
  return (
    <div className="checks-container">
      {message && <p className="checks-message">{message}</p>}
      {checks.map((c, i) => (
        <div key={i} className={`check-item ${done ? "check-done" : ""}`}>
          <span className="check-icon">{done ? "✔️" : "⏳"}</span>
          {c}
        </div>
      ))}
    </div>
  );
}
