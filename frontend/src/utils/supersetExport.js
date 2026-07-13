import JSZip from "jszip";
import yaml from "js-yaml";

// ── Constants ────────────────────────────────────────────────────────────────
const VERSION = "1.0.0";
const DB_NAME = "ETL_DWH";
const DB_SCHEMA = "public";
const dumpOpts = { noRefs: true, lineWidth: -1, sortKeys: false };
const dump = (obj) => yaml.dump(obj, dumpOpts);
// UUID determinista: misma semilla → mismo UUID en cada exportación.
// Permite que overwrite=true actualice el chart existente (mismo UUID → mismo ID en Superset)
// en lugar de crear uno nuevo cada vez.
const deterministicUUID = (seed) => {
  let h1 = 0xdeadbeef, h2 = 0x41c6ce57;
  for (let i = 0; i < seed.length; i++) {
    const c = seed.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 2654435761) >>> 0;
    h2 = Math.imul(h2 ^ c, 1597334677) >>> 0;
  }
  h1 ^= h2 >>> 17; h2 ^= h1 >>> 13;
  h1 = Math.imul(h1, 2654435761) >>> 0;
  h2 = Math.imul(h2, 1597334677) >>> 0;
  const h3 = (h1 ^ (h2 << 5)) >>> 0;
  const h4 = (h2 ^ (h1 >> 3)) >>> 0;
  const pad = n => (n >>> 0).toString(16).padStart(8, "0");
  const [a, b, c, d] = [pad(h1), pad(h2), pad(h3), pad(h4)];
  return `${a}-${b.slice(0, 4)}-4${b.slice(5, 8)}-${(8 + (h3 & 3)).toString(16)}${c.slice(1, 4)}-${c.slice(4)}${d}`;
};

// UUID fijo para la conexión de base de datos — garantiza que todos los exports
// compartan la misma entrada ETL_DWH en Superset. El usuario la configura una vez
// y todos los dashboards (ETLs y Jobs) la reutilizan automáticamente.
const DB_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890";

// Columnas de auditoría ETL — no aportan valor analítico en charts
const AUDIT_KEYWORDS = [
  "CARGA_DW", "LOAD_DT", "INSERT_DT", "UPDATE_DT", "CREATED_AT", "UPDATED_AT",
  "MODIFIED_AT", "ETL_DATE", "PROCESS_DATE", "FECHA_CARGA", "FECHA_INSERT",
  "FECHA_UPDATE", "FECHA_ETL", "FECHA_PROCESO", "DW_TIMESTAMP", "AUDIT",
];

// ── Column name utilities ─────────────────────────────────────────────────────
const isUsableColumn = (name) => {
  if (!name) return false;
  const upper = String(name).toUpperCase();
  if (upper.startsWith("SK_")) return false;
  if (upper.startsWith("FK_")) return false;
  if (upper.startsWith("ID_")) return false;
  if (upper.startsWith("COD_")) return false;
  if (upper.startsWith("BK_")) return false;
  if (upper === "ID" || upper.endsWith("_ID")) return false;
  // Identificadores de negocio LATAM — no aportan valor analítico como dimensión
  if (upper === "RUT") return false;
  if (upper === "CI") return false;
  if (upper === "DNI") return false;
  if (upper === "LEGAJO") return false;
  if (upper === "CODIGO") return false;
  if (upper === "CODE") return false;
  if (upper === "NRO" || upper === "NUMERO") return false;
  if (upper.startsWith("NRO_")) return false;
  if (upper.startsWith("NUM_")) return false;
  if (upper.startsWith("COD") && upper.length <= 6) return false;
  return true;
};

const inferSemanticType = (name, values) => {
  const u = String(name).toUpperCase();
  const sample = values.find(v => v !== null && v !== undefined && v !== "");

  // Surrogate / foreign / natural keys → exclude
  if (u === "ID" || u.endsWith("_ID") || u.startsWith("SK_") ||
    u.startsWith("FK_") || u.startsWith("ID_")) return "id";

  if (typeof sample === "boolean") return "boolean";

  // Audit columns → treat as non-usable
  if (AUDIT_KEYWORDS.some(k => u.includes(k))) return "id";

  // Date detection
  const DATE_KW = ["FECHA", "DATE", "DT", "ANIO", "MES", "TRIMESTRE", "DIA", "YEAR", "MONTH", "DAY", "PERIODO", "QUARTER"];
  if (DATE_KW.some(k => u.includes(k))) return "date";
  if (typeof sample === "string" && /^\d{4}-\d{2}(-\d{2})?$/.test(sample)) return "date";

  // Category-prefix indicators (TIPO_VENTA should be category, not metric even if VENTA is a metric keyword)
  const CAT_PREFIXES = ["TIPO", "CATEGORIA", "ESTADO", "CLASE", "GRUPO", "NOMBRE", "DESC", "DESCRIPCION", "CODIGO", "CODE", "FLAG", "IND", "INDICADOR", "GENERO", "PAIS", "REGION", "CIUDAD", "ZONA", "SEGMENTO"];
  if (CAT_PREFIXES.some(k => u === k || u.startsWith(k + "_"))) return "category";

  // Metric detection — keywords cover the common DWH vocabulary
  const METRIC_KW = ["MONTO", "IMPORTE", "TOTAL", "PRECIO", "CANTIDAD", "QTY", "AMOUNT", "INGRESO", "EGRESO",
    "COSTO", "VENTA", "COMPRA", "REVENUE", "DESCUENTO", "IMPUESTO", "NETO", "BRUTO", "SALDO", "COUNT",
    "VALOR", "STOCK", "PESO", "VOLUMEN", "TASA", "PORCENTAJE", "RATIO", "SCORE", "RATING", "HORAS",
    "DIAS", "UNIDADES", "GANANCIA", "MARGEN", "UTILIDAD", "FACTURACION", "PAGOS", "CUOTA", "DEUDA",
    "CREDITO", "DEBITO", "BALANCE", "INVENTARIO", "VENTAS", "COMPRAS", "PROMEDIO", "AVG", "SUM", "MAX", "MIN"];

  if (typeof sample === "number" && METRIC_KW.some(k => u.includes(k))) return "metric";
  // Name-only metric inference for KTR-parsed columns where values are all null
  if (sample === undefined && METRIC_KW.some(k => u.includes(k))) return "metric";
  if (typeof sample === "number") return "metric";

  return "category";
};

