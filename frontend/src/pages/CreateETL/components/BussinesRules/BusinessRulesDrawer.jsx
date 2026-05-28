import { useState } from "react";
import "../etlForm.css";
import "./BusinessRulesDrawer.css";

export default function BusinessRulesDrawer({ value, onChange }) {
  const [open, setOpen] = useState(false);

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
      <div className="br-drawer__body">
        <textarea
          className="origen-textarea br-drawer__textarea"
          placeholder="Describa las reglas de negocio a considerar: validaciones, criterios de transformación, condiciones especiales, etc."
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </div>
  );
}
