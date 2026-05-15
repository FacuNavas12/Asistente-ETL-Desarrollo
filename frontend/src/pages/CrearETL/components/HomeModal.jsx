import "./homeModal.css";

export default function HomeModal({ onConfirm, onCancel }) {
  return (
    <div className="home-modal-overlay" onClick={onCancel}>
      <div className="home-modal" onClick={e => e.stopPropagation()}>
        <h3 className="home-modal__title">¿Salir del formulario?</h3>
        <p className="home-modal__text">
          Tu progreso se guarda automáticamente por <strong>2 horas</strong>.
          Podrás retomar el ETL desde la pantalla de inicio.
        </p>
        <div className="home-modal__actions">
          <button className="home-modal__cancel" onClick={onCancel}>
            Quedarme
          </button>
          <button className="home-modal__confirm" onClick={onConfirm}>
            Ir al inicio
          </button>
        </div>
      </div>
    </div>
  );
}