const inferType = (values) => {
  const sample = values.find(v => v !== null && v !== undefined && v !== "");
  if (sample === undefined) return "VARCHAR";
  if (typeof sample === "number") return Number.isInteger(sample) ? "INTEGER" : "DOUBLE PRECISION";
  if (typeof sample === "boolean") return "BOOLEAN";
  return "VARCHAR";
};

// ── Table builder ─────────────────────────────────────────────────────────────
// Prefijos que indican tablas intermedias/staging — excluidas del export analítico
const STAGING_PREFIXES = ["stg_", "staging_", "tmp_", "temp_", "ods_", "raw_", "wrk_", "work_", "landing_", "src_", "source_", "ext_"];

const isAnalyticsTable = (name) => {
  const lower = String(name).toLowerCase();
  return !STAGING_PREFIXES.some(p => lower.startsWith(p));
};

const buildTables = (dwhSample = {}, dwhModel = null) =>
  Object.entries(dwhSample)
    .filter(([name]) => isAnalyticsTable(name))
    .map(([name, rows]) => {
      if (!Array.isArray(rows) || !rows.length) return null;

      // Si la fila está vacía (modelo no pobló valores), generar valores sintéticos
      // a partir del dwhModel del formulario o de patrones de nombre de columna comunes
      const firstRow = rows[0] ?? {};
      if (Object.keys(firstRow).length === 0) {
        const tableModel = dwhModel?.tables?.find(
          t => t.nombre?.toLowerCase() === name.toLowerCase()
        );
        if (tableModel?.columnas?.length) {
          const syntheticRow = {};
          for (const col of tableModel.columnas) {
            syntheticRow[col.nombre.toLowerCase()] = _syntheticValue(col.nombre);
          }
          rows = [syntheticRow];
        } else {
          return null;
        }
      }
      const colNames = Array.from(rows.reduce((s, row) => {
        // Normalizar a minúsculas para compatibilidad con PostgreSQL
        Object.keys(row ?? {}).forEach(k => s.add(k.toLowerCase())); return s;
      }, new Set()));
      const columns = colNames.map(col => ({
        name: col, // ya está en minúsculas
        // buscar el valor con la key original (mayúsculas o minúsculas)
        values: rows.map(r => r?.[col] ?? r?.[col.toUpperCase()]),
        semanticType: inferSemanticType(col, rows.map(r => r?.[col] ?? r?.[col.toUpperCase()])),
      }));
      const usableColumns = columns.filter(c =>
        isUsableColumn(c.name) &&
        c.values.some(v => v !== null && v !== undefined && v !== "")
      );

      const descriptiveKeywords = [
        'NOMBRE', 'NAME', 'DESCRIPCION', 'DESCRIPTION', 'DETALLE', 'DETAIL',
        'TIPO', 'TYPE', 'CATEGORIA', 'CATEGORY', 'CLASE', 'CLASS',
        'ESTADO', 'STATUS', 'ETIQUETA', 'LABEL', 'TITULO', 'TITLE',
        // Identificadores descriptivos LATAM
        'RAZON_SOCIAL', 'RAZON', 'SOCIAL', 'DENOMINACION', 'FANTASIA',
        'APELLIDO', 'SURNAME',
        // Adicionales genéricos
        'OBSERVACION', 'COMENTARIO', 'NOTA',
        'SUBCATEGORIA', 'SUBCATEGORY',
        'LOCALIDAD', 'BARRIO', 'COLONIA',
        'SUCURSAL', 'BRANCH', 'OFICINA', 'SEDE',
        'LINEA', 'LINE', 'FAMILIA', 'FAMILY', 'MARCA', 'BRAND',
        'SERVICIO', 'SERVICE', 'MODALIDAD', 'TURNO', 'SHIFT',
        'DEPARTAMENTO', 'CIUDAD', 'PAIS', 'REGION', 'PROVINCIA',
        'LOCALIDAD', 'MUNICIPIO', 'ZONA', 'TERRITORIO', 'COUNTRY', 'CITY',
        'PROYECTO', 'PROJECT', 'FASE', 'ETAPA', 'STAGE',
        'PRODUCTO', 'PRODUCT', 'ARTICULO', 'ITEM', 'SKU',
        'CLIENTE', 'CUSTOMER', 'PROVEEDOR', 'SUPPLIER', 'VENDEDOR',
        'COMPRA', 'VENTA', 'SALE', 'CANAL', 'CHANNEL',
        'ONTOLOGY', 'TERM', 'DEFINITION', 'QUALIFIER', 'EVIDENCE',
        'GENE', 'PROTEIN', 'RNA', 'ANNOTATION',
        'EMPLEADO', 'EMPLOYEE', 'CARGO', 'ROLE',
        'AREA', 'DIVISION', 'EQUIPO', 'TEAM',
        'ASIGNATURA', 'CURSO', 'MATERIA', 'CARRERA', 'FACULTAD',
        'ALUMNO', 'STUDENT', 'DOCENTE', 'TEACHER',
      ];

      const pickColumn =
        usableColumns.find(c => descriptiveKeywords.some(k => c.name.toUpperCase().includes(k))) ??
        usableColumns.find(c => typeof c.values.find(v => v !== null) === 'string') ??
        usableColumns[0] ??
        columns.find(c => c.values.some(v => v !== null && v !== undefined && v !== ""));
      return pickColumn ? { name, columns, pickColumn } : null;
    })
    .filter(Boolean);

