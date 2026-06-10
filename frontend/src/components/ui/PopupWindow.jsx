// ADVERTENCIA: window.open() en useEffect es incompatible con React StrictMode
// (double-invoke del efecto cierra el popup antes de que el bloqueador lo permita reabrir).
// Preferir abrir el popup directamente en el onClick del componente que lo invoca.
import { useState, useEffect } from "react";
import { createPortal } from "react-dom";

function collectCSS() {
  let css = "";
  for (const sheet of document.styleSheets) {
    try {
      for (const rule of sheet.cssRules) {
        css += rule.cssText + "\n";
      }
    } catch {
      // hojas externas con CORS bloqueado — se omiten
    }
  }
  return css;
}

export default function PopupWindow({ children, title = "", onClose, width = 1000, height = 640 }) {
  const [container, setContainer] = useState(null);

  useEffect(() => {
    const popup = window.open(
      "",
      "",
      `width=${width},height=${height},resizable=yes,scrollbars=yes`
    );
    if (!popup) return;

    popup.document.title = title;

    // Copiar todas las reglas CSS como texto (sin clonar <link> ni <style>)
    const style = popup.document.createElement("style");
    style.textContent = collectCSS();
    popup.document.head.appendChild(style);

    popup.document.body.style.margin = "0";
    popup.document.body.style.background = "var(--bg, #fff)";

    const root = popup.document.createElement("div");
    popup.document.body.appendChild(root);
    setContainer(root);

    popup.onbeforeunload = () => onClose?.();
    return () => { if (!popup.closed) popup.close(); };
  }, []);

  return container ? createPortal(children, container) : null;
}
