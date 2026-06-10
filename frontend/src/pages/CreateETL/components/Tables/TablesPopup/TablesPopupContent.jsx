import TableDataPreview from "../TableDataPreview";
import "./tablesPopup.css";

export default function TablesPopupContent({ tables }) {
  if (!tables?.length) return null;

  return (
    <div className="popup-window-root">
      <h2 className="popup-window-title">Tablas de origen</h2>
      <div className="popup-window-list">
        {tables.map((t) => (
          <TableDataPreview key={t.tableName} table={t} forceOpen={true} />
        ))}
      </div>
    </div>
  );
}
