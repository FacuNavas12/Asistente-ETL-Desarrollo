import { useState } from "react";
import "../etlForm.css";
import { useTableEditor, ColumnTable, TablePanel, SaveTableButton, TableCardHeader, SavedTablesList } from "../tableUtils";
import {
  formatTableName,
  cleanColumnText,
  applySKPrefix,
  removeSKPrefix
} from "../../validation/stringCleaners";

const EMPTY_TABLE = { tipo: "Dimension", nombre: "", origenVinculado: "", columnas: [] };
const EMPTY_COL   = { nombre: "", tipo: "Texto", esSurrogateKey: false };

const STG_DWH_TYPE_MAP = { Texto: "Texto", Numero: "Entero", Fecha: "Fecha", Booleano: "Booleano" };

const DWH_COL_DEFS = [
  { key: "nombre",         label: "Columna" },
  { key: "tipo",           label: "Tipo" },
  { key: "esSurrogateKey", label: "SK", render: (col) => col.esSurrogateKey ? "✓" : "✗" },
];

export default function DwhModel({ value, onChange, stagingTables = [] }) {
  const tables    = value?.tables ?? [];
  const setTables = (newTables) => onChange({ ...value, tables: newTables });

  const ed = useTableEditor({
    emptyTable: EMPTY_TABLE,
    emptyCol:   EMPTY_COL,
    tables,
    setTables,
    columnsKey: "columnas",
  });

  const [selectedStgColName, setSelectedStgColName] = useState("");

  const stagingCols = stagingTables
    .find(t => t.tableName === ed.currentTable.origenVinculado)
    ?.columns ?? [];

  const handleAddColumn = () => {
    if (!ed.currentCol.nombre.trim()) return;
    ed.addColumn(ed.currentCol);
    setSelectedStgColName("");
  };

  const handleSaveTable = () => {
    if (!ed.currentTable.nombre.trim() || ed.currentTable.columnas.length === 0) return;
    ed.saveTable(t => ({ ...t, nombre: formatTableName(t.nombre, t.tipo) }));
    setSelectedStgColName("");
  };

  const handleEditTable = (i) => {
    setSelectedStgColName("");
    ed.editTable(i);
  };

  const canAddTable = ed.currentTable.nombre.trim() && ed.currentTable.columnas.length > 0;

  return (
    <div className="form-section">
      <h2 className="form-section__title">Modelo de DWH</h2>

      <TablePanel editingIndex={ed.editingIndex}>

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
          <select
            value={ed.currentTable.origenVinculado}
            onChange={(e) => {
              ed.setCurrentTable({ ...ed.currentTable, origenVinculado: e.target.value });
              setSelectedStgColName("");
              ed.setCurrentCol({ ...EMPTY_COL });
            }}
          >
            <option value="">Seleccionar</option>
            {stagingTables.map(t => (
              <option key={t.tableName} value={t.tableName}>{t.tableName}</option>
            ))}
          </select>
        </div>

        {/* Nueva columna */}
        <div className="staging-add-row">
          <div className="form-field">
            <label>Nombre de columna</label>
            <select
              value={selectedStgColName}
              onChange={(e) => {
                const rawName = e.target.value;
                setSelectedStgColName(rawName);
                const stgCol = stagingCols.find(c => c.nombre === rawName);
                let cleaned = rawName ? cleanColumnText(rawName) : "";
                cleaned = ed.currentCol.esSurrogateKey ? applySKPrefix(cleaned) : removeSKPrefix(cleaned);
                const tipo = stgCol ? (STG_DWH_TYPE_MAP[stgCol.tipo] ?? "Texto") : "Texto";
                ed.setCurrentCol({ ...ed.currentCol, nombre: cleaned, tipo });
              }}
              disabled={!ed.currentTable.origenVinculado}
            >
              <option value="">Seleccionar</option>
              {stagingCols.map(c => (
                <option key={c.nombre} value={c.nombre}>{c.nombre}</option>
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
              Si
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

        <SaveTableButton
          editingIndex={ed.editingIndex}
          onClick={handleSaveTable}
          disabled={!canAddTable}
        />
      </TablePanel>

      {/* Tablas guardadas */}
      <SavedTablesList
        tables={tables}
        renderCard={(table, i) => (
          <>
            <TableCardHeader
              prefix={<span className={`dwh-badge dwh-badge--${table.tipo.toLowerCase()}`}>{table.tipo}</span>}
              name={table.nombre}
              origen={table.origenVinculado}
              onEdit={() => handleEditTable(i)}
              onRemove={() => ed.removeAt(i)}
            />
            <ColumnTable columns={table.columnas} columnDefs={DWH_COL_DEFS} />
          </>
        )}
      />
    </div>
  );
}


