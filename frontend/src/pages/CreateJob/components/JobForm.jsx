import { useRef, useState } from "react";

function KtrDropZone({ files, onAdd, onRemove }) {
  const inputRef = useRef(null);
  const [dragging, setDragging] = useState(false);

  const filterKtr = (fileList) =>
    Array.from(fileList).filter((f) => f.name.toLowerCase().endsWith(".ktr"));

  const handleDrop = (e) => {
    e.preventDefault();
    setDragging(false);
    const valid = filterKtr(e.dataTransfer.files);
    if (valid.length) onAdd(valid);
  };

  const handleChange = (e) => {
    const valid = filterKtr(e.target.files);
    if (valid.length) onAdd(valid);
    e.target.value = "";
  };

  const openPicker = () => inputRef.current?.click();

  return (
    <div
      className={`job-dropzone ${dragging ? "job-dropzone--active" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
      onDragLeave={() => setDragging(false)}
      onDrop={handleDrop}
      onClick={files.length === 0 ? openPicker : undefined}
    >
      <input
        ref={inputRef}
        type="file"
        accept=".ktr"
        multiple
        style={{ display: "none" }}
        onChange={handleChange}
      />

      {files.length === 0 ? (
        <div className="job-dropzone__placeholder">
          <span className="job-dropzone__placeholder-icon">📂</span>
          <span className="job-dropzone__placeholder-main">
            Arrastrá tus archivos .ktr aquí
          </span>
          <span className="job-dropzone__placeholder-sub">
            o hacé click para seleccionarlos
          </span>
        </div>
      ) : (
        <div
          className="job-dropzone__list"
          onClick={(e) => e.stopPropagation()}
        >
          {files.map((f, i) => (
            <div key={i} className="job-dropzone__file">
              <span>
                <span>📄</span>
                {f.name}
              </span>
              <button
                className="job-dropzone__file-remove"
                onClick={() => onRemove(i)}
                title="Quitar archivo"
              >
                ✕
              </button>
            </div>
          ))}
          <button className="job-dropzone__add-btn" onClick={openPicker}>
            + Agregar más archivos
          </button>
        </div>
      )}
    </div>
  );
}

export default function JobForm({
  ktrFiles,
  onKtrAdd,
  onKtrRemove,
  jobDescription,
  onJobDescription,
  businessRules,
  onBusinessRules,
  onSubmit,
  onLimpiar,
  dirty,
}) {
  return (
    <div className="job-body">
      <div className="job-form-fields" style={{ display: "flex", flexDirection: "column", gap: "20px", maxWidth: "760px" }}>
        <div className="job-field">
          <label className="job-field-label">
            Archivos de transformación (.ktr)
          </label>
          <KtrDropZone
            files={ktrFiles}
            onAdd={onKtrAdd}
            onRemove={onKtrRemove}
          />
        </div>

        <div className="job-field">
          <label className="job-field-label">
            Descripción del job
            <span>¿Qué debe hacer este job y en qué orden?</span>
          </label>
          <textarea
            className="job-textarea"
            value={jobDescription}
            onChange={(e) => onJobDescription(e.target.value)}
            placeholder='Ej: "Primero cargar clientes a STG, luego ventas, y finalmente consolidar todo en el DWH"'
          />
        </div>

        <div className="job-field">
          <label className="job-field-label">
            Reglas adicionales
            <span>(opcional)</span>
          </label>
          <textarea
            className="job-textarea"
            value={businessRules}
            onChange={(e) => onBusinessRules(e.target.value)}
            placeholder='Ej: "Si falla la carga de clientes, no continuar con las demás transformaciones"'
            style={{ minHeight: "68px" }}
          />
        </div>

        <button
          className="job-submit-btn"
          onClick={onSubmit}
          disabled={ktrFiles.length === 0 || !jobDescription.trim()}
        >
          Analizar Job
        </button>
      </div>
    </div>
  );
}
