import { useState } from "react";
import "../../css/etlForm.css";

const EMPTY_COLUMN = { nombre: "", tipo: "Texto", regla: "MAYÚSCULAS", datoNoValido: "Reemplazar por NULL" };

export default function StagingForm({ value, onChange }) {
  const [current, setCurrent] = useState(EMPTY_COLUMN);

  const handleAdd = () => {
    if (!current.nombre.trim()) return;
    const updated = {
      ...value,
      columns: [...(value?.columns ?? []), current],
    };
    onChange(updated);
    setCurrent(EMPTY_COLUMN);
  };

  const handleRemove = (index) => {
    const updated = {
      ...value,
      columns: value.columns.filter((_, i) => i !== index),
    };
    onChange(updated);
  };

  const handleTableName = (tableName) => {
    onChange({ ...value, tableName });
  };

  const columns = value?.columns ?? [];

  return (
    <div className="form-section">
      <h2 className="form-section__title">Definición de tabla Staging</h2>

      <div className="form-field staging-table-name">
        <label>Nombre de tabla Staging</label>
        <input
          type="text"
          placeholder="Ej: STG_ESTUDIANTES"
          value={value?.tableName ?? ""}
          onChange={(e) => handleTableName(e.target.value)}
        />
      </div>

      <div className="form-field">
        <label>Tabla / fuente de origen vinculada</label>
        <input
          type="text"
          placeholder="Ej: tabla_clientes del sistema CRM"
          value={value?.origenVinculado ?? ""}
          onChange={(e) => onChange({ ...value, origenVinculado: e.target.value })}
        />
      </div>

      <div className="staging-add-row">
        <div className="form-field">
          <label>Nombre del campo</label>
          <input
            type="text"
            placeholder="Ej: Nombre"
            value={current.nombre}
            onChange={(e) => setCurrent({ ...current, nombre: e.target.value })}
          />
        </div>

        <div className="form-field">
          <label>Tipo de dato</label>
          <select value={current.tipo} onChange={(e) => setCurrent({ ...current, tipo: e.target.value })}>
            <option>Texto</option>
            <option>Número</option>
            <option>Fecha</option>
            <option>Booleano</option>
          </select>
        </div>

        <div className="form-field">
          <label>Regla de limpieza</label>
          <select value={current.regla} onChange={(e) => setCurrent({ ...current, regla: e.target.value })}>
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
          <select value={current.datoNoValido} onChange={(e) => setCurrent({ ...current, datoNoValido: e.target.value })}>
            <option>Reemplazar por NULL</option>
            <option>Eliminar fila</option>
            <option>Usar valor por defecto</option>
          </select>
        </div>

        <button
          className="staging-add-btn"
          onClick={handleAdd}
          disabled={!current.nombre.trim()}
          title="Agregar columna"
        >
          + Agregar
        </button>
      </div>

      {columns.length > 0 && (
        <div className="staging-table-wrapper">
          <table className="staging-table">
            <thead>
              <tr>
                <th>Campo</th>
                <th>Tipo</th>
                <th>Regla</th>
                <th>Dato no válido</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {columns.map((col, i) => (
                <tr key={i}>
                  <td>{col.nombre}</td>
                  <td>{col.tipo}</td>
                  <td>{col.regla}</td>
                  <td>{col.datoNoValido}</td>
                  <td>
                    <button className="staging-remove-btn" onClick={() => handleRemove(i)}>✕</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
