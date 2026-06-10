import { useState } from "react";
import { parseDDL, canonicalSchemaToTablaOrigen } from "@/api/schema";
import TableConfirmPanel from "../Tables/TableConfirmPanel";
import "../../css/shared.css";
import "../../css/inputOrigin.css";
import "../../css/tableConfirmPanel.css";

const DIALECTS = [
  { value: "ansi",     label: "SQL estándar (ANSI)" },
  { value: "postgres", label: "PostgreSQL" },
  { value: "tsql",     label: "SQL Server (T-SQL)" },
  { value: "mysql",    label: "MySQL" },
];

const PLACEHOLDER = `-- Pegá uno o más CREATE TABLE aquí
CREATE TABLE public.clientes (
    id         SERIAL PRIMARY KEY,
    nombre     VARCHAR(100) NOT NULL,
    email      VARCHAR(200),
    created_at DATE
);

CREATE TABLE public.pedidos (
    id          SERIAL PRIMARY KEY,
    cliente_id  INTEGER NOT NULL REFERENCES public.clientes(id),
    monto       DECIMAL(10,2),
    estado      VARCHAR(20)
);`;

export default function InputDDL({ value = [], onChange }) {
  const [ddl, setDdl]         = useState("");
  const [dialect, setDialect] = useState("ansi");
  const [candidates, setCandidates] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState("");

  const handleParse = async () => {
    if (!ddl.trim()) return;
    setLoading(true);
    setError("");
    try {
      const schemas = await parseDDL(ddl, dialect);
      const tables = schemas.map(s => canonicalSchemaToTablaOrigen(s));
      setCandidates(tables);
    } catch (err) {
      setError(err.message ?? "Error al parsear el DDL");
    } finally {
      setLoading(false);
    }
  };

  const handleReset = () => {
    setCandidates(null);
    setDdl("");
    setError("");
    onChange([]);
  };

  return (
    <div className="origen-file-zone">
      {!candidates ? (
        <>
          <p className="origen-file-zone__hint">
            Pegá uno o más <strong>CREATE TABLE</strong>. El servidor extrae tipos,
            PK y FK directamente del DDL — sin acceder a la base de datos.
            Los tipos no reconocidos se marcan como <em>unknown</em>.
          </p>

          <div className="form-grid form-grid--mb" style={{ marginBottom: "8px" }}>
            <div className="form-field">
              <label>Dialecto SQL</label>
              <select value={dialect} onChange={e => setDialect(e.target.value)}>
                {DIALECTS.map(d => (
                  <option key={d.value} value={d.value}>{d.label}</option>
                ))}
              </select>
            </div>
          </div>

          <textarea
            className="ddl-textarea"
            value={ddl}
            onChange={e => setDdl(e.target.value)}
            placeholder={PLACEHOLDER}
            rows={14}
            spellCheck={false}
          />

          {error && <p className="origen-file-zone__error">{error}</p>}

          <button
            className="staging-add-btn"
            onClick={handleParse}
            disabled={loading || !ddl.trim()}
            style={{ marginTop: "8px" }}
          >
            {loading ? "Parseando..." : "Parsear DDL"}
          </button>
        </>
      ) : (
        <>
          <p className="tpc-catalog-header">
            {candidates.length} tabla{candidates.length !== 1 ? "s" : ""} detectada{candidates.length !== 1 ? "s" : ""}
            <span className="conn-catalog-hint">
              — confirmar para usar en la Transformación.
            </span>
          </p>

          {/* Badge: UNKNOWN types warning */}
          {candidates.some(t =>
            (t.canonical_schema?.fields ?? []).some(f => f.type === "unknown")
          ) && (
            <p className="origen-file-zone__error" style={{ marginBottom: "8px" }}>
              Algunas columnas tienen tipo <strong>unknown</strong> (tipo SQL no reconocido).
              Revisalas en el formulario antes de continuar.
            </p>
          )}

          {/* FK summary */}
          {candidates.some(t => (t.canonical_schema?.foreign_keys ?? []).length > 0) && (
            <p className="conn-catalog-hint" style={{ marginBottom: "8px" }}>
              Se detectaron relaciones FK — visibles en la vista de esquema.
            </p>
          )}

          <TableConfirmPanel
            candidates={candidates}
            value={value}
            onChange={onChange}
          />

          <button
            className="staging-remove-btn origen-cancel-btn"
            onClick={handleReset}
            style={{ marginTop: "12px" }}
          >
            Editar DDL
          </button>
        </>
      )}
    </div>
  );
}
