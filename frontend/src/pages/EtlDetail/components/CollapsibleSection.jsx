import { useRef, useState } from "react";
import "./CollapsibleSection.css";

function ToggleArrow({ open, onClick, label }) {
  return (
    <button
      type="button"
      className="etl-section__toggle"
      onClick={onClick}
      aria-expanded={open}
      aria-label={label}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" width="12" height="12">
        <path d={open ? "M18 15l-6-6-6 6" : "M6 9l6 6 6-6"} />
      </svg>
    </button>
  );
}

// Card genérica de sección con header colapsable — usada por Resultado y Conexión.
// La flecha se repite al pie cuando está abierta, para secciones largas donde
// el header ya no es visible sin scrollear hacia arriba. La de arriba cierra
// la sección; la de abajo lleva de vuelta al título (no cierra) — así una
// sección larga se puede "cerrar visualmente" sin perder el contenido.
export default function CollapsibleSection({ title, defaultOpen = true, children }) {
  const [open, setOpen] = useState(defaultOpen);
  const headerRef = useRef(null);
  const toggle = () => setOpen(o => !o);
  const scrollToHeader = () => {
    headerRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  return (
    <div className={`etl-section${open ? "" : " etl-section--collapsed"}`}>
      <div className="etl-section__header" ref={headerRef}>
        <h2 className="etl-section__title">{title}</h2>
        <ToggleArrow open={open} onClick={toggle} label={open ? "Contraer sección" : "Expandir sección"} />
      </div>
      {open && (
        <>
          <div className="etl-section__body">{children}</div>
          <div className="etl-section__footer">
            <ToggleArrow open={open} onClick={scrollToHeader} label="Ir al título de la sección" />
          </div>
        </>
      )}
    </div>
  );
}
