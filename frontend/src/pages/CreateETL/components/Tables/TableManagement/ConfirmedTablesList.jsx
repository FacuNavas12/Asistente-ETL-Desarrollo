import TableDataPreview from "../TableDataPreview";
import TablesPopupButton from "../TablesPopup";
import { tableKey } from "../tableUtils";
import "../../../css/shared.css";
import "../../../css/inputOrigin.css";

export default function ConfirmedTablesList({ tables = [], onChange }) {
  if (!tables.length) return null;

  const handleRemove = (key) => {
    onChange(tables.filter(t => tableKey(t) !== key));
  };

  return (
    <div className="origen-previews">
      <div className="origen-previews__header">
        <p className="origen-previews__label">Tablas confirmadas</p>
        <TablesPopupButton tables={tables} />
      </div>
      {tables.map((t, i) => (
        <TableDataPreview
          key={i}
          table={t}
          onRemove={() => handleRemove(tableKey(t))}
        />
      ))}
    </div>
  );
}
