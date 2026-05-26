export default function PendingModal({ type, pendingItem, onGoTo, onCreateNew, onClose }) {
  const label = type === "job" ? "Job" : "ETL";
  return (
    <div className="sidebar-modal-overlay" onClick={onClose}>
      <div className="sidebar-modal" onClick={e => e.stopPropagation()}>
        <h2 className="sidebar-modal__title">Ya hay un {label} en proceso</h2>
        <p className="sidebar-modal__sub">
          "{pendingItem.name}" aún no fue completado.
        </p>
        <div className="sidebar-modal__options">
          <button className="sidebar-modal__opt sidebar-modal__opt--primary" onClick={onGoTo}>
            Ver {label} pendiente
          </button>
          <button className="sidebar-modal__opt" onClick={onCreateNew}>
            Crear uno nuevo de todas formas
          </button>
          <button className="sidebar-modal__opt sidebar-modal__opt--muted" onClick={onClose}>
            Ignorar, quedarme aquí
          </button>
        </div>
      </div>
    </div>
  );
}
