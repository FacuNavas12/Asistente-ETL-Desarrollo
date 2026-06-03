import { useRef, useState } from "react";
import Papa from "papaparse";
import { inferSchema, canonicalSchemaToTablaOrigen } from "@/api/schema";
import TableConfirmPanel from "../Tables/TableConfirmPanel";
import "../../css/shared.css";
import "../../css/inputOrigin.css";
import "../../css/inputConnection.css";
import "../../css/tableConfirmPanel.css";

// PapaParse is kept for rendering the data preview only.
// Schema extraction (types, stats) is done by the backend via POST /api/schema/infer.
function parsePreview(file) {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: true,
      preview: 20,       // only first 20 rows for preview
      skipEmptyLines: true,
      complete: r  => resolve(r),
      error:    err => reject(new Error(err.message)),
    });
  });
}

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
      // 1. Backend infers schema + stats (authoritative, handles encoding/delimiters).
      const canonicalSchema = await inferSchema(file);
      const tabla = canonicalSchemaToTablaOrigen(canonicalSchema);

      // 2. PapaParse provides a lightweight preview for the UI (no schema inference).
      try {
        const preview = await parsePreview(file);
        if (preview.data?.length > 0) {
          tabla._previewRows = preview.data;   // UI-only, never sent to backend
        }
      } catch {
        // Preview failure is non-fatal — schema is already available.
      }

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
            Seleccione un archivo <strong>.csv</strong>. La primera fila debe ser el encabezado de columnas.
            El servidor detecta automáticamente el delimitador y la codificación.
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
          {/* Show inferred-by-sample badges */}
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
