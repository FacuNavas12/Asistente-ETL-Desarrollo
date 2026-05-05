import "../../css/etlForm.css";
import { useTableEditor, ColumnTable } from "./tableUtils";
import {
  formatTableName,
  cleanColumnText,
  applySKPrefix,
  removeSKPrefix
} from "../../validation/stringCleanersDWH";

const EMPTY_TABLE = { tipo: "Dimension", nombre: "", origenVinculado: "", columnas: [] };
const EMPTY_COL   = { nombre: "", tipo: "Texto", esSurrogateKey: false };

const DWH_COL_DEFS = [
  { key: "nombre",         label: "Columna" },
  { key: "tipo",           label: "Tipo" },
  { key: "esSurrogateKey", label: "SK", render: (col) => col.esSurrogateKey ? "✔" : "—" },
];

export default function DwhModel({ value, onChange }) {
  const tables    = value?.tables ?? [];
  const setTables = (newTables) => onChange({ ...value, tables: newTables });

  const ed = useTableEditor({
    emptyTable: EMPTY_TABLE,
    emptyCol:   EMPTY_COL,
    tables,
    setTables,
    columnsKey: "columnas",
  });

  const handleColumnNameInput = (val) => {
    let cleaned = cleanColumnText(val);
    cleaned = ed.currentCol.esSurrogateKey ? applySKPrefix(cleaned) : removeSKPrefix(cleaned);
    ed.setCurrentCol({ ...ed.currentCol, nombre: cleaned });
  };

  const handleAddColumn = () => {
    if (!ed.currentCol.nombre.trim()) return;
    ed.addColumn(ed.currentCol);
  };

  const handleSaveTable = () => {
    if (!ed.currentTable.nombre.trim() || ed.currentTable.columnas.length === 0) return;
    ed.saveTable(t => ({ ...t, nombre: formatTableName(t.nombre, t.tipo) }));
  };

  const canAddTable = ed.currentTable.nombre.trim() && ed.currentTable.columnas.length > 0;

  return (
    <div className="form-section">
      <h2 className="form-section__title">Modelo de DWH</h2>

      {/* ── Panel nueva tabla ── */}
      <div className="dwh-table-panel">
        <p className="dwh-panel-label">Nueva tabla</p>

        <div className="staging-add-row">
          <div className="form-field">
            <label>Tipo</label>
            <select
              value={ed.currentTable.tipo}
              onChange={(e) => ed.setCurrentTable({ ...ed.currentTable, tipo: e.target.value })}
            >
              <option>Dimension</option>
              <option>Fact</option>
            </select>
          </div>

          <div className="form-field" style={{ flex: "2 1 200px" }}>
            <label>Nombre de tabla</label>
            <input
              type="text"
              placeholder="Ej: cliente"
              value={ed.currentTable.nombre}
              onChange={(e) => ed.setCurrentTable({ ...ed.currentTable, nombre: e.target.value })}
            />
          </div>
        </div>

        <div className="form-field">
          <label>Tabla / fuente de origen vinculada</label>
          <input
            type="text"
            placeholder="Ej: STG_CLIENTES o tabla_ventas del ERP"
            value={ed.currentTable.origenVinculado}
            onChange={(e) => ed.setCurrentTable({ ...ed.currentTable, origenVinculado: e.target.value })}
          />
        </div>

        {/* Nueva columna */}
        <div className="staging-add-row">
          <div className="form-field">
            <label>Nombre de columna</label>
            <input
              type="text"
              placeholder="Ej: SK_CLIENTE"
              value={ed.currentCol.nombre}
              onChange={(e) => handleColumnNameInput(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label>Tipo de dato</label>
            <select
              value={ed.currentCol.tipo}
              onChange={(e) => ed.setCurrentCol({ ...ed.currentCol, tipo: e.target.value })}
            >
              <option>Texto</option>
              <option>Entero</option>
              <option>Decimal</option>
              <option>Fecha</option>
              <option>Booleano</option>
            </select>
          </div>

          <div className="form-field dwh-sk-field">
            <label>Surrogate Key</label>
            <label className="dwh-checkbox-label">
              <input
                type="checkbox"
                checked={ed.currentCol.esSurrogateKey}
                onChange={(e) => {
                  const checked = e.target.checked;
                  let newName = cleanColumnText(ed.currentCol.nombre);
                  newName = checked ? applySKPrefix(newName) : removeSKPrefix(newName);
                  ed.setCurrentCol({ ...ed.currentCol, esSurrogateKey: checked, nombre: newName });
                }}
              />
              Sí
            </label>
          </div>

          <button
            className="staging-add-btn"
            onClick={handleAddColumn}
            disabled={!ed.currentCol.nombre.trim()}
          >
            + Columna
          </button>
        </div>

        <ColumnTable
          columns={ed.currentTable.columnas}
          columnDefs={DWH_COL_DEFS}
          onRemove={ed.removeColumn}
          wrapperClass="dwh-col-preview"
        />

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
                <span className={`dwh-badge dwh-badge--${table.tipo.toLowerCase()}`}>
                  {table.tipo}
                </span>
                <span className="dwh-table-card__name">{table.nombre}</span>
                {table.origenVinculado && (
                  <span className="dwh-table-card__origen">← {table.origenVinculado}</span>
                )}
                <button className="staging-edit-btn" onClick={() => ed.editTable(i)}>✎</button>
                <button className="staging-remove-btn" onClick={() => ed.removeAt(i)}>✕</button>
              </div>

              <ColumnTable columns={table.columnas} columnDefs={DWH_COL_DEFS} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
