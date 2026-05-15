export const CSV_FILENAME = "clientes_test.csv";

export const CSV_TEXT = `id,nombre,email,saldo,activo,fecha_alta
1,Juan Perez,juan@mail.com,1500.50,true,2023-01-15
2,Maria Lopez,maria@mail.com,2300.00,false,2023-03-22
3,Pedro Garcia,pedro@mail.com,800.75,true,2022-11-05
4,Ana Torres,ana@mail.com,4200.10,true,2024-06-30`;

// formatInputName("clientes_test") → "INPUT_CLIENTES_TEST"
export const CSV_EXPECTED = {
  tableCount: 1,
  tableName: "INPUT_CLIENTES_TEST",
  columnNames: ["id", "nombre", "email", "saldo", "activo", "fecha_alta"],
  rowCount: 4,
};
