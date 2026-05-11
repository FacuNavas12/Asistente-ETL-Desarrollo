import { useState } from "react";
import "../../css/etlForm.css";
import { useTableEditor, TablePanel, SaveTableButton, TableCardHeader, SavedTablesList } from "./tableUtils";
import { formatInputName } from "../../validation/stringCleanersDWH";

const TIPOS    = ["string", "int", "float", "bool", "date"];
const FORMATOS = ["", "dd/MM/yyyy", "ISO8601", "decimal(10,2)"];
const ROLES    = ["PK", "FK", "clave natural", "atributo"];

const EMPTY_TABLE = { tableName: "", columns: [] };
const EMPTY_COL   = { name: "", dataType: "string", dataFormat: "", role: "atributo", data: [] };

function CollapseRow({ col, onRemove, onEdit }) {
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
        {onEdit   && <button className="staging-edit-btn"   onClick={onEdit}>✎</button>}
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
  const [currentDato,   setCurrentDato]   = useState("");
  const [editingColIdx, setEditingColIdx] = useState(null);

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
    if (editingColIdx !== null) {
      ed.setCurrentTable(t => ({
        ...t,
        columns: t.columns.map((c, idx) => idx === editingColIdx ? ed.currentCol : c),
      }));
      setEditingColIdx(null);
    } else {
      ed.addColumn(ed.currentCol);
    }
    setCurrentDato("");
  };

  const handleCancelColEdit = () => {
    setEditingColIdx(null);
    ed.setCurrentCol(EMPTY_COL);
    setCurrentDato("");
  };

  const handleEditColumn = (i) => {
    ed.setCurrentCol({ ...ed.currentTable.columns[i] });
    setEditingColIdx(i);
    setCurrentDato("");
  };

  const handleEditTable = (i) => {
    ed.editTable(i);
    setEditingColIdx(null);
    setCurrentDato("");
  };

  const handleSaveTable = () => {
    if (!ed.currentTable.tableName.trim() || ed.currentTable.columns.length === 0) return;
    ed.saveTable(t => ({ ...t, tableName: formatInputName(t.tableName) }));
    setEditingColIdx(null);
    setCurrentDato("");
  };

  const canAddTable  = ed.currentTable.tableName.trim() && ed.currentTable.columns.length > 0;
  const isEditingCol = editingColIdx !== null;

  return (
    <div className="form-section">
      <h2 className="form-section__title">Datos de origen</h2>

      <TablePanel editingIndex={ed.editingIndex}>

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
          <p className="origen-col-form__label">{isEditingCol ? "Editar columna" : "Nueva columna"}</p>

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

          <div className="staging-add-row" style={{ marginBottom: 0 }}>
            <button className="staging-add-btn" onClick={handleAddColumn} disabled={!ed.currentCol.name.trim()}>
              {isEditingCol ? "Actualizar columna" : "+ Columna"}
            </button>
            {isEditingCol && (
              <button className="staging-remove-btn origen-cancel-btn" onClick={handleCancelColEdit}>
                Cancelar
              </button>
            )}
          </div>
        </div>

        {/* ── Preview de columnas de la tabla actual ── */}
        {ed.currentTable.columns.length > 0 && (
          <div className="origen-cols-preview">
            {ed.currentTable.columns.map((col, i) => (
              <CollapseRow
                key={i}
                col={col}
                onEdit={() => handleEditColumn(i)}
                onRemove={editingColIdx === i ? undefined : () => ed.removeColumn(i)}
              />
            ))}
          </div>
        )}

        <SaveTableButton
          editingIndex={ed.editingIndex}
          onClick={handleSaveTable}
          disabled={!canAddTable}
        />
      </TablePanel>

      {/* ── Tablas guardadas ── */}
      <SavedTablesList
        tables={tables}
        renderCard={(table, i) => (
          <>
            <TableCardHeader
              name={table.tableName}
              onEdit={() => handleEditTable(i)}
              onRemove={() => ed.removeAt(i)}
            />
            <div className="origen-saved-cols">
              {table.columns.map((col, j) => (
                <CollapseRow key={j} col={col} />
              ))}
            </div>
          </>
        )}
      />
    </div>
  );
}