// ── PDI step column extractors ────────────────────────────────────────────────
// Reads text of a DIRECT child element only (avoids tag-name collisions with grandchildren)
const directChildText = (el, tag) => {
  for (const child of el.children) {
    if (child.tagName === tag) return child.textContent?.trim() || null;
  }
  return null;
};

// ─ Category A: fields > field > column_name | stream_name
// Covers: TableOutput, ConcurrentTableOutput, SynchronizeAfterMerge,
//         PostgresBulkLoader, OraBulkLoader, MySQLBulkLoader, MSSQLBulkLoader,
//         VerticaBulkLoader, TeraFastBulkLoader, MonetDBBulkLoader, DB2BulkLoader
const extractFieldsCols = (step) =>
  Array.from(step.querySelectorAll("fields > field")).map(f =>
    (f.querySelector("column_name")?.textContent ||
      f.querySelector("stream_name")?.textContent || "").trim()
  ).filter(Boolean);

// ─ Category B: DimensionLookup (SCD type 1/2)
//   lookup keys: fields > key > name
//   update attributes: fields > field > name
//   surrogate key returned: fields > return > name
const extractDimLookupCols = (step) => [
  ...Array.from(step.querySelectorAll("fields > key")).map(k => k.querySelector("name")?.textContent?.trim()),
  ...Array.from(step.querySelectorAll("fields > field")).map(f => f.querySelector("name")?.textContent?.trim()),
  ...Array.from(step.querySelectorAll("fields > return")).map(r => r.querySelector("name")?.textContent?.trim()),
].filter(Boolean);

// ─ Category C: InsertUpdate / Update / Delete
//   keys: lookup > key > name
//   values: lookup > value > name
const extractLookupCols = (step) => [
  ...Array.from(step.querySelectorAll("lookup > key")).map(k => k.querySelector("name")?.textContent?.trim()),
  ...Array.from(step.querySelectorAll("lookup > value")).map(v => v.querySelector("name")?.textContent?.trim()),
].filter(Boolean);

// ─ Category D: CombinationLookup (degenerate dimensions)
//   fields: fields > field > name
//   surrogate: return > name
const extractCombinationCols = (step) => [
  ...Array.from(step.querySelectorAll("fields > field")).map(f => f.querySelector("name")?.textContent?.trim()),
  step.querySelector("return > name")?.textContent?.trim(),
].filter(Boolean);

// ─ Generic fallback: tries all known column-name patterns across PDI XML schemas.
//   Covers custom plugins and any step type not listed explicitly.
const extractGenericCols = (step) => {
  const SELECTORS = [
    "fields > field > column_name",
    "fields > field > stream_name",
    "fields > field > name",
    "fields > key > name",
    "fields > return > name",
    "lookup > key > name",
    "lookup > value > name",
    "keys > key > name",
    "values > value > name",
    "mapping > field > name",
    "mapping > field > column_name",
    "field_in > name",
    "field_out > name",
  ];
  const cols = new Set();
  for (const sel of SELECTORS) {
    for (const el of step.querySelectorAll(sel)) {
      const text = el.textContent?.trim();
      if (text && text.length > 0 && text.length < 128) cols.add(text);
    }
  }
  return Array.from(cols);
};

// Step type → extractor mapping.
// Any type NOT listed here falls through to extractGenericCols.
const STEP_EXTRACTORS = {
  // Standard table write (fields > field > column_name / stream_name)
  TableOutput: extractFieldsCols,
  ConcurrentTableOutput: extractFieldsCols,
  SynchronizeAfterMerge: extractFieldsCols,
  // Bulk loaders — all use same fields structure as TableOutput
  PostgresBulkLoader: extractFieldsCols,
  OraBulkLoader: extractFieldsCols,
  MySQLBulkLoader: extractFieldsCols,
  MSSQLBulkLoader: extractFieldsCols,
  VerticaBulkLoader: extractFieldsCols,
  TeraFastBulkLoader: extractFieldsCols,
  MonetDBBulkLoader: extractFieldsCols,
  DB2BulkLoader: extractFieldsCols,
  // SCD dimension
  DimensionLookup: extractDimLookupCols,
  // Lookup-based writes
  InsertUpdate: extractLookupCols,
  Update: extractLookupCols,
  Delete: extractLookupCols,
  // Degenerate dimension
  CombinationLookup: extractCombinationCols,
};

