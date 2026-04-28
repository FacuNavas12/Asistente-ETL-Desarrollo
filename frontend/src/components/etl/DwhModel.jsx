import { useState } from "react";
import "../../css/etlForm.css";

import {
  formatTableName,
  cleanColumnText,
  applySKPrefix,
  removeSKPrefix
} from "../../validation/stringCleaners";

const EMPTY_TABLE = { tipo: "Dimension", nombre: "", columnas: [] };
const EMPTY_COL = { nombre: "", tipo: "Texto", esSurrogateKey: false };

export default function DwhModel({ value, onChange }) {
  const [currentTable, setCurrentTable] = useState(EMPTY_TABLE);
  const [currentCol, setCurrentCol] = useState(EMPTY_COL);

  const tables = value?.tables ?? [];

  // ================================
  //  ⭐ AUTOCORRECCIÓN DE COLUMNAS
  // ================================
  const handleColumnNameInput = (value) => {
    let cleaned = cleanColumnText(value);

    if (currentCol.esSurrogateKey) {
      cleaned = applySKPrefix(cleaned);
    } else {
      cleaned = removeSKPrefix(cleaned);
    }

    setCurrentCol({ ...currentCol, nombre: cleaned });
  };

  const handleAddColumn = () => {
    if (!currentCol.nombre.trim()) return;

    setCurrentTable((t) => ({
      ...t,
      columnas: [...t.columnas, currentCol],
    }));

    setCurrentCol(EMPTY_COL);
  };

  const handleRemoveColumn = (i) => {
    setCurrentTable((t) => ({
      ...t,
      columnas: t.columnas.filter((_, idx) => idx !== i),
    }));
  };

  // ================================
  //  ⭐ AUTOCORRECCIÓN DE TABLAS
  // ================================
  const handleTableNameInput = (value) => {
    const formatted = formatTableName(value);
    setCurrentTable({ ...currentTable, nombre: formatted });
  };

  const handleAddTable = () => {
    if (!currentTable.nombre.trim() || currentTable.columnas.length === 0)
      return;

    onChange({ ...value, tables: [...tables, currentTable] });

    setCurrentTable(EMPTY_TABLE);
    setCurrentCol(EMPTY_COL);
  };

  const handleRemoveTable = (i) => {
    onChange({
      ...value,
      tables: tables.filter((_, idx) => idx !== i),
    });
  };

  const canAddTable =
    currentTable.nombre.trim() && currentTable.columnas.length > 0;

  return (
    <div className="form-section">
      <h2 className="form-section__title">Modelo de DWH</h2>

      {/* Nueva tabla */}
      <div className="dwh-table-panel">
        <p className="dwh-panel-label">Nueva tabla</p>

        <div className="staging-add-row">
          <div className="form-field">
            <label>Tipo</label>
            <select
              value={currentTable.tipo}
              onChange={(e) =>
                setCurrentTable({ ...currentTable, tipo: e.target.value })
              }
            >
              <option>Dimension</option>
              <option>Fact</option>
            </select>
          </div>

          <div className="form-field" style={{ flex: "2 1 200px" }}>
            <label>Nombre de tabla</label>

            {/* ⭐ Ahora autocorrige al escribir */}
            <input
              type="text"
              placeholder="Ej: DIM_CLIENTE"
              value={currentTable.nombre}
              onChange={(e) => handleTableNameInput(e.target.value)}
            />
          </div>
        </div>

        {/* Nueva columna */}
        <div className="staging-add-row">
          <div className="form-field">
            <label>Nombre de columna</label>

            {/* ⭐ Ahora autocorrige al escribir */}
            <input
              type="text"
              placeholder="Ej: SK_CLIENTE"
              value={currentCol.nombre}
              onChange={(e) => handleColumnNameInput(e.target.value)}
            />
          </div>

          <div className="form-field">
            <label>Tipo de dato</label>
            <select
              value={currentCol.tipo}
              onChange={(e) =>
                setCurrentCol({ ...currentCol, tipo: e.target.value })
              }
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
                checked={currentCol.esSurrogateKey}
                onChange={(e) => {
                  const checked = e.target.checked;
                  let newName = cleanColumnText(currentCol.nombre);

                  newName = checked
                    ? applySKPrefix(newName)
                    : removeSKPrefix(newName);

                  setCurrentCol({
                    ...currentCol,
                    esSurrogateKey: checked,
                    nombre: newName
                  });
                }}
              />
              Sí
            </label>
          </div>

          <button
            className="staging-add-btn"
            onClick={handleAddColumn}
            disabled={!currentCol.nombre.trim()}
          >
            + Columna
          </button>
        </div>

        {/* Columnas de la tabla actual */}
        {currentTable.columnas.length > 0 && (
          <div className="staging-table-wrapper dwh-col-preview">
            <table className="staging-table">
              <thead>
                <tr>
                  <th>Columna</th>
                  <th>Tipo</th>
                  <th>SK</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {currentTable.columnas.map((col, i) => (
                  <tr key={i}>
                    <td>{col.nombre}</td>
                    <td>{col.tipo}</td>
                    <td>{col.esSurrogateKey ? "✔" : "—"}</td>
                    <td>
                      <button
                        className="staging-remove-btn"
                        onClick={() => handleRemoveColumn(i)}
                      >
                        ✕
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        <button
          className="dwh-add-table-btn"
          onClick={handleAddTable}
          disabled={!canAddTable}
        >
          + Agregar tabla
        </button>
      </div>

      {/* Tablas ya agregadas */}
      {tables.length > 0 && (
        <div className="dwh-tables-list">
          {tables.map((table, i) => (
            <div key={i} className="dwh-table-card">
              <div className="dwh-table-card__header">
                <span
                  className={`dwh-badge dwh-badge--${table.tipo.toLowerCase()}`}
                >
                  {table.tipo}
                </span>
                <span className="dwh-table-card__name">{table.nombre}</span>
                <button
                  className="staging-remove-btn"
                  onClick={() => handleRemoveTable(i)}
                >
                  ✕
                </button>
              </div>

              <div className="staging-table-wrapper">
                <table className="staging-table">
                  <thead>
                    <tr>
                      <th>Columna</th>
                      <th>Tipo</th>
                      <th>SK</th>
                    </tr>
                  </thead>
                  <tbody>
                    {table.columnas.map((col, j) => (
                      <tr key={j}>
                        <td>{col.nombre}</td>
                        <td>{col.tipo}</td>
                        <td>{col.esSurrogateKey ? "✔" : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
