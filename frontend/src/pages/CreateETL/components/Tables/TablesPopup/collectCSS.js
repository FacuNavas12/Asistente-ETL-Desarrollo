export default function collectCSS() {
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
