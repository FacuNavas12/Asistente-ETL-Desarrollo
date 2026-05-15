import { csvToTables }   from "../utils/csvToTables";
import { excelToTables } from "../utils/excelToTables";

import { CSV_TEXT, CSV_FILENAME, CSV_EXPECTED }   from "./inputs/csvSample";

import { makeExcelFile, EXCEL_EXPECTED }          from "./inputs/excelSample";

function check(label, actual, expected) {
  const pass = JSON.stringify(actual) === JSON.stringify(expected);
  return { label, pass, actual, expected };
}

function checkApprox(label, actual, expected) {
  const pass = actual === expected;
  return { label, pass, actual, expected };
}

async function runCsvTest() {
  const name = "CSV - clientes_test.csv";
  try {
    const blob = new Blob([CSV_TEXT], { type: "text/csv" });
    const file = new File([blob], CSV_FILENAME, { type: "text/csv" });
    const tables = await csvToTables(file);

    const checks = [
      checkApprox("tableCount",  tables.length,                   CSV_EXPECTED.tableCount),
      checkApprox("tableName",   tables[0]?.tableName,            CSV_EXPECTED.tableName),
      checkApprox("columnCount", tables[0]?.columns.length,       CSV_EXPECTED.columnNames.length),
      check(      "columnNames", tables[0]?.columns.map(c => c.name), CSV_EXPECTED.columnNames),
      checkApprox("rowCount",    tables[0]?.columns[0]?.data.length, CSV_EXPECTED.rowCount),
    ];

    const status = checks.every(c => c.pass) ? "pass" : "fail";
    console.group(`[ETL TEST] ${name} - ${status.toUpperCase()}`);
    checks.forEach(c => console.log(`  ${c.pass ? "✓" : "✗"} ${c.label}: got`, c.actual, c.pass ? "" : `expected ${JSON.stringify(c.expected)}`));
    console.groupEnd();
    return { name, status, checks, tables };
  } catch (error) {
    console.error(`[ETL TEST] ${name} - ERROR:`, error);
    return { name, status: "error", checks: [], tables: [], error: error.message };
  }
}

async function runExcelTest() {
  const name = "Excel - datos_test.xlsx";
  try {
    const file   = makeExcelFile();
    const tables = await excelToTables(file);

    const checks = [
      checkApprox("tableCount", tables.length, EXCEL_EXPECTED.tableCount),
      ...EXCEL_EXPECTED.tables.map((exp, i) => [
        checkApprox(`tables[${i}].tableName`,   tables[i]?.tableName,          exp.tableName),
        checkApprox(`tables[${i}].columnCount`, tables[i]?.columns.length,     exp.columnCount),
        checkApprox(`tables[${i}].rowCount`,    tables[i]?.columns[0]?.data.length, exp.rowCount),
      ]).flat(),
    ];

    const status = checks.every(c => c.pass) ? "pass" : "fail";
    console.group(`[ETL TEST] ${name} - ${status.toUpperCase()}`);
    checks.forEach(c => console.log(`  ${c.pass ? "✓" : "✗"} ${c.label}: got`, c.actual, c.pass ? "" : `expected ${JSON.stringify(c.expected)}`));
    console.groupEnd();
    return { name, status, checks, tables };
  } catch (error) {
    console.error(`[ETL TEST] ${name} - ERROR:`, error);
    return { name, status: "error", checks: [], tables: [], error: error.message };
  }
}


export async function runAllOrigenInputTests() {
  console.group("[ETL TESTS] OrigenInput parsers");
  const [csvResult, excelResult] = await Promise.all([
    runCsvTest(),
    Promise.resolve(runExcelTest())
    //Promise.resolve(runDdlTest()),
  ]);
  const results = [csvResult, excelResult];
  const passed  = results.filter(r => r.status === "pass").length;
  console.log(`\n[ETL TESTS] ${passed}/${results.length} tests pasaron`);
  console.groupEnd();
  return results;
}

