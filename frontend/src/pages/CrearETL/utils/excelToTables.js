import * as XLSX from "xlsx";
import { formatInputName } from "../validation/stringCleaners";

export function excelToTables(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = (e) => {
      try {
        const workbook = XLSX.read(e.target.result, { type: "array" });
        const tables = workbook.SheetNames.map((sheetName) => {
          const sheet = workbook.Sheets[sheetName];
          const rows = XLSX.utils.sheet_to_json(sheet, { header: 1, defval: "" });
          if (rows.length === 0) return null;
          const [headers, ...dataRows] = rows;
          const columns = headers.map((field, i) => ({
            name: String(field ?? `col${i + 1}`),
            dataType: "string",
            dataFormat: "",
            role: "atributo",
            data: dataRows.map((row) => String(row[i] ?? "")),
          }));
          return { tableName: formatInputName(sheetName), columns };
        }).filter(Boolean);
        resolve(tables);
      } catch (err) {
        reject(err);
      }
    };
    reader.onerror = () => reject(new Error("Error al leer el archivo"));
    reader.readAsArrayBuffer(file);
  });
}

