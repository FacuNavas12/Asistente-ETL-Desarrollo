import { useState } from "react";
import "./CollapsibleSection.css";

function ToggleArrow({ open, onClick }) {
  return (
    <button
      type="button"
      className="etl-section__toggle"
      onClick={onClick}
      aria-expanded={open}
      aria-label={open ? "Contraer sección" : "Expandir sección"}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="12" height="12">
        <path d={open ? "M18 15l-6-6-6 6" : "M6 9l6 6 6-6"} />
      </svg>
    </button>
  );
}

// Card genérica de sección con header colapsable — usada por Resultado y Conexión.
// La flecha se repite al pie cuando está abierta, para secciones largas donde
// el header ya no es visible sin scrollear hacia arriba.
export default function CollapsibleSection({ title, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen);
  const toggle = () => setOpen(o => !o);

  return (
    <div className={`etl-section${open ? "" : " etl-section--collapsed"}`}>
      <div className="etl-section__header">
        <h2 className="etl-section__title">{title}</h2>
        <ToggleArrow open={open} onClick={toggle} />
      </div>
      {open && (
        <>
          <div className="etl-section__body">{children}</div>
          <div className="etl-section__footer">
            <ToggleArrow open={open} onClick={toggle} />
          </div>
        </>
      )}
    </div>
  );
}
