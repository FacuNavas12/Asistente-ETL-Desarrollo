import { useState } from "react";
import "../../css/tableDataPreview.css";

function RoleBadge({ role }) {
  if (role === "PK") return <span className="origen-schema__badge origen-schema__badge--pk">PK</span>;
  if (role === "FK") return <span className="origen-schema__badge origen-schema__badge--fk">FK</span>;
  if (role === "clave natural") return <span className="origen-schema__badge origen-schema__badge--nk">NK</span>;
  return null;
}

export default function TableDataPreview({ table, forceOpen = false, onRemove = null }) {
  const [open, setOpen] = useState(forceOpen);
  const cols = table.columns ?? [];

  if (!cols.length && !onRemove) return null;

  const fieldMap = Object.fromEntries(
    (table.canonical_schema?.fields ?? []).map(f => [f.name, f])
  );

  return (
    <div className="origen-preview">
      <div className="origen-preview__header">
        <span className="origen-preview__name">{table.tableName}</span>
        <span className="origen-preview__meta">{cols.length} col</span>
        {cols.length > 0 && (
          <button className="origen-preview__toggle" onClick={() => setOpen(o => !o)}>
            {open ? "Ocultar" : "Ver columnas"}
          </button>
        )}
        {onRemove && (
          <button className="staging-remove-btn" onClick={onRemove}>✕</button>
        )}
      </div>

      {open && cols.length > 0 && (
        <div className="origen-preview__wrap">
          <table className="origen-preview__table">
            <thead>
              <tr>
                <th className="origen-preview__rn">#</th>
                <th>Columna</th>
                <th>Tipo</th>
                <th>Rol</th>
              </tr>
            </thead>
            <tbody>
              {cols.map((col, i) => {
                const originalType = fieldMap[col.name]?.original_type;
                const typeLabel = col.dataType + (col.dataFormat ? ` · ${col.dataFormat}` : "");
                return (
                  <tr key={i}>
                    <td className="origen-preview__rn">{i + 1}</td>
                    <td className="origen-schema__colname">{col.name}</td>
                    <td>
                      <span className="origen-schema__type">{typeLabel}</span>
                      {originalType && (
                        <span className="origen-schema__original">{originalType}</span>
                      )}
                    </td>
                    <td><RoleBadge role={col.role} /></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
