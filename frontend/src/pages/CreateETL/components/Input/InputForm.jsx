import { useState, useRef, useEffect } from "react";
import "../etlForm.css";
import OrigenInputFormulario from "./InputFormulario";
import OrigenInputCSV        from "./InputCSV";
import OrigenInputExcel      from "./InputExcel";
import InputConection        from "./InputConection";
import TablesPopupButton     from "../Tables/TablesPopupButton";
import TableDataPreview      from "../Tables/TableDataPreview";

const MODOS = [
  { id: "formulario",  label: "Formulario" },
  { id: "csv",         label: "CSV"        },
  { id: "excel",       label: "Excel"      },
  { id: "connections", label: "Conexiones" },
];

export default function OrigenInput({ value, onChange }) {
  const [modo, setModo]   = useState("formulario");
  const [open, setOpen]   = useState(false);
  const menuRef           = useRef();

  useEffect(() => {
    const handler = (e) => {
      if (menuRef.current && !menuRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const modoActual = MODOS.find((m) => m.id === modo);

  const switchMode = (id) => {
    setModo(id);
    setOpen(false);
  };

  return (
    <div className="form-section">
      <div className="origen-header">
        <h2 className="form-section__title">Datos de origen</h2>

        <div className="origen-modo-dropdown" ref={menuRef}>
          <button
            className="origen-modo-btn"
            onClick={() => setOpen((o) => !o)}
            aria-haspopup="listbox"
            aria-expanded={open}
          >
            {modoActual.label}
            <span className="origen-modo-arrow">{open ? "▲" : "▼"}</span>
          </button>

          {open && (
            <ul className="origen-modo-menu" role="listbox">
              {MODOS.map((m) => (
                <li
                  key={m.id}
                  role="option"
                  aria-selected={modo === m.id}
                  className={`origen-modo-option${modo === m.id ? " origen-modo-option--active" : ""}`}
                  onClick={() => switchMode(m.id)}
                >
                  {m.label}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {modo === "formulario" && (
        <OrigenInputFormulario value={value} onChange={onChange} />
      )}
      {modo === "csv" && (
        <OrigenInputCSV value={value} onChange={onChange} onSwitchMode={switchMode} />
      )}
      {modo === "excel" && (
        <OrigenInputExcel value={value} onChange={onChange} onSwitchMode={switchMode} />
      )}
      {modo === "connections" && (
        <InputConection value={value} onChange={onChange} />
      )}

      {Array.isArray(value) && value.length > 0 && (
        <div className="origen-previews">
          <div className="origen-previews__header">
            <p className="origen-previews__label">Vista previa de datos cargados</p>
            <TablesPopupButton tables={value} />
          </div>
          {value.map((t, i) => <TableDataPreview key={i} table={t} />)}
        </div>
      )}
    </div>
  );
}
