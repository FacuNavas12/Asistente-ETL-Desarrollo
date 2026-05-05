import { useState } from "react";
import "../../css/etlForm.css";
import { ColumnTable } from "./tableUtils";

const EMPTY_COLUMN = { nombre: "", tipo: "Texto", regla: "MAYÚSCULAS", datoNoValido: "Reemplazar por NULL" };

const STG_COL_DEFS = [
  { key: "nombre",       label: "Campo" },
  { key: "tipo",         label: "Tipo" },
  { key: "regla",        label: "Regla" },
  { key: "datoNoValido", label: "Dato no válido" },
];

export default function StagingForm({ value, onChange }) {
  const [current, setCurrent] = useState(EMPTY_COLUMN);

  const columns = value?.columns ?? [];

  const handleAdd = () => {
    if (!current.nombre.trim()) return;
    onChange({ ...value, columns: [...columns, current] });
    setCurrent(EMPTY_COLUMN);
  };

  const handleRemove = (i) => {
    onChange({ ...value, columns: columns.filter((_, idx) => idx !== i) });
  };

  return (
    <div className="form-section">
      <h2 className="form-section__title">Definición de tabla Staging</h2>

      <div className="form-field staging-table-name">
        <label>Nombre de tabla Staging</label>
        <input
          type="text"
          placeholder="Ej: STG_ESTUDIANTES"
          value={value?.tableName ?? ""}
          onChange={(e) => onChange({ ...value, tableName: e.target.value })}
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

      <ColumnTable columns={columns} columnDefs={STG_COL_DEFS} onRemove={handleRemove} />
    </div>
  );
}
