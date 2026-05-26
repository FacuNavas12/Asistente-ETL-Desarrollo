import { useState } from "react";

function LogicItem({ label, value }) {
  if (!value) return null;
  return (
    <div className="job-logic-item">
      <strong>{label}</strong>
      {value}
    </div>
  );
}

function ExecutionOrder({ entries }) {
  return (
    <div className="job-review__section">
      <p className="job-review__section-title">Orden de ejecución inferido</p>
      <div className="job-order-list">
        {entries.map((entry) => (
          <div key={entry.order} className="job-order-item">
            <div className="job-order-item__num">{entry.order}</div>
            <div className="job-order-item__info">
              <span className="job-order-item__name">{entry.filename}</span>
              <span className="job-order-item__rationale">{entry.rationale}</span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ControlLogic({ plan }) {
  const variablesText = plan.variables?.length
    ? plan.variables.map((v) => `${v.name} = ${v.value}`).join(", ")
    : null;

  const checkpointsText = plan.checkpoints?.length
    ? plan.checkpoints.map((c) => `Log tras "${c.after_transformation}"`).join(", ")
    : null;

  const notifText = plan.notifications?.length
    ? plan.notifications.map((n) => `${n.trigger}: ${n.type}`).join("; ")
    : null;

  const loopsText = plan.loops?.length
    ? plan.loops.map((l) => `${l.transformation_name} (máx ${l.max_iterations} iter.)`).join("; ")
    : null;

  if (!variablesText && !checkpointsText && !plan.error_handling && !notifText) return null;

  return (
    <div className="job-review__section">
      <p className="job-review__section-title">Lógica de control</p>
      <div className="job-logic-grid">
        <LogicItem label="Variables" value={variablesText} />
        <LogicItem label="Checkpoints" value={checkpointsText} />
        <LogicItem label="Manejo de errores" value={plan.error_handling} />
        <LogicItem label="Notificaciones" value={notifText} />
        {loopsText && <LogicItem label="Loops" value={loopsText} />}
      </div>
    </div>
  );
}

export default function JobReview({
  analyzeResult,
  onConfirm,
  onRefine,
  isRefining,
  errors,
}) {
  const [correction, setCorrection] = useState("");
  const { job_plan: plan, iteration, warnings } = analyzeResult;

  const handleRefine = () => {
    if (!correction.trim() || isRefining) return;
    onRefine(correction.trim());
    setCorrection("");
  };

  return (
    <div className="job-body">
      {errors.length > 0 && (
        <div className="job-errors-box">
          <ul>
            {errors.map((e, i) => (
              <li key={i}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="job-review">
        <div className="job-review__header">
          <h2 className="job-review__name">{plan.job_name}</h2>
          {iteration > 1 && (
            <span className="job-review__iteration">
              Iteración {iteration}
            </span>
          )}
        </div>

        {warnings?.length > 0 && (
          <div className="job-review__warnings">
            <strong>Advertencias:</strong>
            <ul>
              {warnings.map((w, i) => (
                <li key={i}>{w}</li>
              ))}
            </ul>
          </div>
        )}

        <ExecutionOrder entries={plan.execution_order} />

        <ControlLogic plan={plan} />

        {plan.overall_rationale && (
          <div className="job-review__section">
            <p className="job-review__section-title">Justificación general</p>
            <p className="job-review__rationale">{plan.overall_rationale}</p>
          </div>
        )}

        <div className="job-review__section">
          <div className="job-review__correction">
            <span className="job-review__correction-label">
              ¿Querés ajustar algo?
            </span>
            <textarea
              className="job-textarea"
              value={correction}
              onChange={(e) => setCorrection(e.target.value)}
              placeholder='Ej: "Agregá un log de error entre la primera y segunda transformación"'
              disabled={isRefining}
              style={{ minHeight: "72px" }}
            />
            <div className="job-review__actions">
              <button
                className="job-btn--secondary"
                onClick={handleRefine}
                disabled={!correction.trim() || isRefining}
              >
                {isRefining ? "Aplicando..." : "Aplicar corrección"}
              </button>
              <button
                className="job-btn--primary"
                onClick={onConfirm}
                disabled={isRefining}
              >
                Confirmar y generar .kjb
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
