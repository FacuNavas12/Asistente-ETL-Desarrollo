const validateForm = ({ origenTables, stagingDef, reglasNegocio, dwhModel }) => {
  const errors = [];

  // ORIGEN
  if (!origenTables || origenTables.length === 0) {
    errors.push("Debe agregar al menos una tabla de origen.");
  } else {
    origenTables.forEach((t, idx) => {
      if (!t.tableName?.trim()) {
        errors.push(`La tabla ${idx + 1} de origen no tiene nombre.`);
      }
      if (!t.columns || t.columns.length === 0) {
        errors.push(`La tabla "${t.tableName || `sin nombre ${idx + 1}`}" no tiene columnas.`);
      }
    });
  }

  // STAGING
  if (!stagingDef.tableName.trim()) {
    errors.push("El nombre de la tabla de Staging está vacío.");
  }

  if (!stagingDef.columns || stagingDef.columns.length === 0) {
    errors.push("Debe agregar al menos una columna en Staging.");
  }

  // DWH
  if (!dwhModel.tables || dwhModel.tables.length === 0) {
    errors.push("Debe agregar al menos una tabla en el DWH.");
  } else {
    dwhModel.tables.forEach((t, idx) => {
      if (!t.nombre?.trim()) {
        errors.push(`La tabla ${idx + 1} del DWH no tiene nombre.`);
      }
      if (!t.columnas || t.columnas.length === 0) {
        errors.push(
          `La tabla ${t.nombre || "(sin nombre)"} no tiene columnas.`
        );
      }
    });
  }

  // REGLAS
  if (!reglasNegocio.trim()) {
    errors.push("Debe describir las reglas de negocio.");
  }

  return {
    isValid: errors.length === 0,
    errors,
  };
};

export default validateForm;