// Genera un valor sintético tipado para que inferSemanticType pueda usar el valor JS
// (detecta boolean, number, string) además del nombre de la columna.
const _syntheticValue = (colName) => {
  const u = colName.toUpperCase();

  if (u.startsWith("SK_") || u.startsWith("FK_") ||
    u.startsWith("ID_") || u.endsWith("_ID") || u === "ID") return 1;

  const dateKW = ["FECHA", "DATE", "DT", "INICIO", "FIN", "COMIENZO"];
  if (dateKW.some(k => u.includes(k))) return "2024-01-01";

  if (u.startsWith("ES_") || u.startsWith("IS_") || u.startsWith("FLAG_") ||
    u.includes("VIGENTE") || u.includes("ACTIVO") || u.includes("CAPITAL")) return true;

  const numKW = ["MONTO", "TOTAL", "PRECIO", "CANTIDAD", "QTY", "AREA", "POBLACION",
    "DENSIDAD", "DURACION", "DIAS", "PORCENTAJE", "TASA", "COSTO"];
  if (numKW.some(k => u.includes(k))) return 0.0;

  const intKW = ["ANIO", "MES", "DIA", "TRIMESTRE", "YEAR", "MONTH", "DAY", "ORDEN",
    "ORDER", "NUMERO", "NUM", "COUNT"];
  if (intKW.some(k => u.includes(k))) return 1;

  return "ejemplo";
};

// Parses PDI .ktr files and returns a dwh_sample-compatible object:
// { tableName: [{ col1: <syntheticValue>, ... }] }
// Works with ALL PDI output step types; unknown types use generic column extraction.
export async function extractDwhSchemaFromKtrs(ktrFiles) {
  const dwhSample = {};

  const addCols = (tableName, cols) => {
    if (!tableName || !cols.length) return;
    const name = tableName.toLowerCase();
    const existing = dwhSample[name]?.[0] ?? {};
    cols.forEach(col => { if (!(col in existing)) existing[col] = _syntheticValue(col); });
    dwhSample[name] = [existing];
  };

  for (const file of ktrFiles) {
    let text;
    try { text = await file.text(); } catch { continue; }
    let doc;
    try { doc = new DOMParser().parseFromString(text, "text/xml"); } catch { continue; }
    if (doc.querySelector("parsererror")) continue;

    for (const step of Array.from(doc.querySelectorAll("step"))) {
      const stepType = directChildText(step, "type");
      if (!stepType) continue;

      const tableName = directChildText(step, "table");
      if (!tableName) continue;

      // Skip reject/log/audit tables in addition to staging prefixes
      const tl = tableName.toLowerCase();
      if (tl.includes("rechaz") || tl.includes("reject") ||
        tl.includes("_log") || tl.includes("audit")) continue;

      const extractor = STEP_EXTRACTORS[stepType] ?? extractGenericCols;
      addCols(tableName, extractor(step));
    }
  }

  return dwhSample;
}

// ── Metrics ───────────────────────────────────────────────────────────────────
const countMetric = {
  label: "COUNT(*)",
  expressionType: "SQL",
  sqlExpression: "COUNT(*)",
  hasCustomLabel: false,
  optionName: "metric_count",
};

const sumMetric = (colName) => ({
  label: `SUM(${colName})`,
  expressionType: "SQL",
  sqlExpression: `SUM(${colName})`,
  hasCustomLabel: false,
  optionName: `metric_sum_${colName.toLowerCase().replace(/\W/g, "_")}`,
});

// ── Database / dataset YAML ───────────────────────────────────────────────────
const metadataYaml = () => dump({
  version: VERSION,
  type: "Dashboard",
  timestamp: new Date().toISOString(),
});

const databaseYaml = (dbUuid, sqlalchemyUri) => dump({
  database_name: DB_NAME,
  sqlalchemy_uri: sqlalchemyUri,
  cache_timeout: null,
  expose_in_sqllab: true,
  allow_run_async: false,
  allow_ctas: false,
  allow_cvas: false,
  allow_dml: false,
  allow_file_upload: false,
  extra: JSON.stringify({
    allows_virtual_table_explore: true,
    schemas_allowed_for_csv_upload: [],
    engine_params: {},
    metadata_params: {},
  }),
  uuid: dbUuid,
  version: VERSION,
});

const datasetYaml = (table, dsUuid, dbUuid) => dump({
  table_name: table.name,
  main_dttm_col: null,
  description: null,
  default_endpoint: null,
  offset: 0,
  cache_timeout: null,
  schema: DB_SCHEMA,
  sql: null,
  params: null,
  template_params: null,
  filter_select_enabled: true,
  fetch_values_predicate: null,
  extra: null,
  normalize_columns: false,
  always_filter_main_dttm: false,
  uuid: dsUuid,
  metrics: [{
    metric_name: "count",
    verbose_name: "COUNT(*)",
    metric_type: "count",
    expression: "COUNT(*)",
    description: null,
    d3format: null,
    extra: null,
    warning_text: null,
  }],
  columns: table.columns.map(c => ({
    column_name: c.name.toLowerCase(),
    verbose_name: null,
    is_dttm: false,
    is_active: true,
    type: inferType(c.values),
    advanced_data_type: null,
    groupby: true,
    filterable: true,
    expression: null,
    description: null,
    python_date_format: null,
    extra: null,
  })),
  version: VERSION,
  database_uuid: dbUuid,
});

