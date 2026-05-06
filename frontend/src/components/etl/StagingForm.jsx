import "../../css/etlForm.css";
import { useTableEditor, ColumnTable } from "./tableUtils";

const EMPTY_TABLE = { tableName: "", origenVinculado: "", columns: [] };
const EMPTY_COL   = { nombre: "", tipo: "Texto", regla: "MAYÚSCULAS", datoNoValido: "Reemplazar por NULL" };

const ORIGEN_TYPE_MAP = { string: "Texto", int: "Número", float: "Número", bool: "Booleano", date: "Fecha" };

const STG_COL_DEFS = [
  { key: "nombre",       label: "Campo" },
  { key: "tipo",         label: "Tipo" },
  { key: "regla",        label: "Regla" },
  { key: "datoNoValido", label: "Dato no válido" },
];

// value: [{ tableName, origenVinculado, columns: [{nombre, tipo, regla, datoNoValido}] }]
// origenTables: OrigenInput value — [{ tableName, columns: [{name, dataType, ...}] }]
export default function StagingForm({ value, onChange, origenTables = [] }) {
  const tables    = Array.isArray(value) ? value : [];
  const setTables = onChange;

  const ed = useTableEditor({
    emptyTable: EMPTY_TABLE,
    emptyCol:   EMPTY_COL,
    tables,
    setTables,
    columnsKey: "columns",
  });

  const origenCols = origenTables
    .find(t => t.tableName === ed.currentTable.origenVinculado)
    ?.columns ?? [];

  const handleAddColumn = () => {
    if (!ed.currentCol.nombre) return;
    ed.addColumn(ed.currentCol);
  };

  const handleSaveTable = () => {
    if (!ed.currentTable.tableName.trim() || ed.currentTable.columns.length === 0) return;
    ed.saveTable();
  };

  const canAddTable = ed.currentTable.tableName.trim() && ed.currentTable.columns.length > 0;

  return (
    <div className="form-section">
      <h2 className="form-section__title">Definición de tabla Staging</h2>

      <div className="dwh-table-panel">
        <p className="dwh-panel-label">Nueva tabla</p>

        <div className="staging-add-row">
          <div className="form-field staging-table-name" style={{ flex: "2 1 200px" }}>
            <label>Nombre de tabla Staging</label>
            <input
              type="text"
              placeholder="Ej: STG_CLIENTES"
              value={ed.currentTable.tableName}
              onChange={(e) => ed.setCurrentTable({ ...ed.currentTable, tableName: e.target.value })}
            />
          </div>

          <div className="form-field">
            <label>Tabla de origen</label>
            <select
              value={ed.currentTable.origenVinculado}
              onChange={(e) => ed.setCurrentTable({ ...ed.currentTable, origenVinculado: e.target.value })}
            >
              <option value="">— Seleccionar —</option>
              {origenTables.map(t => (
                <option key={t.tableName} value={t.tableName}>{t.tableName}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Nueva columna */}
        <div className="staging-add-row">
          <div className="form-field">
            <label>Campo</label>
            <select
              value={ed.currentCol.nombre}
              onChange={(e) => {
                const selectedName = e.target.value;
                const origenCol = origenCols.find(c => c.name === selectedName);
                const tipo = origenCol ? (ORIGEN_TYPE_MAP[origenCol.dataType] ?? "Texto") : ed.currentCol.tipo;
                ed.setCurrentCol({ ...ed.currentCol, nombre: selectedName, tipo });
              }}
              disabled={!ed.currentTable.origenVinculado}
            >
              <option value="">— Seleccionar —</option>
              {origenCols.map(c => (
                <option key={c.name} value={c.name}>{c.name}</option>
              ))}
            </select>
          </div>

          <div className="form-field">
            <label>Tipo de dato</label>
            <select
              value={ed.currentCol.tipo}
              onChange={(e) => ed.setCurrentCol({ ...ed.currentCol, tipo: e.target.value })}
            >
              <option>Texto</option>
              <option>Número</option>
              <option>Fecha</option>
              <option>Booleano</option>
            </select>
          </div>

          <div className="form-field">
            <label>Regla de limpieza</label>
            <select
              value={ed.currentCol.regla}
              onChange={(e) => ed.setCurrentCol({ ...ed.currentCol, regla: e.target.value })}
            >
              <option>MAYÚSCULAS</option>
              <option>minúsculas</option>
              <option>Title Case</option>
              <option>Eliminar espacios extras</option>
              <option>Eliminar caracteres especiales</option>
              <option>Reemplazar según diccionario</option>
            </select>
          </div>

          <div className="form-field">
            <label>Dato no válido</label>
            <select
              value={ed.currentCol.datoNoValido}
              onChange={(e) => ed.setCurrentCol({ ...ed.currentCol, datoNoValido: e.target.value })}
            >
              <option>Reemplazar por NULL</option>
              <option>Eliminar fila</option>
              <option>Usar valor por defecto</option>
            </select>
          </div>

          <button
            className="staging-add-btn"
            onClick={handleAddColumn}
            disabled={!ed.currentCol.nombre}
            title="Agregar columna"
          >
            + Agregar
          </button>
        </div>

        <ColumnTable
          columns={ed.currentTable.columns}
          columnDefs={STG_COL_DEFS}
          onRemove={ed.removeColumn}
        />

        <button className="dwh-add-table-btn" onClick={handleSaveTable} disabled={!canAddTable}>
          {ed.editingIndex !== null ? "Guardar cambios" : "+ Agregar tabla"}
        </button>
      </div>

      {tables.length > 0 && (
        <div className="dwh-tables-list">
          {tables.map((table, i) => (
            <div key={i} className="dwh-table-card">
              <div className="dwh-table-card__header">
                <span className="dwh-table-card__name">{table.tableName}</span>
                {table.origenVinculado && (
                  <span className="dwh-table-card__origen">← {table.origenVinculado}</span>
                )}
                <button className="staging-edit-btn" onClick={() => ed.editTable(i)}>✎</button>
                <button className="staging-remove-btn" onClick={() => ed.removeAt(i)}>✕</button>
              </div>
              <ColumnTable columns={table.columns} columnDefs={STG_COL_DEFS} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
