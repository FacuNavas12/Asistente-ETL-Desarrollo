import "../../css/shared.css";

export default function ReglasNegocio({ value, onChange }) {
  return (
    <div className="form-section">
      <h2 className="form-section__title">Reglas de negocio</h2>

      <div className="form-field">
        <textarea
          className="origen-textarea"
          placeholder="Describa las reglas de negocio a considerar: validaciones, criterios de transformación, condiciones especiales, etc."
          rows={5}
          value={value}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    </div>
  );
}


