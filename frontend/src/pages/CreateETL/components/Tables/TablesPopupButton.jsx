import { useState, useRef } from "react";
import { createPortal } from "react-dom";
import "../etlForm.css";

function collectCSS() {
  let css = "";
  for (const sheet of document.styleSheets) {
    try {
      for (const rule of sheet.cssRules) css += rule.cssText + "\n";
    } catch {
      // hojas externas con CORS bloqueado — se omiten
    }
  }
  return css;
}

function TablesPopupContent({ tables }) {
  return (
    <div style={{ padding: "24px", fontFamily: "Outfit, sans-serif" }}>
      <h2 style={{ marginTop: 0, fontSize: "18px" }}>Tablas cargadas</h2>
      <ul style={{ listStyle: "none", padding: 0, margin: 0, display: "flex", flexDirection: "column", gap: "10px" }}>
        {tables.map((t) => {
          const cols = t.columns ?? [];
          const maxRows = cols.length > 0 ? Math.max(...cols.map(c => c.data?.length ?? 0)) : 0;
          return (
            <li key={t.tableName} style={{ border: "1px solid #e5e7eb", borderRadius: "8px", padding: "12px 16px" }}>
              <strong style={{ fontSize: "15px" }}>{t.tableName}</strong>
              <span style={{ marginLeft: "12px", fontSize: "13px", color: "#6b7280" }}>
                {cols.length} col · {maxRows} fil
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export default function TablesPopupButton({ tables }) {
  const [portalContainer, setPortalContainer] = useState(null);
  const popupRef = useRef(null);

  const handleOpen = () => {
    // Si ya está abierta, solo enfocarla
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.focus();
      return;
    }

    // Abrir directamente en el handler (gesto de usuario) para evitar bloqueador de popups
    const popup = window.open("", "", "width=1000,height=640,resizable=yes,scrollbars=yes");
    if (!popup) return;
    popupRef.current = popup;

    popup.document.title = "Tablas de origen";

    const style = popup.document.createElement("style");
    style.textContent = collectCSS();
    popup.document.head.appendChild(style);

    popup.document.body.style.margin = "0";
    popup.document.body.style.background = "var(--bg, #fff)";

    const root = popup.document.createElement("div");
    popup.document.body.appendChild(root);

    popup.onbeforeunload = () => {
      setPortalContainer(null);
      popupRef.current = null;
    };

    setPortalContainer(root);
  };

  if (!tables?.length) return null;

  return (
    <>
      <button className="origen-preview__toggle" onClick={handleOpen}>
        Ver tablas en ventana ↗
      </button>
      {portalContainer && createPortal(
        <TablesPopupContent tables={tables} />,
        portalContainer
      )}
    </>
  );
}
