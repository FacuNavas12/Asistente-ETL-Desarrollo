import { useState } from "react";
import "./etlForm.css";

export function useTableList(items, setItems) {
  return {
    add:        (item)         => setItems([...items, item]),
    removeAt:   (i)            => setItems(items.filter((_, idx) => idx !== i)),
    updateAt:   (i, updated)   => setItems(items.map((t, idx) => idx === i ? updated : t)),
    removeById: (id)           => setItems(items.filter(t => t.id !== id)),
    updateById: (id, updated)  => setItems(items.map(t => t.id === id ? updated : t)),
  };
}

export function useTableEditor({ emptyTable, emptyCol, tables, setTables, columnsKey }) {
  const [currentTable, setCurrentTable] = useState(emptyTable);
  const [currentCol,   setCurrentCol]   = useState(emptyCol);
  const [editingIndex, setEditingIndex] = useState(null);
  const tbl = useTableList(tables, setTables);

  const addColumn = (col) => {
    setCurrentTable(t => ({ ...t, [columnsKey]: [...t[columnsKey], col] }));
    setCurrentCol(emptyCol);
  };

  const removeColumn = (i) =>
    setCurrentTable(t => ({ ...t, [columnsKey]: t[columnsKey].filter((_, idx) => idx !== i) }));

  const saveTable = (transform) => {
    const saved = transform ? transform(currentTable) : currentTable;
    if (editingIndex !== null) {
      tbl.updateAt(editingIndex, saved);
    } else {
      tbl.add(saved);
    }
    setCurrentTable(emptyTable);
    setCurrentCol(emptyCol);
    setEditingIndex(null);
  };

  const editTable = (i) => {
    setCurrentTable(JSON.parse(JSON.stringify(tables[i])));
    setCurrentCol(emptyCol);
    setEditingIndex(i);
  };

  return {
    currentTable, setCurrentTable,
    currentCol,   setCurrentCol,
    editingIndex,
    addColumn, removeColumn,
    saveTable, editTable,
    removeAt: tbl.removeAt,
  };
}

export function ColumnTable({ columns, columnDefs, onRemove, wrapperClass = "" }) {
  if (!columns || !columns.length) return null;

  return (
    <div className={`staging-table-wrapper${wrapperClass ? ` ${wrapperClass}` : ""}`}>
      <table className="staging-table">
        <thead>
          <tr>
            {columnDefs.map(d => <th key={d.key}>{d.label}</th>)}
            {onRemove && <th />}
          </tr>
        </thead>
        <tbody>
          {columns.map((col, i) => (
            <tr key={col.id ?? i}>
              {columnDefs.map(d => (
                <td key={d.key}>{d.render ? d.render(col) : col[d.key]}</td>
              ))}
              {onRemove && (
                <td>
                  <button className="staging-remove-btn" onClick={() => onRemove(i)}>✕</button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function TablePanel({ editingIndex, children }) {
  return (
    <div className="dwh-table-panel">
      <p className="dwh-panel-label">
        {editingIndex !== null ? "Editar tabla" : "Nueva tabla"}
      </p>
      {children}
    </div>
  );
}

export function SaveTableButton({ editingIndex, onClick, disabled }) {
  return (
    <button className="dwh-add-table-btn" onClick={onClick} disabled={disabled}>
      {editingIndex !== null ? "Guardar cambios" : "+ Agregar tabla"}
    </button>
  );
}

export function TableCardHeader({ name, origen, onEdit, onRemove, prefix }) {
  return (
    <div className="dwh-table-card__header">
      {prefix}
      <span className="dwh-table-card__name">{name}</span>
      {origen && <span className="dwh-table-card__origen">← {origen}</span>}
      {onEdit   && <button className="staging-edit-btn"   onClick={onEdit}>✎</button>}
      {onRemove && <button className="staging-remove-btn" onClick={onRemove}>✕</button>}
    </div>
  );
}

export function SavedTablesList({ tables, renderCard }) {
  if (!tables?.length) return null;
  return (
    <div className="dwh-tables-list">
      {tables.map((table, i) => (
        <div key={i} className="dwh-table-card">
          {renderCard(table, i)}
        </div>
      ))}
    </div>
  );
}
