import * as XLSX from "xlsx";

const SHEETS = [
  {
    name: "ventas",
    rows: [
      ["venta_id", "producto",    "cantidad", "precio_unit", "fecha"],
      [1,          "Laptop",      2,          1200.00,       "2024-01-10"],
      [2,          "Monitor",     5,          350.50,        "2024-01-11"],
      [3,          "Teclado",     10,         45.99,         "2024-01-12"],
      [4,          "Mouse",       8,          25.00,         "2024-01-13"],
    ],
  },
  {
    name: "empleados",
    rows: [
      ["emp_id", "nombre",         "departamento", "salario",  "activo"],
      [101,      "Laura Mendez",   "Ventas",        55000,      true],
      [102,      "Carlos Ruiz",    "TI",            72000,      true],
      [103,      "Sofia Castro",   "RRHH",          48000,      false],
    ],
  },
];

export function makeExcelFile() {
  const wb = XLSX.utils.book_new();
  for (const { name, rows } of SHEETS) {
    const ws = XLSX.utils.aoa_to_sheet(rows);
    XLSX.utils.book_append_sheet(wb, ws, name);
  }
  const buf = XLSX.write(wb, { type: "array", bookType: "xlsx" });
  const blob = new Blob([buf], {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  return new File([blob], "datos_test.xlsx", { type: blob.type });
}

// formatInputName("ventas") → "INPUT_VENTAS", etc.
export const EXCEL_EXPECTED = {
  tableCount: 2,
  tables: [
    { tableName: "INPUT_VENTAS",    columnCount: 5, rowCount: 4 },
    { tableName: "INPUT_EMPLEADOS", columnCount: 5, rowCount: 3 },
  ],
};
