import "../../css/etlForm.css";

export default function StagingForm() {
  return (
    <div className="form-section">
      <h2 className="form-section__title">Configuración de Staging</h2>

      <div className="form-grid">
        <div className="form-field">
          <label>Nombre del campo</label>
          <input type="text" placeholder="Ej: Nombre" />
        </div>

        <div className="form-field">
          <label>Tipo de dato esperado</label>
          <select>
            <option>Texto</option>
            <option>Número</option>
            <option>Fecha</option>
            <option>Booleano</option>
          </select>
        </div>

        <div className="form-field">
          <label>Reglas de limpieza</label>
          <select>
            <option>MAYÚSCULAS</option>
            <option>minúsculas</option>
            <option>Title Case</option>
            <option>Eliminar espacios extras</option>
            <option>Eliminar caracteres especiales</option>
            <option>Reemplazar valores según diccionario</option>
          </select>
        </div>

        <div className="form-field">
          <label>Dato no válido</label>
          <select>
            <option>Reemplazar por NULL</option>
          </select>
        </div>

        <div className="form-field">
          <label>Nombre de tabla Staging</label>
          <input type="text" placeholder="Ej: STG_ESTUDIANTES" />
        </div>
      </div>
    </div>
  );
}