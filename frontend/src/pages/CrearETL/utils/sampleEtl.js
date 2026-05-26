export const SAMPLE_ETL = {
  descripcionObjetivo:
    "Construir un Data Warehouse para análisis de ventas que permita reportar facturación por cliente, producto y período. " +
    "El proceso debe consolidar datos de ventas diarias, normalizar información de clientes y productos, " +
    "y exponer un modelo dimensional con una tabla de hechos de ventas y dimensiones de cliente, producto y tiempo.",

  origenTables: [
    {
      tableName: "ventas_raw",
      columns: [
        { name: "id_venta",      dataType: "int",      dataFormat: "",                role: "pk",        data: ["1001", "1002", "1003", "1004", "1005"] },
        { name: "fecha",         dataType: "date",     dataFormat: "YYYY-MM-DD",      role: "atributo",  data: ["2026-01-15", "2026-01-15", "2026-02-03", "2026-02-10", "2026-03-01"] },
        { name: "id_cliente",    dataType: "int",      dataFormat: "",                role: "fk",        data: ["501", "502", "501", "503", "502"] },
        { name: "id_producto",   dataType: "int",      dataFormat: "",                role: "fk",        data: ["P-100", "P-200", "P-100", "P-300", "P-200"] },
        { name: "cantidad",      dataType: "int",      dataFormat: "",                role: "atributo",  data: ["2", "1", "5", "3", "1"] },
        { name: "precio_unit",   dataType: "decimal",  dataFormat: "10,2",            role: "atributo",  data: ["1500.00", "8200.50", "1500.00", "450.75", "8200.50"] },
        { name: "descuento",     dataType: "decimal",  dataFormat: "5,2",             role: "atributo",  data: ["0", "10", "5", "0", ""] },
      ],
    },
    {
      tableName: "clientes_raw",
      columns: [
        { name: "id_cliente",    dataType: "int",      dataFormat: "",                role: "pk",        data: ["501", "502", "503"] },
        { name: "nombre",        dataType: "varchar",  dataFormat: "100",             role: "atributo",  data: ["juan perez", "MARIA LOPEZ", "  Carlos Ruiz  "] },
        { name: "email",         dataType: "varchar",  dataFormat: "150",             role: "atributo",  data: ["juan@mail.com", "MARIA@MAIL.COM", "carlos@mail"] },
        { name: "ciudad",        dataType: "varchar",  dataFormat: "80",              role: "atributo",  data: ["CABA", "Rosario", "Córdoba"] },
        { name: "fecha_alta",    dataType: "date",     dataFormat: "YYYY-MM-DD",      role: "atributo",  data: ["2024-05-12", "2023-11-30", "2025-02-18"] },
      ],
    },
    {
      tableName: "productos_raw",
      columns: [
        { name: "id_producto",   dataType: "varchar",  dataFormat: "10",              role: "pk",        data: ["P-100", "P-200", "P-300"] },
        { name: "descripcion",   dataType: "varchar",  dataFormat: "200",             role: "atributo",  data: ["Auriculares BT", "Notebook 14\"", "Cable USB-C"] },
        { name: "categoria",     dataType: "varchar",  dataFormat: "50",              role: "atributo",  data: ["Audio", "Computación", "Accesorios"] },
        { name: "precio_lista",  dataType: "decimal",  dataFormat: "10,2",            role: "atributo",  data: ["1500.00", "8200.50", "450.75"] },
      ],
    },
  ],

  reglasNegocio:
    "1. Excluir ventas con cantidad <= 0 o precio_unit <= 0.\n" +
    "2. Normalizar nombre de cliente a Title Case y quitar espacios extra.\n" +
    "3. Validar formato de email; si es inválido, reemplazar por NULL.\n" +
    "4. Estandarizar ciudad a mayúsculas.\n" +
    "5. Calcular monto_total = cantidad * precio_unit * (1 - descuento/100).\n" +
    "6. Categoría de cliente: FRECUENTE si tiene más de 3 ventas en el período, REGULAR en otro caso.\n" +
    "7. Solo cargar ventas con fecha >= 2026-01-01.\n" +
    "8. La dimensión de tiempo debe incluir año, trimestre, mes y día de la semana.",
};
