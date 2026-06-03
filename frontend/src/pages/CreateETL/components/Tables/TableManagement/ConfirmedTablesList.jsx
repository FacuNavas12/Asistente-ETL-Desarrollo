import TableDataPreview from "../TableDataPreview";
import TablesPopupButton from "../TablesPopupButton";
import "../../../css/shared.css";
import "../../../css/inputOrigin.css";

export default function ConfirmedTablesList({ tables = [], onChange }) {
  if (!tables.length) return null;

  const handleRemove = (tableName) => {
    onChange(tables.filter(t => t.tableName !== tableName));
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
          onRemove={() => handleRemove(t.tableName)}
        />
      ))}
    </div>
  );
}
