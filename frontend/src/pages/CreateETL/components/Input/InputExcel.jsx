import { useRef, useState } from "react";
import { excelToTables } from "../../utils/excelToTables";
import TableConfirmPanel from "../Tables/TableConfirmPanel";
import "../../css/shared.css";
import "../../css/inputOrigin.css";
import "../../css/inputConnection.css";
import "../../css/tableConfirmPanel.css";

export default function OrigenInputExcel({ value = [], onChange, onSwitchMode }) {
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
      const tables = await excelToTables(file);
      if (tables.length === 0) throw new Error("El archivo no contiene hojas con datos.");
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
            Seleccioná un archivo <strong>.xlsx</strong> o <strong>.xls</strong>.
            Cada hoja del libro se convierte en una tabla. La primera fila de cada hoja debe ser el encabezado.
          </p>
          <button
            className="origen-file-btn"
            onClick={() => inputRef.current?.click()}
            disabled={loading}
          >
            {loading ? "Procesando…" : "Seleccionar archivo Excel"}
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
