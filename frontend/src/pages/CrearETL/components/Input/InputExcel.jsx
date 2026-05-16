import { useRef, useState } from "react";
import { excelToTables } from "../../utils/excelToTables";

export default function OrigenInputExcel({ onChange, onSwitchMode }) {
  const inputRef = useRef();
  const [status, setStatus] = useState(null);
  const [error, setError]   = useState("");

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("loading");
    setError("");
    try {
      const tables = await excelToTables(file);
      if (tables.length === 0) throw new Error("El archivo no contiene hojas con datos.");
      onChange(tables);
      setStatus({ tables });
    } catch (err) {
      setError(err.message ?? "Error al procesar el archivo");
      setStatus("error");
    }
    e.target.value = "";
  };

  const totalCols = status?.tables
    ? status.tables.reduce((acc, t) => acc + t.columns.length, 0)
    : 0;

  return (
    <div className="origen-file-zone">
      {!status?.tables ? (
        <>
          <p className="origen-file-zone__hint">
            SeleccionÃ¡ un archivo <strong>.xlsx</strong> o <strong>.xls</strong>.
            Cada hoja del libro se convierte en una tabla. La primera fila de cada hoja debe ser el encabezado.
          </p>
          <button
            className="origen-file-btn"
            onClick={() => inputRef.current?.click()}
            disabled={status === "loading"}
          >
            {status === "loading" ? "Procesandoâ€¦" : "Seleccionar archivo Excel"}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".xlsx,.xls,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet,application/vnd.ms-excel"
            style={{ display: "none" }}
            onChange={handleFile}
          />
          {error && <p className="origen-file-zone__error">{error}</p>}
        </>
      ) : (
        <div className="origen-file-loaded">
          <span className="origen-file-loaded__icon">âœ“</span>
          <div className="origen-file-loaded__info">
            <strong>
              {status.tables.length} tabla{status.tables.length !== 1 ? "s" : ""} cargada{status.tables.length !== 1 ? "s" : ""}
            </strong>
            <span>{totalCols} columna{totalCols !== 1 ? "s" : ""} en total</span>
            <ul className="origen-file-loaded__list">
              {status.tables.map((t) => (
                <li key={t.tableName}>
                  <strong>{t.tableName}</strong> â€” {t.columns.length} col.
                </li>
              ))}
            </ul>
          </div>
          <div className="origen-file-loaded__actions">
            <button className="staging-add-btn" onClick={() => onSwitchMode("formulario")}>
              Editar en formulario
            </button>
            <button
              className="staging-remove-btn origen-cancel-btn"
              onClick={() => { setStatus(null); onChange([]); }}
            >
              Cargar otro
            </button>
          </div>
        </div>
      )}
    </div>
  );
}