// ── Superset chart YAML generators ────────────────────────────────────────────
// IMPORTANTE: params se serializa como objeto YAML (no JSON string).
// slice_name siempre se recibe como parámetro sliceName para garantizar
// que coincida exactamente con el sliceName del dashboard position_json.

const tableChartYaml = ({ tableName, columnName, dsUuid, chartUuid, sliceName, isMetric = false }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "table",
    url_params: {},
    time_grain_sqla: null,
    time_range: "No filter",
    query_mode: isMetric ? "raw" : "aggregate",
    groupby: isMetric ? [] : [columnName],
    metrics: isMetric ? [] : [countMetric],
    all_columns: isMetric ? [columnName] : [],
    percent_metrics: [],
    adhoc_filters: [],
    order_by_cols: [],
    order_desc: true,
    row_limit: 1000,
    include_time: false,
    show_cell_bars: true,
    align_pn: false,
    page_length: 25,
    include_search: true,
    extra_form_data: {},
  };
  return dump({
    slice_name: sliceName,
    description: null,
    certified_by: null,
    certification_details: null,
    viz_type: "table",
    params,
    query_context: null,
    cache_timeout: null,
    uuid: chartUuid,
    version: VERSION,
    dataset_uuid: dsUuid,
    is_managed_externally: false,
    external_url: null,
  });
};

const pieChartYaml = ({ tableName, columnName, dsUuid, chartUuid, sliceName, metric = countMetric }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "pie",
    url_params: {},
    time_range: "No filter",
    metric,
    adhoc_filters: [],
    groupby: [columnName],
    row_limit: 100,
    color_scheme: "supersetColors",
    show_legend: true,
    rich_tooltip: true,
    donut: true,
    show_labels: true,
    labels_outside: true,
    extra_form_data: {},
  };
  return dump({
    slice_name: sliceName,
    description: null,
    certified_by: null,
    certification_details: null,
    viz_type: "pie",
    params,
    query_context: null,
    cache_timeout: null,
    uuid: chartUuid,
    version: VERSION,
    dataset_uuid: dsUuid,
    is_managed_externally: false,
    external_url: null,
  });
};

const barChartYaml = ({ tableName, columnName, xAxis, metric, dsUuid, chartUuid, sliceName }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "echarts_timeseries_bar",
    x_axis: xAxis ?? columnName,
    metrics: [metric ?? countMetric],
    groupby: [],
    adhoc_filters: [],
    row_limit: 10000,
    time_range: "No filter",
    color_scheme: "supersetColors",
    extra_form_data: {},
    orientation: "vertical",
    x_axis_sort_asc: true,
    x_axis_sort_series: "name",
  };
  return dump({
    slice_name: sliceName,
    description: null,
    certified_by: null,
    certification_details: null,
    viz_type: "echarts_timeseries_bar",
    params,
    query_context: null,
    cache_timeout: null,
    uuid: chartUuid,
    version: VERSION,
    dataset_uuid: dsUuid,
    is_managed_externally: false,
    external_url: null,
  });
};

const lineChartYaml = ({ tableName, columnName, xAxis, metric, dsUuid, chartUuid, sliceName }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "echarts_timeseries_line",
    x_axis: xAxis,
    metrics: [metric ?? countMetric],
    groupby: [],
    adhoc_filters: [],
    row_limit: 10000,
    time_range: "No filter",
    color_scheme: "supersetColors",
    extra_form_data: {},
  };
  return dump({
    slice_name: sliceName,
    description: null,
    certified_by: null,
    certification_details: null,
    viz_type: "echarts_timeseries_line",
    params,
    query_context: null,
    cache_timeout: null,
    uuid: chartUuid,
    version: VERSION,
    dataset_uuid: dsUuid,
    is_managed_externally: false,
    external_url: null,
  });
};

const bigNumberYaml = ({ tableName, columnName, dsUuid, chartUuid, sliceName }) => {
  const kpiMetric = columnName
    ? { label: `SUM(${columnName})`, expressionType: "SQL", sqlExpression: `SUM(${columnName})`, hasCustomLabel: false, optionName: `metric_sum_${columnName}` }
    : countMetric;
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "big_number_total",
    metric: kpiMetric,
    adhoc_filters: [],
    time_range: "No filter",
    extra_form_data: {},
  };
  return dump({
    slice_name: sliceName,
    description: null,
    certified_by: null,
    certification_details: null,
    viz_type: "big_number_total",
    params,
    query_context: null,
    cache_timeout: null,
    uuid: chartUuid,
    version: VERSION,
    dataset_uuid: dsUuid,
    is_managed_externally: false,
    external_url: null,
  });
};

