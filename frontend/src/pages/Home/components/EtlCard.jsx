import { ETL_STATUS } from "@/constants/status";
import EtlCardMenu from "./EtlCardMenu";

const ETL_ICONS = ["⚡", "🔄", "📊", "🔗", "🗃️", "⚙️", "🧩", "📦"];

export default function EtlCard({ etl, index, onClick, onDelete, onDeletePermanent }) {
  const status       = ETL_STATUS[etl.status] ?? ETL_STATUS.done;
  const isIncomplete = etl.status === "pending" || etl.status === "en_proceso";
  const action       = isIncomplete ? "Continuar →" : "Ver detalle →";

  return (
    <div
      className="etl-card"
      style={{ animationDelay: `${index * 60}ms` }}
      onClick={onClick}
    >
      <div className="etl-card__top-actions">
        <EtlCardMenu etl={etl} onDeletePermanent={onDeletePermanent} />
        <button
          className="etl-card__delete"
          onClick={(e) => { e.stopPropagation(); onDelete(); }}
          title="Quitar de esta vista"
        >
          ×
        </button>
      </div>

      <div className="etl-card__icon">{ETL_ICONS[index % ETL_ICONS.length]}</div>
      <span className="etl-card__type-tag etl-card__type-tag--etl">Transformación</span>
      <span className="etl-card__name">{etl.name}</span>
      <span className="etl-card__date">
        {new Date(etl.createdAt).toLocaleDateString("es-AR", { dateStyle: "medium" })}
      </span>
      <span className="etl-card__status" style={{ "--status-color": status.color }}>
        {status.label}
      </span>
      <div className="etl-card__footer">
        <span className="etl-card__action">{action}</span>
      </div>
    </div>
  );
}
