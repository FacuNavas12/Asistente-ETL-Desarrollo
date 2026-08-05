/**
 * Mirror de backend/app/services/ktr_builder/naming.py::derive_keyword +
 * formato de timestamp — usado SOLO por la exportación de raw-steps
 * (etlExport.js::downloadLlmRaw, disparada automáticamente por
 * tempAutoDownloadRawSteps.js). Mismo texto fuente (proceso_etl.nombre del
 * LLM) y misma heurística que el backend, para que el archivo de raw-steps
 * quede rastreable junto a los .ktr/.kjb que el backend genere después del
 * mismo proceso. Si naming.py cambia la heurística, portar el cambio acá
 * también — no hay forma de compartir el módulo entre Python y JS.
 */

const FILLER_WORDS = new Set([
  "consolidacion", "consolidado", "actualizacion", "actualizado",
  "proceso", "procesos", "etl", "carga", "cargas", "generacion",
  "integracion", "sincronizacion", "migracion", "staging", "stg", "dwh",
  "datos", "dato", "base", "origen",
]);

const STOPWORDS = new Set([
  "de", "del", "la", "el", "los", "las", "a", "al", "con", "para",
  "por", "en", "y", "o", "un", "una", "unos", "unas",
]);

const ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789";

// Rango Unicode "Combining Diacritical Marks" (U+0300-U+036F) construido por
// código en vez de literal en el regex — evita depender de cómo el editor/
// pipeline de turno serialice un caracter combinante crudo en el archivo.
const COMBINING_MARKS = new RegExp(
  `[${String.fromCharCode(0x0300)}-${String.fromCharCode(0x036f)}]`,
  "g",
);

function stripAccents(s) {
  return s.normalize("NFKD").replace(COMBINING_MARKS, "");
}

function randomId(n = 4) {
  let out = "";
  for (let i = 0; i < n; i++) out += ID_ALPHABET[Math.floor(Math.random() * ID_ALPHABET.length)];
  return out;
}

function keywordSanitize(word) {
  return stripAccents(word).replace(/[^a-zA-Z0-9]/g, "") || randomId();
}

/** Misma heurística que naming.py::derive_keyword — ver docstring de ese módulo. */
export function deriveKeyword(processName) {
  // \p{L}\p{N} (Unicode letras+dígitos) en vez de \w — a diferencia de
  // Python, el \w de JS es ASCII-only incluso con el flag /u, así que
  // "Catálogo" se partiría en "Cat"+"logo" por la á sin esto.
  const words = (processName ?? "").match(/[\p{L}\p{N}]+/gu) ?? [];
  for (const w of words) {
    const wl = stripAccents(w.toLowerCase());
    if (wl.length < 2 || STOPWORDS.has(wl) || FILLER_WORDS.has(wl)) continue;
    return keywordSanitize(w.toLowerCase());
  }
  if (words.length) return keywordSanitize(words[0].toLowerCase());
  return randomId(); // "falta de nombre" real — nunca fallar por esto
}

function pad2(n) {
  return String(n).padStart(2, "0");
}

/** Mismo formato que naming.py::_timestamp — YYYYMMDD_HHMMSS, sin milisegundos. */
export function timestamp() {
  const d = new Date();
  return (
    `${d.getFullYear()}${pad2(d.getMonth() + 1)}${pad2(d.getDate())}` +
    `_${pad2(d.getHours())}${pad2(d.getMinutes())}${pad2(d.getSeconds())}`
  );
}