// ── Smart chart selection ─────────────────────────────────────────────────────
// Returns an array of chart specs: { type, columnName, xAxis?, metric?, label }
// Chart selection logic per table type:
//
//  FACT   → big_number (KPI) + line (metric over time) + bar (metric by category) + table
//  DIM    → pie | bar (distribution) + [line if dates present] + table
//  BRIDGE → big_number (count) + table
//  OTHER  → pie | bar (distribution) + table
//
// Superset viz types chosen:
//  big_number_total         – KPI, no time-axis dependency
//  echarts_timeseries_line  – trend over date/time column
//  echarts_timeseries_bar   – distribution by category or time
//  pie                      – composition for low-cardinality categories (≤15 unique values)
//  table                    – always included as detail view
const selectChartsForTable = (table) => {
  const charts = [];
  const allUsable = table.columns.filter(c => isUsableColumn(c.name));
  const dateColumns = allUsable.filter(c => c.semanticType === "date");
  const metricCols = allUsable.filter(c => c.semanticType === "metric");
  const catCols = allUsable.filter(c => c.semanticType === "category");
  const boolCols = table.columns.filter(c => c.semanticType === "boolean");

  const isFact = /^(fact_|hecho_|fct_|ft_)/i.test(table.name);
  const isDim = /^(dim_|dimension_|d_)/i.test(table.name);
  const isBridge = /^(bridge_|br_|rel_|relacion_)/i.test(table.name);

  const hasValues = table.columns.some(c => c.values.some(v => v != null));
  const cardinality = (col) => hasValues
    ? new Set(col.values.filter(v => v != null)).size
    : null; // null = unknown (KTR-parsed, no sample data)

  // Business dates — exclude audit/ETL load timestamps
  const businessDates = dateColumns.filter(c =>
    !AUDIT_KEYWORDS.some(k => c.name.toUpperCase().includes(k))
  );

  // Real metric columns — exclude any ID-like numerics that slipped through
  const realMetrics = metricCols.filter(c => {
    const u = c.name.toUpperCase();
    return !u.startsWith("ID_") && !u.endsWith("_ID") &&
      !u.startsWith("SK_") && !u.startsWith("FK_");
  });
  const bestMetric = realMetrics[0] ?? metricCols[0];
  const bestMetricObj = bestMetric ? sumMetric(bestMetric.name) : countMetric;

  if (isBridge) {
    charts.push({ type: "big_number", columnName: null, label: "Total registros" });
    charts.push({ type: "table", columnName: (allUsable[0] ?? table.pickColumn).name, label: "Detalle" });
    return charts;
  }

  if (isFact) {
    // KPI for best metric
    charts.push({
      type: "big_number",
      columnName: bestMetric?.name ?? null,
      label: "KPI",
    });
    // Second KPI if available
    const second = realMetrics[1];
    if (second) {
      charts.push({ type: "big_number", columnName: second.name, label: "KPI" });
    }
    // Trend over time
    if (businessDates.length > 0 && bestMetric) {
      charts.push({
        type: "line",
        columnName: bestMetric.name,
        xAxis: businessDates[0].name,
        metric: bestMetricObj,
        label: "Evolución temporal",
      });
    }
    // Breakdown by category — excluir columnas técnicas no descriptivas
    const TECHNICAL_CAT_KEYWORDS = ["MONEDA", "CURRENCY", "ESTADO", "STATUS", "FLAG", "TIPO_CAMBIO", "ACTIVO"];
    const businessCatCols = catCols.filter(c =>
      !TECHNICAL_CAT_KEYWORDS.some(k => c.name.toUpperCase().includes(k))
    );
    if (businessCatCols.length > 0 && bestMetric) {
      charts.push({
        type: "bar",
        columnName: bestMetric.name,
        xAxis: businessCatCols[0].name,
        metric: bestMetricObj,
        label: "Por categoría",
      });
    }
    charts.push({ type: "table", columnName: (bestMetric ?? table.pickColumn).name, label: "Detalle", isMetric: !!bestMetric });
    return charts;
  }

  if (isDim) {
    // Dimensiones: solo pie/bar de distribución + tabla de detalle
    // NUNCA line chart — las dims no son series temporales

    const col = catCols[0] ?? table.pickColumn;
    const colName = col?.name ?? table.pickColumn.name;
    const uniqueCount = new Set(
      (col?.values ?? table.pickColumn.values).filter(v => v != null)
    ).size;

    const realMetrics = metricCols.filter(c => {
      const u = c.name.toUpperCase();
      return !u.startsWith("SK_") && !u.startsWith("FK_") &&
        !u.startsWith("ID_") && !u.endsWith("_ID") &&
        !u.startsWith("COD_") && !u.startsWith("BK_");
    });

    if (realMetrics.length > 0) {
      const bestMetric = realMetrics[0];
      const metricObj = {
        label: `SUM(${bestMetric.name})`,
        expressionType: "SQL",
        sqlExpression: `SUM(${bestMetric.name})`,
        hasCustomLabel: false,
        optionName: `metric_sum_${bestMetric.name}`,
      };
      if (uniqueCount <= 15) {
        charts.push({ type: "pie_with_metric", columnName: colName, metric: metricObj, label: "Distribución" });
      } else {
        charts.push({ type: "bar_with_metric", columnName: colName, metric: metricObj, xAxis: colName, label: "Distribución" });
      }
    } else {
      if (uniqueCount <= 15) {
        charts.push({ type: "pie", columnName: colName, label: "Distribución" });
      } else {
        charts.push({ type: "bar", columnName: colName, xAxis: colName, label: "Distribución" });
      }
    }
    charts.push({ type: "table", columnName: colName, label: "Detalle" });
    return charts;
  }

  // Generic / unknown table type — clasificación semántica por contenido, no por nombre
  // Caso A: tiene métricas reales + fechas → comportamiento fact-like
  if (realMetrics.length > 0 && businessDates.length > 0) {
    charts.push({ type: "big_number", columnName: bestMetric?.name ?? null, label: "KPI" });
    const second = realMetrics[1];
    if (second) charts.push({ type: "big_number", columnName: second.name, label: "KPI" });
    charts.push({
      type: "line",
      columnName: bestMetric.name,
      xAxis: businessDates[0].name,
      metric: bestMetricObj,
      label: "Evolución temporal",
    });
    if (catCols.length > 0) {
      charts.push({
        type: "bar",
        columnName: bestMetric.name,
        xAxis: catCols[0].name,
        metric: bestMetricObj,
        label: "Por categoría",
      });
    }
    charts.push({ type: "table", columnName: (bestMetric ?? table.pickColumn).name, label: "Detalle", isMetric: true });
    return charts;
  }

  // Caso B: tiene métricas reales sin fechas → KPI + bar por categoría + tabla
  if (realMetrics.length > 0) {
    charts.push({ type: "big_number", columnName: bestMetric?.name ?? null, label: "KPI" });
    const second = realMetrics[1];
    if (second) charts.push({ type: "big_number", columnName: second.name, label: "KPI" });
    if (catCols.length > 0) {
      charts.push({
        type: "bar",
        columnName: bestMetric.name,
        xAxis: catCols[0].name,
        metric: bestMetricObj,
        label: "Por categoría",
      });
    }
    charts.push({ type: "table", columnName: (bestMetric ?? table.pickColumn).name, label: "Detalle", isMetric: true });
    return charts;
  }

  // Caso C: tiene fechas sin métricas → line de COUNT + tabla
  if (businessDates.length > 0) {
    charts.push({
      type: "bar",
      columnName: table.pickColumn.name,
      xAxis: businessDates[0].name,
      metric: countMetric,
      label: "Evolución temporal",
    });
    charts.push({ type: "table", columnName: table.pickColumn.name, label: "Detalle" });
    return charts;
  }

  // Caso D: solo categorías → pie/bar según cardinalidad + tabla
  const col = catCols[0] ?? table.pickColumn;
  const card = cardinality(col);
  if (card !== null && card > 15) {
    charts.push({ type: "bar", columnName: col.name, xAxis: col.name, metric: countMetric, label: "Distribución" });
  } else {
    charts.push({ type: "pie", columnName: col.name, label: "Distribución" });
  }
  charts.push({ type: "table", columnName: col.name, label: "Detalle" });
  return charts;
};

