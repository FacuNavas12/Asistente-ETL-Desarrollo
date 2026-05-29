import "../../css/shared.css";

export default function DescripcionObjetivo({ value, onChange }) {
  return (
    <div className="form-section">
      <h2 className="form-section__title">Objetivo del proceso ETL</h2>

      <div className="form-field">
        <textarea
          className="origen-textarea"
          placeholder="Describí qué querés lograr: fuentes de datos, transformaciones esperadas, destino final, casos de uso, etc. Cuanto más detallado, mejor será el proceso generado."
          rows={4}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </div>
  );
}
