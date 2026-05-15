import Papa from "papaparse";
import { formatInputName } from "../validation/stringCleaners";

export function csvToTables(file) {
  return new Promise((resolve, reject) => {
    Papa.parse(file, {
      header: true,
      skipEmptyLines: true,
      complete: ({ data, meta }) => {
        const tableName = formatInputName(file.name.replace(/\.csv$/i, ""));
        const columns = (meta.fields ?? []).map((field) => ({
          name: field,
          dataType: "string",
          dataFormat: "",
          role: "atributo",
          data: data.map((row) => String(row[field] ?? "")),
        }));
        resolve([{ tableName, columns }]);
      },
      error: (err) => reject(new Error(err.message)),
    });
  });
}

