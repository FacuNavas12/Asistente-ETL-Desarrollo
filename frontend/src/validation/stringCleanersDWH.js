// validation/stringCleaners.js

// Convierte texto a mayúsculas y reemplaza espacios
export const toUpperNoSpaces = (str) => {
  if (!str) return "";
  return str.trim().replace(/\s+/g, "_").toUpperCase();
};

// 👉 Para tablas sigue igual
export const formatTableName = (name, tipo) => {
  const clean = toUpperNoSpaces(name);

  if(tipo === "Dimension" && !clean.startsWith("DIM_")) return `DIM_${clean}`;
  if(tipo === "Fact" && !clean.startsWith("FACT_")) return `FACT_${clean}`;
  return clean;
};

// 👉 Para columnas YA NO AGREGAMOS SK_ por defecto
export const cleanColumnText = (name) => {
  return toUpperNoSpaces(name || "");
};

// 👉 Aplica SK_ si corresponde
export const applySKPrefix = (name) => {
  const clean = toUpperNoSpaces(name);
  if (clean.startsWith("SK_")) return clean;
  return `SK_${clean}`;
};

// 👉 Quita SK_ si corresponde
export const removeSKPrefix = (name) => {
  return toUpperNoSpaces(name.replace(/^SK_/, ""));
};

// Staging names
export const formatStagingName = (name) => {
  console.log("nombre que llega por parametro: ", name);
  const clean = toUpperNoSpaces(name);
  if (!clean.startsWith("STG_")) return `STG_${clean}`;
  return clean;
}

//Input names
export const formatInputName = (name) => {
  const clean = toUpperNoSpaces(name);
  if (!clean.startsWith("INPUT_")) return `INPUT_${clean}`;
  return clean;
}