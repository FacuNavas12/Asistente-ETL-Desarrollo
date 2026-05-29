import { useRef, useState } from "react";
import { csvToTables } from "../../utils/csvToTables";
import TableConfirmPanel from "../Tables/TableConfirmPanel";
import "../../css/shared.css";
import "../../css/inputOrigin.css";
import "../../css/inputConnection.css";
import "../../css/tableConfirmPanel.css";

export default function OrigenInputCSV({ value = [], onChange, onSwitchMode }) {
  const inputRef = useRef();
  const [candidates, setCandidates] = useState(null);
  const [loading, setLoading]       = useState(false);
  const [error, setError]           = useState("");

  const handleFile = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setLoading(true);
    setError("");
    try {
      const tables = await csvToTables(file);
      setCandidates(tables);
    } catch (err) {
      setError(err.message ?? "Error al procesar el archivo");
    } finally {
      setLoading(false);
    }
    e.target.value = "";
  };

  const handleReset = () => {
    setCandidates(null);
    onChange([]);
  };

  const handleEditInForm = () => {
    if (candidates) {
      const confirmedNames = new Set((value || []).map(t => t.tableName));
      const toAdd = candidates.filter(t => !confirmedNames.has(t.tableName));
      if (toAdd.length > 0) onChange([...(value || []), ...toAdd]);
    }
    onSwitchMode?.("formulario");
  };

  return (
    <div className="origen-file-zone">
      {!candidates ? (
        <>
          <p className="origen-file-zone__hint">
            Seleccione un archivo <strong>.csv</strong>. La primera fila debe ser el encabezado de columnas.
            Cada columna se carga como campo de la tabla con todos sus valores.
          </p>
          <button
            className="origen-file-btn"
            onClick={() => inputRef.current?.click()}
            disabled={loading}
          >
            {loading ? "Procesando..." : "Seleccionar archivo CSV"}
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
        <>
          <p className="tpc-catalog-header">
            {candidates.length} tabla{candidates.length !== 1 ? "s" : ""} detectada{candidates.length !== 1 ? "s" : ""}
            <span className="conn-catalog-hint">
              — clic en el nombre para previsualizar · confirmar para usar en el ETL
            </span>
          </p>
          <TableConfirmPanel
            candidates={candidates}
            value={value}
            onChange={onChange}
          />
          <div className="origen-file-loaded__actions" style={{ marginTop: "12px" }}>
            <button className="staging-add-btn" onClick={handleEditInForm}>
              Editar en formulario
            </button>
            <button
              className="staging-remove-btn origen-cancel-btn"
              onClick={handleReset}
            >
              Cargar otro
            </button>
          </div>
        </>
      )}
    </div>
  );
}
