import "./confirmModal.css";

export default function ConfirmModal({
  title,
  message,
  confirmLabel = "Confirmar",
  cancelLabel = "Cancelar",
  onConfirm,
  onCancel,
  // Override de color por botón (ej. "home-modal__save" para un Guardar
  // azul) — se suma a la clase base, que ya trae el estilo por defecto.
  confirmClassName = "",
  cancelClassName = "",
}) {
  return (
    <div className="home-modal-overlay">
      <div className="home-modal">
        <h3 className="home-modal__title">{title}</h3>
        <p className="home-modal__text">{message}</p>
        <div className="home-modal__actions">
          <button className={`home-modal__leave ${confirmClassName}`} onClick={onConfirm}>
            {confirmLabel}
          </button>
          <button className={`home-modal__confirm ${cancelClassName}`} onClick={onCancel}>
            {cancelLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
