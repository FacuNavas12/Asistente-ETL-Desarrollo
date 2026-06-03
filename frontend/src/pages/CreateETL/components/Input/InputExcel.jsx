import { useRef, useState } from "react";
import * as XLSX from "xlsx";
import { inferSchema, canonicalSchemaToTablaOrigen } from "@/api/schema";
import TableConfirmPanel from "../Tables/TableConfirmPanel";
import "../../css/shared.css";
import "../../css/inputOrigin.css";
import "../../css/inputConnection.css";
import "../../css/tableConfirmPanel.css";

// XLSX is kept for rendering the data preview only (sheet names + row preview).
// Schema extraction (types, stats) is done by the backend via POST /api/schema/infer.
function parsePreview(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const wb  = XLSX.read(e.target.result, { type: "array" });
        const sheets = {};
        wb.SheetNames.forEach(name => {
          const rows = XLSX.utils.sheet_to_json(wb.Sheets[name], { header: 1, defval: "" });
          sheets[name] = rows.slice(0, 21);   // header + 20 rows max
        });
        resolve(sheets);
      } catch (err) {
        reject(new Error(err.message));
      }
    };
    reader.onerror = () => reject(new Error("Error al leer el archivo"));
    reader.readAsArrayBuffer(file);
  });
}

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
      // 1. Backend infers schema + stats for the whole workbook.
      //    /infer returns a single CanonicalSchema (first sheet or merged).
      //    For multi-sheet workbooks this creates one candidate per call.
      const canonicalSchema = await inferSchema(file);
      const tabla = canonicalSchemaToTablaOrigen(canonicalSchema);

      // 2. XLSX provides a lightweight preview for the UI (no schema inference).
      try {
        const sheets = await parsePreview(file);
        tabla._previewSheets = sheets;   // UI-only, never sent to backend
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
