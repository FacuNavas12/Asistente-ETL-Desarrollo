import "./etlProcessing.css";

export default function EtlChecks({ done }) {
  const checks = [
    "Validando campos...",
    "Aplicando reglas de limpieza...",
    "Generando modelo Staging..."
  ];

  return (
    <div className="checks-container">
      {checks.map((c, i) => (
        <div
          key={i}
          className={`check-item ${done ? "check-done" : ""}`}
        >
          <span className="check-icon">
            {done ? "âœ”ï¸" : "â³"}
          </span>
          {c}
        </div>
      ))}
    </div>
  );
}

