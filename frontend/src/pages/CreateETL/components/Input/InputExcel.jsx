import { useRef, useState } from "react";
// default export returns Array<{ sheet: string, data: Row[] }> — all sheets at once.
// Named exports: readSheet, parseSheetData. NO readXlsxFile or readSheetNames named exports.
import readXlsxFileBrowser from "read-excel-file/browser";
import { inferSchema, canonicalSchemaToTablaOrigen } from "@/api/schema";
import TableConfirmPanel from "../Tables/TableConfirmPanel";
import "../../css/shared.css";
import "../../css/inputOrigin.css";
import "../../css/inputConnection.css";
import "../../css/tableConfirmPanel.css";

// Preview only (.xlsx). Schema inference stays in backend via POST /api/schema/infer.
async function parsePreview(file) {
  const sheetsData = await readXlsxFileBrowser(file);
  const sheets = {};
  for (const { sheet, data } of sheetsData) {
    sheets[sheet] = data.slice(0, 21).map(row =>
      row.map(cell => (cell === null ? "" : String(cell)))
    );
  }
  return sheets;
}

export default function OrigenInputExcel({ value = [], onChange }) {
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
      const canonicalSchema = await inferSchema(file);
      const tabla = canonicalSchemaToTablaOrigen(canonicalSchema);

      try {
        const sheets = await parsePreview(file);
        tabla._previewSheets = sheets;
      } catch {
        // Preview failure is non-fatal.
      }

      if (!tabla.columns.length) throw new Error("El archivo no contiene columnas detectables.");
      setCandidates([tabla]);
    } catch (err) {
      setError(err.message ?? "Error al procesar el archivo");
    } finally {
      setLoading(false);
    }
    e.target.value = "";
  };

  const handleReset = () => {
    setCandidates(null);
  };

  // handleEditInForm desactivado junto con botón "Editar en formulario" (modo formulario desconectado)
  // const handleEditInForm = () => {
  //   if (candidates) {
  //     const confirmedNames = new Set((value || []).map(t => t.tableName));
  //     const toAdd = candidates.filter(t => !confirmedNames.has(t.tableName));
  //     if (toAdd.length > 0) onChange([...(value || []), ...toAdd]);
  //   }
  //   onSwitchMode?.("formulario");
  // };

  return (
    <div className="origen-file-zone">
      {!candidates ? (
        <>
          <p className="origen-file-zone__hint">
            Seleccioná un archivo <strong>.xlsx</strong> o <strong>.xls</strong>.
            El servidor detecta automáticamente tipos de columnas y fechas seriales.
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
          {candidates.map(t => {
            const schema = t.canonical_schema;
            if (!schema) return null;
            const sampledFields = (schema.fields ?? []).filter(f => f.inferred_by === "frictionless");
            if (!sampledFields.length) return null;
            return (
              <p key={t.tableName} className="conn-catalog-hint" style={{ marginBottom: "6px" }}>
                Tipos inferidos por muestra ({sampledFields.length} columnas) — revisar antes de confirmar.
              </p>
            );
          })}
          <TableConfirmPanel
            candidates={candidates}
            value={value}
            onChange={onChange}
          />
          <div className="origen-file-loaded__actions" style={{ marginTop: "12px" }}>
            {/* botón desactivado: modo "formulario" desconectado como opción de origen
            <button className="staging-add-btn" onClick={handleEditInForm}>
              Editar en formulario
            </button>
            */}
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
