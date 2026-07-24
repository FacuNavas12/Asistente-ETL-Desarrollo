import { useState } from "react";
import TableDataPreview from "./TableDataPreview";
import "../../css/shared.css";
import "../../css/tableConfirmPanel.css";

/**
 * Hook compartido para confirmar y quitar tablas de la lista del ETL.
 * Todos los inputs (Connection, CSV, Excel, Formulario) lo usan.
 */
export function useTableConfirmation({ value = [], onChange }) {
  const confirmedNames = new Set((value || []).map(t => t.tableName));

  const confirm = (tableObj) => {
    const rest = (value || []).filter(t => t.tableName !== tableObj.tableName);
    onChange([...rest, tableObj]);
  };

  const remove = (tableName) => {
    onChange((value || []).filter(t => t.tableName !== tableName));
  };

  return { confirmedNames, confirm, remove };
}

// ── Fila individual de la tabla de candidatos ─────────────────────────────

function CandidateRow({
  candidate, index, confirmed,
  isConfirming, anyConfirming,
  onConfirm, onRemove, onSelectTable, isSelected,
}) {
  const [previewOpen, setPreviewOpen] = useState(false);
  const isObj    = candidate !== null && typeof candidate === "object";
  const name     = isObj ? candidate.tableName : candidate;
  const hasCols  = isObj && (candidate.columns || []).length > 0;
  const clickable = !!onSelectTable || hasCols;

  const handleNameClick = () => {
    if (onSelectTable) {
      onSelectTable(name);
    } else if (hasCols) {
      setPreviewOpen(o => !o);
    }
  };

  return (
    <>
      <tr className={isSelected ? "tpc-row--selected" : undefined}>
        <td className="tpc-row-num">{index + 1}</td>
        <td
          className={clickable ? "tpc-row-name tpc-row-name--clickable" : "tpc-row-name"}
          onClick={clickable ? handleNameClick : undefined}
        >
          {name}
          {confirmed && <span className="tpc-confirmed-badge">✓ confirmada</span>}
        </td>
        <td className="tpc-row-action">
          {confirmed ? (
            <button className="staging-remove-btn" onClick={() => onRemove(name)}>
              Quitar
            </button>
          ) : (
            <button
              className="staging-add-btn tpc-confirm-btn"
              onClick={() => onConfirm(name, isObj ? candidate : null)}
              disabled={anyConfirming}
            >
              {isConfirming ? "Cargando..." : "Confirmar"}
            </button>
          )}
        </td>
      </tr>
      {previewOpen && hasCols && (
        <tr>
          <td colSpan={3} className="tpc-preview-cell">
            <TableDataPreview table={candidate} forceOpen />
          </td>
        </tr>
      )}
    </>
  );
}

// ── Componente principal ──────────────────────────────────────────────────

/**
 * Panel compartido de candidatos con preview y confirmación.
 *
 * Props:
 *   candidates      — Array<string | tableObj>  tablas disponibles a confirmar
 *   value           — tableObj[]                tablas ya confirmadas (ETL context)
 *   onChange        — (tables) => void
 *   onConfirm       — (name) => void  override async (Connection)
 *   confirmingTable — string | null   nombre de tabla en carga async
 *   confirmError    — string
 *   onSelectTable   — (name) => void  para preview externo (Connection DB rows)
 *   selectedTable   — string | null   nombre destacado
 *   children        — JSX             contenido extra debajo de la tabla (Connection: panel de filas DB)
 */
export default function TableConfirmPanel({
  candidates = [],
  value = [],
  onChange,
  onConfirm,
  confirmingTable = null,
  confirmError = "",
  onSelectTable,
  selectedTable = null,
  children,
}) {
  const { confirmedNames, confirm, remove } = useTableConfirmation({ value, onChange });
  const [query, setQuery] = useState("");

  const handleConfirm = (name, candidateObj) => {
    if (onConfirm) {
      onConfirm(name);
    } else if (candidateObj) {
      confirm(candidateObj);
    }
  };

  if (!candidates.length) return null;

  const nameOf = (candidate) =>
    typeof candidate === "object" ? candidate.tableName : candidate;

  // Filtramos por nombre pero conservamos el índice original (el "#" refleja la
  // posición real en la lista completa, no la posición dentro del filtro).
  const q = query.trim().toLowerCase();
  const filtered = candidates
    .map((candidate, i) => ({ candidate, i }))
    .filter(({ candidate }) => !q || nameOf(candidate).toLowerCase().includes(q));

  const confirmedCount = candidates.reduce(
    (acc, c) => acc + (confirmedNames.has(nameOf(c)) ? 1 : 0),
    0,
  );

  return (
    <div className="tpc">
      {confirmError && <p className="tpc-error">{confirmError}</p>}

      <div className="tpc-toolbar">
        <div className="tpc-search-wrap">
          <span className="tpc-search-icon" aria-hidden="true">🔍</span>
          <input
            type="text"
            className="tpc-search"
            placeholder="Buscar tabla..."
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
          {query && (
            <button
              className="tpc-search-clear"
              onClick={() => setQuery("")}
              title="Limpiar búsqueda"
              aria-label="Limpiar búsqueda"
            >
              ×
            </button>
          )}
        </div>
        <span className="tpc-counter">
          {confirmedCount} de {candidates.length} confirmadas
        </span>
      </div>

      <div className="staging-table-wrapper tpc-scroll">
        <table className="staging-table">
          <thead>
            <tr>
              <th>#</th>
              <th>Tabla</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={3} className="tpc-no-results">
                  Sin resultados para “{query}”
                </td>
              </tr>
            ) : (
              filtered.map(({ candidate, i }) => {
                const name = nameOf(candidate);
                return (
                  <CandidateRow
                    key={name}
                    candidate={candidate}
                    index={i}
                    confirmed={confirmedNames.has(name)}
                    isConfirming={confirmingTable === name}
                    anyConfirming={!!confirmingTable}
                    onConfirm={handleConfirm}
                    onRemove={remove}
                    onSelectTable={onSelectTable}
                    isSelected={selectedTable === name}
                  />
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {children}
    </div>
  );
}
