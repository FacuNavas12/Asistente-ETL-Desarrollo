import { useState } from "react";
import { useTableEditor, TablePanel, SaveTableButton } from "../Tables/tableUtils";
import "../../css/shared.css";
import "../../css/inputOrigin.css";
import { formatInputName } from "../../validation/stringCleaners";

const TIPOS    = ["string", "int", "float", "bool", "date"];
const FORMATOS = ["", "dd/MM/yyyy", "ISO8601", "decimal(10,2)"];
const ROLES    = ["PK", "FK", "clave natural", "atributo"];

const EMPTY_TABLE = { tableName: "", columns: [] };
const EMPTY_COL   = { name: "", dataType: "string", dataFormat: "", role: "atributo" };

function CollapseRow({ col, onRemove, onEdit }) {
  return (
    <div className="origen-col-collapse">
      <div className="origen-col-collapse__header">
        <span className="origen-col-toggle--placeholder" />
        <span className="origen-col-name">{col.name}</span>
        <span className="origen-col-meta">
          {col.dataType}{col.dataFormat ? ` · ${col.dataFormat}` : ""} · {col.role}
        </span>
        {onEdit   && <button className="staging-edit-btn"   onClick={onEdit}>✎</button>}
        {onRemove && <button className="staging-remove-btn" onClick={onRemove}>✕</button>}
      </div>
    </div>
  );
}

export { CollapseRow };

export default function OrigenInputFormulario({ value, onChange }) {
  const tables = Array.isArray(value) ? value : [];
  const [editingColIdx, setEditingColIdx] = useState(null);

  const ed = useTableEditor({
    emptyTable: EMPTY_TABLE,
    emptyCol:   EMPTY_COL,
    tables,
    setTables:  onChange,
    columnsKey: "columns",
  });

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
  };

  const handleCancelColEdit = () => {
    setEditingColIdx(null);
    ed.setCurrentCol(EMPTY_COL);
  };

  const handleEditColumn = (i) => {
    ed.setCurrentCol({ ...ed.currentTable.columns[i] });
    setEditingColIdx(i);
  };

  const handleSaveTable = () => {
    if (!ed.currentTable.tableName.trim() || ed.currentTable.columns.length === 0) return;
    ed.saveTable(t => ({ ...t, tableName: formatInputName(t.tableName) }));
    setEditingColIdx(null);
  };

  const canAddTable  = ed.currentTable.tableName.trim() && ed.currentTable.columns.length > 0;
  const isEditingCol = editingColIdx !== null;

  return (
    <div className="form-section">
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
                {FORMATOS.map(f => <option key={f} value={f}>{f || " "}</option>)}
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

    </div>
  );
}
