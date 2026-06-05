import TablesPopupWindow from "./TablesPopupWindow";
import "../../../css/tableDataPreview.css";

export default function TablesPopupButton({ tables }) {
  if (!tables?.length) return null;

  return (
    <TablesPopupWindow tables={tables}>
      {(handleOpen) => (
        <button className="origen-preview__toggle" onClick={handleOpen}>
          Ver tablas en ventana ↗
        </button>
      )}
    </TablesPopupWindow>
  );
}
