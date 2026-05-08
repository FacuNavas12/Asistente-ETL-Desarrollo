import { useState } from "react";
import "../../css/etlForm.css";
import { useTableEditor } from "./tableUtils";

const ORIGEN_TYPE_MAP = {
  string: "Texto", int: "Número", float: "Número", bool: "Booleano", date: "Fecha",
};

const REGLAS_OPCIONES = [
  "MAYÚSCULAS", "minúsculas", "Title Case",
  "Eliminar espacios extras", "Eliminar caracteres especiales",
  "Reemplazar según diccionario", "Trim", "Normalizar tildes",
];

const DATO_INVALIDO_OPTS  = ["Reemplazar por NULL", "Eliminar fila", "Usar valor por defecto"];
const ESTRATEGIA_OPTS     = ["keep_first", "keep_last", "keep_most_complete"];
const POLITICA_ERROR_OPTS = ["reject", "quarantine", "default_values"];

const EMPTY_REGLAS_TABLA = {
  filtros: [],
  claveDeduplicacion: { columnas: [], estrategia: "keep_first" },
  politicaError: "reject",
};

const EMPTY_TABLE = {
  tableName: "",
  origenVinculado: "",
  columns: [],
  reglasTabla: { filtros: [], claveDeduplicacion: { columnas: [], estrategia: "keep_first" }, politicaError: "reject" },
  metadata: { sourceSystem: "" },
};

const makeCol = (nombre, tipo = "Texto") => ({
  nombre, tipo, reglas: [], datoNoValido: "Reemplazar por NULL",
});

