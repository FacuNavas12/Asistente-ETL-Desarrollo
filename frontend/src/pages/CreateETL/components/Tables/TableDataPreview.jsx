import { useState } from "react";
import "../etlForm.css";

export default function TableDataPreview({ table }) {
  const [open, setOpen] = useState(false);
  const cols    = table.columns ?? [];
  const maxRows = cols.length > 0 ? Math.max(...cols.map(c => c.data?.length ?? 0)) : 0;
  if (maxRows === 0) return null;

  return (
    <div className="origen-preview">
      <div className="origen-preview__header">
        <span className="origen-preview__name">{table.tableName}</span>
        <span className="origen-preview__meta">{cols.length} col · {maxRows} fil</span>
        <button className="origen-preview__toggle" onClick={() => setOpen(o => !o)}>
          {open ? "Ocultar tabla" : "Ver como tabla"}
        </button>
      </div>
      {open && (
        <div className="origen-preview__wrap">
          <table className="origen-preview__table">
            <thead>
              <tr>
                <th className="origen-preview__rn">#</th>
                {cols.map((c, i) => <th key={i}>{c.name}</th>)}
              </tr>
            </thead>
            <tbody>
              {Array.from({ length: maxRows }, (_, rowIdx) => (
                <tr key={rowIdx}>
                  <td className="origen-preview__rn">{rowIdx + 1}</td>
                  {cols.map((c, ci) => (
                    <td key={ci}>
                      {c.data?.[rowIdx] !== undefined
                        ? c.data[rowIdx]
                        : <span className="origen-preview__empty">-</span>}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
