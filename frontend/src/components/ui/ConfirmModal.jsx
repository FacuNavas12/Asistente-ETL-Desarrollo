import "./confirmModal.css";

export default function ConfirmModal({
  title,
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  onConfirm,
  onCancel,
}) {
  return (
    <div className="home-modal-overlay">
      <div className="home-modal">
        <h3 className="home-modal__title">{title}</h3>
        <p className="home-modal__text">{message}</p>
        <div className="home-modal__actions">
          <button className="home-modal__leave" onClick={onConfirm}>
            {confirmLabel}
          </button>
          <button className="home-modal__confirm" onClick={onCancel}>
            {cancelLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
