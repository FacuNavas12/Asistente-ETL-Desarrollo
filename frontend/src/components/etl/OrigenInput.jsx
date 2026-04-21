import "../../css/etlForm.css";

export default function OrigenInput() {
  return (
    <div className="form-section">
      <h2 className="form-section__title">Origen del archivo</h2>

      <div className="dropzone">
        <p>Arrastrá un archivo aquí o hacé clic para seleccionar</p>
      </div>
    </div>
  );
}