// ── Dashboard layout builder ──────────────────────────────────────────────────
const buildDashboardConfig = ({ etlName, dashUuid, charts }) => {
  const rows = [];
  for (let i = 0; i < charts.length; i += 2) rows.push(charts.slice(i, i + 2));

  const position = {
    DASHBOARD_VERSION_KEY: "v2",
    ROOT_ID: { type: "ROOT", id: "ROOT_ID", children: ["GRID_ID"] },
    GRID_ID: { type: "GRID", id: "GRID_ID", children: rows.map((_, i) => `ROW-${i}`), parents: ["ROOT_ID"] },
  };

  rows.forEach((row, rowIdx) => {
    const rowId = `ROW-${rowIdx}`;
    const chartIds = row.map(c => `CHART-${c.chartUuid.slice(0, 8)}`);
    position[rowId] = {
      type: "ROW", id: rowId, children: chartIds,
      meta: { background: "BACKGROUND_TRANSPARENT" },
      parents: ["ROOT_ID", "GRID_ID"],
    };
    row.forEach((c, colIdx) => {
      const chartId = chartIds[colIdx];
      position[chartId] = {
        type: "CHART", id: chartId, children: [],
        meta: { width: 6, height: 50, chartId: 0, sliceName: c.sliceName, uuid: c.chartUuid },
        parents: ["ROOT_ID", "GRID_ID", rowId],
      };
    });
  });

  return {
    dashboard_title: `ETL - ${etlName}`,
    description: null,
    css: "",
    slug: null,
    uuid: dashUuid,
    position,
    metadata: {
      show_native_filters: true,
      default_filters: "{}",
      filter_scopes: {},
      expanded_slices: {},
      refresh_frequency: 0,
      timed_refresh_immune_slices: [],
      color_scheme: "",
      label_colors: {},
      shared_label_colors: {},
      cross_filters_enabled: false,
      global_chart_configuration: {},
      chart_configuration: {},
    },
    version: VERSION,
    is_managed_externally: false,
    external_url: null,
    certified_by: null,
    certification_details: null,
    published: false,
  };
};

const dashboardYaml = (cfg) => dump(buildDashboardConfig(cfg));

const slugify = (s) =>
  String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 60) || "etl";

