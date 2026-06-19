import "../css/homeModal.css";

export default function UnsavedChangesModal({ onDiscard, onCancel }) {
  return (
    <div className="home-modal-overlay">
      <div className="home-modal">
        <h3 className="home-modal__title">Tenés cambios sin guardar</h3>
        <p className="home-modal__text">
          Si salís ahora, se descartarán todos los cambios no guardados.
        </p>
        <div className="home-modal__actions">
          <button className="home-modal__leave" onClick={onDiscard}>
            Descartar y salir
          </button>
          <button className="home-modal__confirm" onClick={onCancel}>
            Cancelar
          </button>
        </div>
      </div>
    </div>
  );
}
