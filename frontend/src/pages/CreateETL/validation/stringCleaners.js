// validation/stringCleaners.js

// Convierte texto a mayúsculas y reemplaza espacios
export const toUpperNoSpaces = (str) => {
  if (!str) return "";
  return str.trim().replace(/\s+/g, "_").toUpperCase();
};

//Input names
export const formatInputName = (name) => {
  const clean = toUpperNoSpaces(name);
  if (!clean.startsWith("INPUT_")) return `INPUT_${clean}`;
  return clean;
}