// ── Main ZIP export ───────────────────────────────────────────────────────────
export async function generateSupersetZip(etl, sqlalchemyUri = "postgresql://user:password@host:5432/dwh") {
  let dwhSample = etl?.result?.dwh_sample ?? {};

  // Fallback 1: si dwh_sample está vacío O todas las filas están vacías, extraer desde el/los KTR.
  // Flujo de 2 KTR: las tablas DWH (dim_/fact_) viven en ktr2_xml (STG→DWH) — parsear ambos.
  const dwhSampleIsEmpty = !Object.keys(dwhSample).length ||
    Object.values(dwhSample).every(rows =>
      !rows.length || rows.every(row => !Object.keys(row ?? {}).length)
    );

  if (dwhSampleIsEmpty && etl?.result?.ktr_xml) {
    const ktrBlobs = [new Blob([etl.result.ktr_xml], { type: "application/xml" })];
    if (etl?.result?.ktr2_xml) {
      ktrBlobs.push(new Blob([etl.result.ktr2_xml], { type: "application/xml" }));
    }
    dwhSample = await extractDwhSchemaFromKtrs(ktrBlobs);
  }

  // Fallback 1b: si fact_ventas no está en dwhSample pero sí stg_detalle_facturas,
  // construir fact_ventas sintética con las columnas esperadas del DWH
  if (!dwhSample['fact_ventas'] && (dwhSample['stg_detalle_facturas'] || dwhSample['stg_facturas'])) {
    dwhSample['fact_ventas'] = [{
      sk_venta: 1,
      fk_cliente: 1,
      fk_producto: 1,
      fk_vendedor: 1,
      fk_tiempo: 1,
      nro_factura: "ejemplo",
      cantidad: 0.0,
      precio_unitario: 0.0,
      descuento_pct: 0.0,
      subtotal_linea: 0.0,
      monto_impuestos: 0.0,
      total_factura: 0.0,
      moneda: "ejemplo",
      tipo_cambio: 1.0,
      fecha_carga_dwh: "2024-01-01",
    }];
  }

  console.log('dwhSample final:', JSON.stringify(dwhSample));

  // Fallback 2: si el KTR tampoco dio resultados, usar el dwhModel del formulario
  if (!Object.keys(dwhSample).length && etl?.formData?.dwhModel?.tables?.length) {
    for (const table of etl.formData.dwhModel.tables) {
      const tableName = table.nombre?.toLowerCase();
      if (!tableName) continue;
      const row = {};
      for (const col of table.columnas ?? []) {
        const colName = col.nombre?.toLowerCase();
        if (!colName) continue;
        row[colName] = _syntheticValue(col.nombre);
      }
      if (Object.keys(row).length) dwhSample[tableName] = [row];
    }
  }

  const tables = buildTables(dwhSample, etl?.formData?.dwhModel ?? null);
  console.log('dwh_sample:', JSON.stringify(dwhSample));
  console.log('dwhModel tables:', etl?.formData?.dwhModel?.tables?.map(t => t.nombre));
  console.log('tables count:', tables.length);
  if (!tables.length) throw new Error("No hay datos en el DWH para exportar a Superset.");

  const zip = new JSZip();
  const folder = zip.folder(`etl_${slugify(etl.name)}_export`);
  const dbUuid = DB_UUID;
  // UUIDs deterministas: mismo ETL + misma tabla/chart → mismo UUID en cada exportación
  const etlSeed = String(etl.id ?? etl.name ?? "etl");
  const dashUuid = deterministicUUID(`${etlSeed}:dashboard`);
  const allCharts = [];

  folder.file("metadata.yaml", metadataYaml());
  folder.file(`databases/${DB_NAME}.yaml`, databaseYaml(dbUuid, sqlalchemyUri));

  for (const table of tables) {
    const dsUuid = deterministicUUID(`${etlSeed}:dataset:${table.name}`);
    folder.file(`datasets/${DB_NAME}/${table.name}.yaml`, datasetYaml(table, dsUuid, dbUuid));

    for (const spec of selectChartsForTable(table)) {
      const chartUuid = deterministicUUID(`${etlSeed}:chart:${table.name}:${spec.type}:${spec.columnName ?? ""}:${spec.xAxis ?? ""}`);
      const normalizeLabel = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
      const chartLabel = spec.type === "line"
        ? normalizeLabel(`${table.name} - ${spec.columnName} por ${spec.xAxis} (${spec.label})`)
        : normalizeLabel(`${table.name} - ${spec.xAxis ?? spec.columnName ?? spec.label} (${spec.label})`);
      const common = { tableName: table.name, columnName: spec.columnName, dsUuid, chartUuid, sliceName: chartLabel };

      let yamlContent;
      if (spec.type === "table") yamlContent = tableChartYaml({ ...common, isMetric: spec.isMetric ?? false });
      else if (spec.type === "pie") yamlContent = pieChartYaml(common);
      else if (spec.type === "pie_with_metric") yamlContent = pieChartYaml({ ...common, metric: spec.metric });
      else if (spec.type === "bar") yamlContent = barChartYaml({ ...common, xAxis: spec.xAxis, metric: spec.metric });
      else if (spec.type === "bar_with_metric") yamlContent = barChartYaml({ ...common, xAxis: spec.xAxis ?? spec.columnName, metric: spec.metric });
      else if (spec.type === "line") yamlContent = lineChartYaml({ ...common, xAxis: spec.xAxis, metric: spec.metric });
      else if (spec.type === "big_number") yamlContent = bigNumberYaml(common);

      if (!yamlContent) continue;
      folder.file(`charts/${slugify(chartLabel)}_${chartUuid.slice(0, 8)}.yaml`, yamlContent);
      allCharts.push({ chartUuid, sliceName: chartLabel });
    }
  }

  folder.file(
    `dashboards/${slugify(etl.name)}_${dashUuid.slice(0, 8)}.yaml`,
    dashboardYaml({ etlName: etl.name, dashUuid, charts: allCharts }),
  );

  folder.file("README.md",
    `# Dashboard Superset - ${etl.name}\n\n` +
    `Importar en Superset: Settings → Import Dashboards → seleccionar este ZIP.\n` +
    `Si la URI no está configurada, editar en Settings → Database Connections → ${DB_NAME}.\n\n` +
    `Tablas: ${tables.map(t => t.name).join(", ")}\n` +
    `Charts: ${allCharts.length}\n`
  );

  return await zip.generateAsync({ type: "blob" });
}
