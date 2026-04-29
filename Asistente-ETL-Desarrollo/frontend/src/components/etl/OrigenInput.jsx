import "../../css/etlForm.css";

export default function OrigenInput({ value, onChange }) {
  return (
    <div className="form-section">
      <h2 className="form-section__title">Datos de origen</h2>

      <div className="form-field">
        <textarea
          className="origen-textarea"
          placeholder="Describí la fuente de datos: estructura de tablas, campos disponibles, sistema origen, etc."
          rows={5}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </div>
  );
}