// value: [{ tableName, origenVinculado, columns, reglasTabla, metadata }]
// origenTables: OrigenInput value
export default function StagingForm({ value, onChange, origenTables = [] }) {
  const tables = Array.isArray(value) ? value : [];

  const ed = useTableEditor({
    emptyTable: EMPTY_TABLE,
    emptyCol:   makeCol(""),
    tables,
    setTables:  onChange,
    columnsKey: "columns",
  });

  const [editingColIdx,  setEditingColIdx]  = useState(null);
  const [selectedRegla,  setSelectedRegla]  = useState(REGLAS_OPCIONES[0]);
  const [currentFiltro,  setCurrentFiltro]  = useState("");
  const [currentDedupCol, setCurrentDedupCol] = useState("");

  const ct   = ed.currentTable;
  const rt   = ct.reglasTabla ?? { ...EMPTY_REGLAS_TABLA, claveDeduplicacion: { columnas: [], estrategia: "keep_first" } };
  const meta = ct.metadata ?? { sourceSystem: "" };

  // ── Origen selection: auto-populate columns ──────────────────────────────
  const handleOrigenChange = (tableName) => {
    const ot = origenTables.find(t => t.tableName === tableName);
    const columns = ot
      ? ot.columns.map(c => makeCol(c.name, ORIGEN_TYPE_MAP[c.dataType] ?? "Texto"))
      : [];
    ed.setCurrentTable(t => ({
      ...t,
      origenVinculado: tableName,
      columns,
      metadata: { ...t.metadata, sourceSystem: "" },
    }));
    setEditingColIdx(null);
  };

  // ── Column inline edit ───────────────────────────────────────────────────
  const toggleEditCol = (i) => {
    if (editingColIdx === i) {
      setEditingColIdx(null);
    } else {
      setEditingColIdx(i);
      setSelectedRegla(REGLAS_OPCIONES[0]);
    }
  };

  const updateCol = (i, updater) => {
    ed.setCurrentTable(t => ({
      ...t,
      columns: t.columns.map((c, idx) => idx === i ? updater(c) : c),
    }));
  };

  const addRegla = (colIdx) => {
    if (!selectedRegla) return;
    updateCol(colIdx, c => {
      const reglas = Array.isArray(c.reglas) ? c.reglas : [];
      if (reglas.includes(selectedRegla)) return c;
      return { ...c, reglas: [...reglas, selectedRegla] };
    });
  };

  const removeRegla = (colIdx, reglaIdx) => {
    updateCol(colIdx, c => ({
      ...c,
      reglas: (Array.isArray(c.reglas) ? c.reglas : []).filter((_, ri) => ri !== reglaIdx),
    }));
  };

  // ── Reglas de tabla ──────────────────────────────────────────────────────
  const setRT = (updater) => {
    ed.setCurrentTable(t => ({
      ...t,
      reglasTabla: updater(t.reglasTabla ?? { ...EMPTY_REGLAS_TABLA, claveDeduplicacion: { columnas: [], estrategia: "keep_first" } }),
    }));
  };

  const addFiltro = () => {
    if (!currentFiltro.trim()) return;
    setRT(r => ({ ...r, filtros: [...r.filtros, currentFiltro.trim()] }));
    setCurrentFiltro("");
  };

  const removeFiltro = (i) => setRT(r => ({ ...r, filtros: r.filtros.filter((_, idx) => idx !== i) }));

  const addDedupCol = () => {
    if (!currentDedupCol) return;
    setRT(r => ({
      ...r,
      claveDeduplicacion: {
        ...r.claveDeduplicacion,
        columnas: [...r.claveDeduplicacion.columnas, currentDedupCol],
      },
    }));
    setCurrentDedupCol("");
  };

  const removeDedupCol = (i) => setRT(r => ({
    ...r,
    claveDeduplicacion: {
      ...r.claveDeduplicacion,
      columnas: r.claveDeduplicacion.columnas.filter((_, idx) => idx !== i),
    },
  }));

  // ── Save: auto-append unconfigured origin columns ────────────────────────
  const handleSaveTable = () => {
    if (!ct.tableName.trim() || !ct.origenVinculado) return;
    const ot = origenTables.find(t => t.tableName === ct.origenVinculado);
    let finalCols = [...ct.columns];
    if (ot) {
      const existing = new Set(finalCols.map(c => c.nombre));
      const missing  = ot.columns
        .filter(c => !existing.has(c.name))
        .map(c => makeCol(c.name, ORIGEN_TYPE_MAP[c.dataType] ?? "Texto"));
      finalCols = [...finalCols, ...missing];
    }
    ed.saveTable(t => ({ ...t, columns: finalCols }));
    setEditingColIdx(null);
    setCurrentFiltro("");
    setCurrentDedupCol("");
  };

  const canAddTable   = ct.tableName.trim() && ct.origenVinculado;
  const dedupAvailable = ct.columns.filter(c => !rt.claveDeduplicacion.columnas.includes(c.nombre));

  return (
    <div className="form-section">
      <h2 className="form-section__title">Definición de tabla Staging</h2>

      <div className="dwh-table-panel">
        <p className="dwh-panel-label">
          {ed.editingIndex !== null ? "Editar tabla" : "Nueva tabla"}
        </p>

        {/* ── Nombre + origen ── */}
        <div className="staging-add-row">
          <div className="form-field" style={{ flex: "2 1 200px" }}>
            <label>Nombre de tabla Staging</label>
            <input
              type="text"
              placeholder="Ej: STG_CLIENTES"
              value={ct.tableName}
              onChange={(e) => ed.setCurrentTable(t => ({ ...t, tableName: e.target.value }))}
            />
          </div>
          <div className="form-field">
            <label>Tabla de origen</label>
            <select
              value={ct.origenVinculado}
              onChange={(e) => handleOrigenChange(e.target.value)}
            >
              <option value="">— Seleccionar —</option>
              {origenTables.map(t => (
                <option key={t.tableName} value={t.tableName}>{t.tableName}</option>
              ))}
            </select>
          </div>
        </div>

        {/* ── Lista de columnas ── */}
        {ct.columns.length > 0 && (
          <div className="stg-col-list">
            <p className="stg-section-label">Columnas</p>
            {ct.columns.map((col, i) => {
              const reglas = Array.isArray(col.reglas) ? col.reglas : [];
              return (
                <div key={i} className={`stg-col-item${editingColIdx === i ? " stg-col-item--editing" : ""}`}>
                  <div className="stg-col-item__header">
                    <span className="stg-col-item__name">{col.nombre}</span>
                    <span className="stg-tipo-badge">{col.tipo}</span>
                    <div className="stg-col-item__tags">
                      {reglas.map((r, ri) => (
                        <span key={ri} className="stg-regla-tag">{r}</span>
                      ))}
                    </div>
                    <span className="stg-dato-tag">{col.datoNoValido}</span>
                    <button className="staging-edit-btn" onClick={() => toggleEditCol(i)}>
                      {editingColIdx === i ? "▲" : "✎"}
                    </button>
                  </div>

                  {editingColIdx === i && (
                    <div className="stg-col-inline-edit">
                      <div className="staging-add-row">
                        <div className="form-field" style={{ flex: "2 1 200px" }}>
                          <label>Regla de limpieza</label>
                          <div className="origen-dato-input-row">
                            <select
                              value={selectedRegla}
                              onChange={(e) => setSelectedRegla(e.target.value)}
                            >
                              {REGLAS_OPCIONES.map(r => <option key={r}>{r}</option>)}
                            </select>
                            <button className="staging-add-btn" onClick={() => addRegla(i)}>+</button>
                          </div>
                          {reglas.length > 0 && (
                            <div className="origen-dato-tags" style={{ marginTop: 6 }}>
                              {reglas.map((r, ri) => (
                                <span key={ri} className="origen-dato-tag">
                                  {r}
                                  <button className="origen-dato-remove" onClick={() => removeRegla(i, ri)}>✕</button>
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                        <div className="form-field">
                          <label>Dato no válido</label>
                          <select
                            value={col.datoNoValido}
                            onChange={(e) => updateCol(i, c => ({ ...c, datoNoValido: e.target.value }))}
                          >
                            {DATO_INVALIDO_OPTS.map(d => <option key={d}>{d}</option>)}
                          </select>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}

        {/* ── Reglas de tabla ── */}
        <div className="stg-reglas-tabla">
          <p className="stg-section-label">Reglas de tabla</p>

          {/* Filtros */}
          <div className="stg-subsection">
            <label className="stg-subsection-label">Filtros (condiciones SQL)</label>
            <div className="origen-dato-input-row">
              <input
                type="text"
                placeholder="Ej: status != 'INACTIVO'"
                value={currentFiltro}
                onChange={(e) => setCurrentFiltro(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addFiltro(); } }}
              />
              <button className="staging-add-btn" onClick={addFiltro} disabled={!currentFiltro.trim()}>+</button>
            </div>
            {rt.filtros.length > 0 && (
              <div className="origen-dato-tags" style={{ marginTop: 6 }}>
                {rt.filtros.map((f, i) => (
                  <span key={i} className="origen-dato-tag">
                    {f}
                    <button className="origen-dato-remove" onClick={() => removeFiltro(i)}>✕</button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Clave de deduplicación */}
          <div className="stg-subsection">
            <label className="stg-subsection-label">Clave de deduplicación</label>
            <div className="staging-add-row" style={{ marginBottom: 0 }}>
              <div className="form-field" style={{ flex: "2 1 200px" }}>
                <label>Columnas</label>
                <div className="origen-dato-input-row">
                  <select
                    value={currentDedupCol}
                    onChange={(e) => setCurrentDedupCol(e.target.value)}
                    disabled={!dedupAvailable.length}
                  >
                    <option value="">— Seleccionar columna —</option>
                    {dedupAvailable.map(c => (
                      <option key={c.nombre} value={c.nombre}>{c.nombre}</option>
                    ))}
                  </select>
                  <button className="staging-add-btn" onClick={addDedupCol} disabled={!currentDedupCol}>+</button>
                </div>
                {rt.claveDeduplicacion.columnas.length > 0 && (
                  <div className="origen-dato-tags" style={{ marginTop: 6 }}>
                    {rt.claveDeduplicacion.columnas.map((col, i) => (
                      <span key={i} className="origen-dato-tag">
                        {col}
                        <button className="origen-dato-remove" onClick={() => removeDedupCol(i)}>✕</button>
                      </span>
                    ))}
                  </div>
                )}
              </div>
              <div className="form-field">
                <label>Estrategia</label>
                <select
                  value={rt.claveDeduplicacion.estrategia}
                  onChange={(e) => setRT(r => ({
                    ...r,
                    claveDeduplicacion: { ...r.claveDeduplicacion, estrategia: e.target.value },
                  }))}
                >
                  {ESTRATEGIA_OPTS.map(s => <option key={s}>{s}</option>)}
                </select>
              </div>
            </div>
          </div>

          {/* Política de error */}
          <div className="stg-subsection">
            <label className="stg-subsection-label">Política de error por defecto</label>
            <select
              value={rt.politicaError}
              onChange={(e) => setRT(r => ({ ...r, politicaError: e.target.value }))}
            >
              {POLITICA_ERROR_OPTS.map(p => <option key={p}>{p}</option>)}
            </select>
          </div>
        </div>

        {/* ── Metadatos inyectados ── */}
        <div className="stg-metadata-section">
          <p className="stg-section-label">Metadatos inyectados</p>
          <div className="stg-metadata-row">
            <div className="stg-meta-auto-item">
              <span className="stg-meta-auto-badge">AUTO</span>
              <span className="stg-meta-field-name">load_date</span>
              <span className="stg-meta-field-desc">Fecha y hora de carga</span>
            </div>
            <div className="stg-meta-auto-item">
              <span className="stg-meta-auto-badge">AUTO</span>
              <span className="stg-meta-field-name">batch_id</span>
              <span className="stg-meta-field-desc">ID de corrida · formato b_N</span>
            </div>
            <div className="stg-meta-source-item">
              <span className="stg-meta-field-name">source_system</span>
              <div className="form-field" style={{ flex: 1 }}>
                <input
                  type="text"
                  placeholder={ct.origenVinculado ? `${ct.origenVinculado}_ORIGEN` : "Seleccionar origen primero"}
                  value={meta.sourceSystem}
                  onChange={(e) => ed.setCurrentTable(t => ({
                    ...t,
                    metadata: { ...t.metadata, sourceSystem: e.target.value },
                  }))}
                  disabled={!ct.origenVinculado}
                />
                {ct.origenVinculado && !meta.sourceSystem && (
                  <span className="stg-meta-hint">Auto: {ct.origenVinculado}_ORIGEN</span>
                )}
              </div>
            </div>
          </div>
        </div>

        <button className="dwh-add-table-btn" onClick={handleSaveTable} disabled={!canAddTable}>
          {ed.editingIndex !== null ? "Guardar cambios" : "+ Agregar tabla"}
        </button>
      </div>

      {/* ── Tablas guardadas ── */}
      {tables.length > 0 && (
        <div className="dwh-tables-list">
          {tables.map((table, i) => (
            <div key={i} className="dwh-table-card">
              <div className="dwh-table-card__header">
                <span className="dwh-table-card__name">{table.tableName}</span>
                {table.origenVinculado && (
                  <span className="dwh-table-card__origen">← {table.origenVinculado}</span>
                )}
                <button className="staging-edit-btn" onClick={() => { ed.editTable(i); setEditingColIdx(null); }}>✎</button>
                <button className="staging-remove-btn" onClick={() => ed.removeAt(i)}>✕</button>
              </div>

              <div className="stg-saved-cols">
                {table.columns.map((col, j) => {
                  const reglas = Array.isArray(col.reglas) ? col.reglas : [];
                  return (
                    <div key={j} className="stg-saved-col">
                      <span className="stg-saved-col__name">{col.nombre}</span>
                      <span className="stg-tipo-badge stg-tipo-badge--sm">{col.tipo}</span>
                      {reglas.length > 0 && (
                        <div className="stg-saved-col__reglas">
                          {reglas.map((r, ri) => <span key={ri} className="stg-regla-tag">{r}</span>)}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>

              <div className="stg-saved-meta">
                <span className="stg-saved-meta-badge">load_date</span>
                <span className="stg-saved-meta-badge">batch_id</span>
                {(table.metadata?.sourceSystem || table.origenVinculado) && (
                  <span className="stg-saved-meta-badge stg-saved-meta-badge--source">
                    {table.metadata?.sourceSystem || `${table.origenVinculado}_ORIGEN`}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
