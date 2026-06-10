import { useState, useRef } from "react";
import { createPortal } from "react-dom";
import collectCSS from "./collectCSS";
import TablesPopupContent from "./TablesPopupContent";

export default function TablesPopupWindow({ tables, children }) {
  const [portalContainer, setPortalContainer] = useState(null);
  const popupRef = useRef(null);

  const handleOpen = () => {
    if (popupRef.current && !popupRef.current.closed) {
      popupRef.current.focus();
      return;
    }

    const popup = window.open("", "", "width=1000,height=640,resizable=yes,scrollbars=yes");
    if (!popup) return;
    popupRef.current = popup;

    popup.document.title = "Tablas de origen";

    const style = popup.document.createElement("style");
    style.textContent = collectCSS();
    popup.document.head.appendChild(style);

    popup.document.body.style.margin = "0";

    const root = popup.document.createElement("div");
    popup.document.body.appendChild(root);

    popup.onbeforeunload = () => {
      setPortalContainer(null);
      popupRef.current = null;
    };

    setPortalContainer(root);
  };

  return (
    <>
      {children(handleOpen)}
      {portalContainer && createPortal(
        <TablesPopupContent tables={tables} />,
        portalContainer
      )}
    </>
  );
}
