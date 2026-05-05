import { useState } from "react";
import "../../css/etlForm.css";
import { useTableEditor } from "./tableUtils";

const TIPOS    = ["string", "int", "float", "bool", "date"];
const FORMATOS = ["", "dd/MM/yyyy", "ISO8601", "decimal(10,2)"];
const ROLES    = ["PK", "FK", "clave natural", "atributo"];

const EMPTY_TABLE = { tableName: "", columns: [] };
const EMPTY_COL   = { name: "", dataType: "string", dataFormat: "", role: "atributo", data: [] };

function CollapseRow({ col, onRemove }) {
  const [open, setOpen] = useState(false);
  const hasData = col.data.length > 0;

  return (
    <div className="origen-col-collapse">
      <div className="origen-col-collapse__header">
        {hasData
          ? <button className="origen-col-toggle" onClick={() => setOpen(o => !o)}>{open ? "▲" : "▼"}</button>
          : <span className="origen-col-toggle--placeholder" />
        }
        <span className="origen-col-name">{col.name}</span>
        <span className="origen-col-meta">
          {col.dataType}{col.dataFormat ? ` · ${col.dataFormat}` : ""} · {col.role}
        </span>
        {hasData && (
          <span className="origen-col-count">{col.data.length} dato{col.data.length !== 1 ? "s" : ""}</span>
        )}
        {onRemove && <button className="staging-remove-btn" onClick={onRemove}>✕</button>}
      </div>

      {open && hasData && (
        <div className="origen-col-collapse__body">
          {col.data.map((d, i) => <span key={i} className="origen-dato-tag">{d}</span>)}
        </div>
      )}
    </div>
  );
}

export default function OrigenInput({ value, onChange }) {
  const tables = Array.isArray(value) ? value : [];
  const [currentDato, setCurrentDato] = useState("");

  const ed = useTableEditor({
    emptyTable: EMPTY_TABLE,
    emptyCol:   EMPTY_COL,
    tables,
    setTables:  onChange,
    columnsKey: "columns",
  });

  const handleAddDato = () => {
    if (!currentDato.trim()) return;
    ed.setCurrentCol(c => ({ ...c, data: [...c.data, currentDato.trim()] }));
    setCurrentDato("");
  };

  const handleRemoveDato = (i) =>
    ed.setCurrentCol(c => ({ ...c, data: c.data.filter((_, idx) => idx !== i) }));

  const handleAddColumn = () => {
    if (!ed.currentCol.name.trim()) return;
    ed.addColumn(ed.currentCol);
    setCurrentDato("");
  };

  const handleEditTable = (i) => {
    ed.editTable(i);
    setCurrentDato("");
  };

  const handleSaveTable = () => {
    if (!ed.currentTable.tableName.trim() || ed.currentTable.columns.length === 0) return;
    ed.saveTable();
    setCurrentDato("");
  };

  const canAddTable = ed.currentTable.tableName.trim() && ed.currentTable.columns.length > 0;

  return (
    <div className="form-section">
      <h2 className="form-section__title">Datos de origen</h2>

      {/* ── Panel nueva tabla ── */}
      <div className="dwh-table-panel">
        <p className="dwh-panel-label">Nueva tabla</p>

        <div className="staging-add-row">
          <div className="form-field" style={{ flex: "2 1 200px" }}>
            <label>Nombre de tabla</label>
            <input
              type="text"
              placeholder="ej. clientes"
              value={ed.currentTable.tableName}
              onChange={(e) => ed.setCurrentTable({ ...ed.currentTable, tableName: e.target.value })}
            />
          </div>
        </div>

        {/* ── Definición de columna ── */}
        <div className="origen-col-form">
          <p className="origen-col-form__label">Nueva columna</p>

          <div className="staging-add-row">
            <div className="form-field">
              <label>Columna</label>
              <input
                type="text"
                placeholder="Nombre"
                value={ed.currentCol.name}
                onChange={(e) => ed.setCurrentCol({ ...ed.currentCol, name: e.target.value })}
              />
            </div>
            <div className="form-field">
              <label>Tipo</label>
              <select
                value={ed.currentCol.dataType}
                onChange={(e) => ed.setCurrentCol({ ...ed.currentCol, dataType: e.target.value })}
              >
                {TIPOS.map(t => <option key={t}>{t}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label>Formato</label>
              <select
                value={ed.currentCol.dataFormat}
                onChange={(e) => ed.setCurrentCol({ ...ed.currentCol, dataFormat: e.target.value })}
              >
                {FORMATOS.map(f => <option key={f} value={f}>{f || "—"}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label>Rol</label>
              <select
                value={ed.currentCol.role}
                onChange={(e) => ed.setCurrentCol({ ...ed.currentCol, role: e.target.value })}
              >
                {ROLES.map(r => <option key={r}>{r}</option>)}
              </select>
            </div>
          </div>

          {/* ── Datos de la columna ── */}
          <div className="origen-dato-section">
            <label className="origen-dato-label">Datos</label>
            <div className="origen-dato-input-row">
              <input
                type="text"
                placeholder="Ingrese un dato y presione +"
                value={currentDato}
                onChange={(e) => setCurrentDato(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); handleAddDato(); } }}
              />
              <button className="staging-add-btn" onClick={handleAddDato} disabled={!currentDato.trim()}>
                +
              </button>
            </div>
            {ed.currentCol.data.length > 0 && (
              <div className="origen-dato-tags">
                {ed.currentCol.data.map((d, i) => (
                  <span key={i} className="origen-dato-tag">
                    {d}
                    <button className="origen-dato-remove" onClick={() => handleRemoveDato(i)}>✕</button>
                  </span>
                ))}
              </div>
            )}
          </div>

          <button className="staging-add-btn" onClick={handleAddColumn} disabled={!ed.currentCol.name.trim()}>
            + Columna
          </button>
        </div>

        {/* ── Preview de columnas agregadas ── */}
        {ed.currentTable.columns.length > 0 && (
          <div className="origen-cols-preview">
            {ed.currentTable.columns.map((col, i) => (
              <CollapseRow key={i} col={col} onRemove={() => ed.removeColumn(i)} />
            ))}
          </div>
        )}

        <button className="dwh-add-table-btn" onClick={handleSaveTable} disabled={!canAddTable}>
          {ed.editingIndex !== null ? "Guardar cambios" : "+ Agregar tabla"}
        </button>
      </div>

      {/* ── Tablas guardadas ── */}
      {tables.length > 0 && (
        <div className="dwh-tables-list">
          {tables.map((table, i) => (
            <div key={i} className="dwh-table-card">
              <div className="dwh-table-card__header">
                <span className="dwh-table-card__name">{table.tableName}</span>
                <button className="staging-edit-btn" onClick={() => handleEditTable(i)}>✎</button>
                <button className="staging-remove-btn" onClick={() => ed.removeAt(i)}>✕</button>
              </div>
              <div className="origen-saved-cols">
                {table.columns.map((col, j) => (
                  <CollapseRow key={j} col={col} />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
