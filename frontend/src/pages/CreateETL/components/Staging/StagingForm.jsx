import { useState } from "react";
import "../../css/shared.css";
import "../../css/inputOrigin.css";
import "../../css/stagingForm.css";
import { useTableEditor, TablePanel, SaveTableButton, TableCardHeader, SavedTablesList } from "../Tables/tableUtils";
import { EMPTY_METADATA } from "./stagingMetadata";
import { StagingMetadataSection, StagingMetaBadges } from "./StagingMetadataSection";
import { formatStagingName } from "../../validation/stringCleaners";

const ORIGEN_TYPE_MAP = {
  string: "Texto", int: "Int", float: "Float", bool: "Booleano", date: "Fecha",
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
  reglasTabla: { ...EMPTY_REGLAS_TABLA, claveDeduplicacion: { columnas: [], estrategia: "keep_first" } },
  metadata: { ...EMPTY_METADATA },
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

  const [editingColIdx,   setEditingColIdx]   = useState(null);
  const [selectedRegla,   setSelectedRegla]   = useState(REGLAS_OPCIONES[0]);
  const [currentFiltro,   setCurrentFiltro]   = useState("");
  const [currentDedupCol, setCurrentDedupCol] = useState("");

  const ct   = ed.currentTable;
  const rt   = ct.reglasTabla ?? { ...EMPTY_REGLAS_TABLA, claveDeduplicacion: { columnas: [], estrategia: "keep_first" } };
  const meta = ct.metadata ?? { ...EMPTY_METADATA };

  const handleOrigenChange = (tableName) => {
    const ot = origenTables.find(t => t.tableName === tableName);
    const columns = ot
      ? ot.columns.map(c => makeCol(c.name, ORIGEN_TYPE_MAP[c.dataType] ?? "Texto"))
      : [];
    ed.setCurrentTable(t => ({
      ...t,
      origenVinculado: tableName,
      columns,
      metadata: { ...EMPTY_METADATA },
    }));
    setEditingColIdx(null);
  };

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
    //guardo y limpio el nombre de la tabla staging
    ed.saveTable(t => ({ ...t, columns: finalCols, tableName: formatStagingName(t.tableName) }));
    setEditingColIdx(null);
    setCurrentFiltro("");
    setCurrentDedupCol("");
  };

  const canAddTable    = ct.tableName.trim() && ct.origenVinculado;
  const dedupAvailable = ct.columns.filter(c => !rt.claveDeduplicacion.columnas.includes(c.nombre));

  return (
    <div className="form-section">
      <h2 className="form-section__title">Definición de tabla Staging</h2>

      <TablePanel editingIndex={ed.editingIndex}>

        {/* Nombre + origen  */}
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
              <option value="">Seleccionar</option>
              {origenTables.map(t => (
                <option key={t.tableName} value={t.tableName}>{t.tableName}</option>
              ))}
            </select>
          </div>
        </div>

        {/*  Lista de columnas  */}
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
                      {editingColIdx === i ? "â–²" : "âœŽ"}
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
                                  <button className="origen-dato-remove" onClick={() => removeRegla(i, ri)}>âœ•</button>
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

        {/* Reglas de tabla */}
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
                    <button className="origen-dato-remove" onClick={() => removeFiltro(i)}>âœ•</button>
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Clave de deduplicacion */}
          <div className="stg-subsection">
            <label className="stg-subsection-label">Clave de duplicación</label>
            <div className="staging-add-row" style={{ marginBottom: 0 }}>
              <div className="form-field" style={{ flex: "2 1 200px" }}>
                <label>Columnas</label>
                <div className="origen-dato-input-row">
                  <select
                    value={currentDedupCol}
                    onChange={(e) => setCurrentDedupCol(e.target.value)}
                    disabled={!dedupAvailable.length}
                  >
                    <option value="">- Seleccionar columna -</option>
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
                        <button className="origen-dato-remove" onClick={() => removeDedupCol(i)}>✓</button>
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

          {/* Poli­tica de error */}
          <div className="stg-subsection">
            <label className="stg-subsection-label">Polí­tica de error por defecto</label>
            <select
              value={rt.politicaError}
              onChange={(e) => setRT(r => ({ ...r, politicaError: e.target.value }))}
            >
              {POLITICA_ERROR_OPTS.map(p => <option key={p}>{p}</option>)}
            </select>
          </div>
        </div>


        {/* Metadatos inyectados */}
        <StagingMetadataSection
          meta={meta}
          origenVinculado={ct.origenVinculado}
          onChange={(sourceSystem) => ed.setCurrentTable(t => ({
            ...t,
            metadata: { ...t.metadata, sourceSystem },
          }))}
        />


        <SaveTableButton
          editingIndex={ed.editingIndex}
          onClick={handleSaveTable}
          disabled={!canAddTable}
        />
      </TablePanel>

      {/* Tablas guardadas */}
      <SavedTablesList
        tables={tables}
        renderCard={(table, i) => (
          <>
            <TableCardHeader
              name={table.tableName}
              origen={table.origenVinculado}
              onEdit={() => { ed.editTable(i); setEditingColIdx(null); }}
              onRemove={() => ed.removeAt(i)}
            />
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
            <StagingMetaBadges table={table} />
          </>
        )}
      />
    </div>
  );
}


