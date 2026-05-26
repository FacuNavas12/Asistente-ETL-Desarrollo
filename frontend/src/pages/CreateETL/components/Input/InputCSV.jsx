import { useRef, useState } from "react";
import { csvToTables } from "../../utils/csvToTables";

export default function OrigenInputCSV({ onChange, onSwitchMode }) {
  const inputRef = useRef();
  const [status, setStatus] = useState(null); // null | "loading" | { tables } | "error"
  const [error, setError]   = useState("");

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setStatus("loading");
    setError("");
    try {
      const tables = await csvToTables(file);
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
            Seleccione un archivo <strong>.csv</strong>. La primera fila debe ser el encabezado de columnas.
            Cada columna se carga como campo de la tabla con todos sus valores.
          </p>
          <button
            className="origen-file-btn"
            onClick={() => inputRef.current?.click()}
            disabled={status === "loading"}
          >
            {status === "loading" ? "Procesando" : "Seleccionar archivo CSV"}
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".csv,text/csv"
            style={{ display: "none" }}
            onChange={handleFile}
          />
          {error && <p className="origen-file-zone__error">{error}</p>}
        </>
      ) : (
        <div className="origen-file-loaded">
          <span className="origen-file-loaded__icon">✓</span>
          <div className="origen-file-loaded__info">
            <strong>
              {status.tables.length} tabla{status.tables.length !== 1 ? "s" : ""} cargada{status.tables.length !== 1 ? "s" : ""}
            </strong>
            <span>{totalCols} columna{totalCols !== 1 ? "s" : ""} en total</span>
            <ul className="origen-file-loaded__list">
              {status.tables.map((t) => (
                <li key={t.tableName}>
                  <strong>{t.tableName}</strong> - {t.columns.length} col.
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


