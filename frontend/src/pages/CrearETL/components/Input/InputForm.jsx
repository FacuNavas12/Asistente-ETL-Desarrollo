import { useState, useRef, useEffect } from "react";
import "../etlForm.css";
import OrigenInputFormulario from "./InputFormulario";
import OrigenInputCSV        from "./InputCSV";
import OrigenInputExcel      from "./InputExcel";
import InputConection        from "./InputConection";

const MODOS = [
  { id: "formulario",  label: "Formulario" },
  { id: "csv",         label: "CSV"        },
  { id: "excel",       label: "Excel"      },
  { id: "connections", label: "Conexiones" },
];

function TableDataPreview({ table }) {
  const [open, setOpen] = useState(false);
  const cols    = table.columns ?? [];
  const maxRows = cols.length > 0 ? Math.max(...cols.map(c => c.data?.length ?? 0)) : 0;
  if (maxRows === 0) return null;

  return (
    <div className="origen-preview">
      <div className="origen-preview__header">
        <span className="origen-preview__name">{table.tableName}</span>
        <span className="origen-preview__meta">{cols.length} col · {maxRows} fil</span>
        <button className="origen-preview__toggle" onClick={() => setOpen(o => !o)}>
          {open ? "Ocultar tabla" : "Ver como tabla"}
        </button>
      </div>
      {open && (
        <div className="origen-preview__wrap">
          <table className="origen-preview__table">
            <thead>
              <tr>
                <th className="origen-preview__rn">#</th>
                {cols.map((c, i) => <th key={i}>{c.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: maxRows }, (_, rowIdx) => (
                <tr key={rowIdx}>
                  <td className="origen-preview__rn">{rowIdx + 1}</td>
                  {cols.map((c, ci) => (
                    <td key={ci}>
                      {c.data?.[rowIdx] !== undefined
                        ? c.data[rowIdx]
                        : <span className="origen-preview__empty">-</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

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
          <p className="origen-previews__label">Vista previa de datos cargados</p>
          {value.map((t, i) => <TableDataPreview key={i} table={t} />)}
        </div>
      )}
    </div>
  );
}


