import { useState, useEffect } from "react";
import "../../css/shared.css";
import "../../css/businessRulesDrawer.css";
import BusinessRulesEditor from "./BusinessRulesEditor";

const SHORTCUTS = [
  { write: "# ",        result: "Encabezado H1" },
  { write: "## ",       result: "Encabezado H2" },
  { write: "- ",        result: "Lista con viñetas" },
  { write: "1. ",       result: "Lista numerada" },
  { write: "**texto**", result: "Negrita" },
  { write: "> ",        result: "Cita / Blockquote" },
];

export default function BusinessRulesDrawer({ value, onChange }) {
  const [open,     setOpen]     = useState(false);
  const [pinned,   setPinned]   = useState(false);
  const [hovering, setHovering] = useState(false);

  useEffect(() => {
    if (!open) setPinned(false);
  }, [open]);

  const showTooltip = hovering || pinned;

  return (
    <div className={`br-drawer ${open ? "br-drawer--open" : ""}`}>
      <button
        className="br-drawer__handle"
        onClick={() => setOpen(o => !o)}
        aria-expanded={open}
      >
        <span className="br-drawer__label">Reglas de Negocio</span>
        <span className={`br-drawer__arrow ${open ? "br-drawer__arrow--open" : ""}`}>↑</span>
      </button>

      {open && (
        <div className="br-hint">
          <button
            className={`br-hint__btn${pinned ? " br-hint__btn--pinned" : ""}`}
            onMouseEnter={() => setHovering(true)}
            onMouseLeave={() => setHovering(false)}
            onClick={() => setPinned(p => !p)}
            aria-label="Atajos de formato"
          >
            (?)
          </button>
          {showTooltip && (
            <div className="br-hint__panel">
              <table className="br-hint__table">
                <thead>
                  <tr><th>Escribe</th><th>Resultado</th></tr>
                </thead>
                <tbody>
                  {SHORTCUTS.map(({ write, result }) => (
                    <tr key={write}>
                      <td><code>{write}</code></td>
                      <td>{result}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      <div className="br-drawer__body">
        <BusinessRulesEditor value={value} onChange={onChange} />
      </div>
    </div>
  );
}
