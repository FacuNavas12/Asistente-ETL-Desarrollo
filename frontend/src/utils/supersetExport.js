import JSZip from "jszip";
import yaml from "js-yaml";

const VERSION = "1.0.0";
const DB_NAME = "ETL_DWH";
const DB_SCHEMA = "public";

const dumpOpts = { noRefs: true, lineWidth: -1, sortKeys: false };
const dump = (obj) => yaml.dump(obj, dumpOpts);

const uuid = () => crypto.randomUUID();

const isUsableColumn = (name) => {
  if (!name) return false;
  const upper = String(name).toUpperCase();
  if (upper.startsWith("SK_")) return false;
  if (upper.startsWith("FK_")) return false;
  if (upper === "ID" || upper.endsWith("_ID")) return false;
  return true;
};

// Cambio 1: inferencia de tipo semántico por nombre y valores
const inferSemanticType = (name, values) => {
  const upper = String(name).toUpperCase();
  const sample = values.find(v => v !== null && v !== undefined && v !== "");

  if (upper === "ID" || upper.endsWith("_ID") || upper.startsWith("SK_") || upper.startsWith("FK_")) {
    return "id";
  }
  if (typeof sample === "boolean") return "boolean";

  const dateKeywords = ["FECHA", "DATE", "DT", "ANIO", "MES", "TRIMESTRE", "DIA", "YEAR", "MONTH", "DAY"];
  if (dateKeywords.some(k => upper.includes(k))) return "date";
  if (typeof sample === "string" && /^\d{4}-\d{2}(-\d{2})?$/.test(sample)) return "date";

  const metricKeywords = ["MONTO", "IMPORTE", "TOTAL", "PRECIO", "CANTIDAD", "QTY", "AMOUNT",
                          "INGRESO", "EGRESO", "COSTO", "VENTA", "COMPRA", "REVENUE",
                          "DESCUENTO", "IMPUESTO", "NETO", "BRUTO", "SALDO", "COUNT"];
  if (typeof sample === "number" && metricKeywords.some(k => upper.includes(k))) return "metric";
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

const buildTables = (dwhSample = {}) =>
  Object.entries(dwhSample)
    .map(([name, rows]) => {
      if (!Array.isArray(rows) || !rows.length) return null;
      const columnNames = Array.from(rows.reduce((set, row) => {
        Object.keys(row ?? {}).forEach(k => set.add(k));
        return set;
      }, new Set()));
      // Cambio 2: cada columna incluye su tipo semántico
      const columns = columnNames.map(col => ({
        name: col,
        values: rows.map(r => r?.[col]),
        semanticType: inferSemanticType(col, rows.map(r => r?.[col])),
      }));
      const pickColumn =
        columns.find(c => isUsableColumn(c.name) && c.values.some(v => v !== null && v !== undefined && v !== "")) ??
        columns.find(c => c.values.some(v => v !== null && v !== undefined && v !== ""));
      return pickColumn ? { name, columns, pickColumn } : null;
    })
    .filter(Boolean);

const metadataYaml = () => dump({
  version: VERSION,
  type: "Dashboard",
  timestamp: new Date().toISOString(),
});

// FIX 4: sqlalchemyUri como parámetro; extra como dict YAML (no JSON string)
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
  extra: {
    allows_virtual_table_explore: true,
    schemas_allowed_for_csv_upload: [],
    engine_params: {},
    metadata_params: {},
  },
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
  metrics: [
    {
      metric_name: "count",
      verbose_name: "COUNT(*)",
      metric_type: "count",
      expression: "COUNT(*)",
      description: null,
      d3format: null,
      extra: null,
      warning_text: null,
    },
  ],
  columns: table.columns.map(c => ({
    column_name: c.name,
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

// FIX 2: expressionType "SQL" con sqlExpression evita el error
// "Cannot compile Column object until its 'name' is assigned" de SQLAlchemy
const countMetric = {
  label: "COUNT(*)",
  expressionType: "SQL",
  sqlExpression: "COUNT(*)",
  hasCustomLabel: false,
  optionName: "metric_count",
};

// Cambio 3: selección inteligente de charts según tipo de tabla y columnas
const selectChartsForTable = (table) => {
  const charts = [];

  const dateColumns     = table.columns.filter(c => c.semanticType === "date"     && isUsableColumn(c.name));
  const metricColumns   = table.columns.filter(c => c.semanticType === "metric"   && isUsableColumn(c.name));
  const categoryColumns = table.columns.filter(c => c.semanticType === "category" && isUsableColumn(c.name));

  const isFact = table.name.toLowerCase().startsWith("fact_") || table.name.toLowerCase().startsWith("hecho_");
  const isDim  = table.name.toLowerCase().startsWith("dim_")  || table.name.toLowerCase().startsWith("dimension_");

  if (isFact) {
    if (metricColumns.length > 0) {
      charts.push({ type: "big_number", columnName: metricColumns[0].name, label: "KPI" });
    }
    if (dateColumns.length > 0 && metricColumns.length > 0) {
      charts.push({ type: "line", columnName: metricColumns[0].name, xAxis: dateColumns[0].name, label: "Evolución temporal" });
    }
    if (categoryColumns.length > 0 && metricColumns.length > 0 && dateColumns.length === 0) {
      charts.push({ type: "bar", columnName: metricColumns[0].name, xAxis: categoryColumns[0].name, label: "Por categoría" });
    }
    charts.push({ type: "table", columnName: metricColumns[0]?.name ?? table.pickColumn.name, label: "Detalle" });
    return charts;
  }

  if (isDim) {
    const col = categoryColumns[0] ?? dateColumns[0] ?? table.pickColumn;
    const colName = col?.name ?? table.pickColumn.name;
    const uniqueCount = new Set(col?.values?.filter(v => v != null) ?? []).size;
    if (uniqueCount <= 10) {
      charts.push({ type: "pie", columnName: colName, label: "Distribución" });
    } else {
      charts.push({ type: "bar", columnName: colName, xAxis: colName, label: "Distribución" });
    }
    charts.push({ type: "table", columnName: colName, label: "Detalle" });
    return charts;
  }

  // Tabla genérica
  const col = table.pickColumn;
  const uniqueCount = new Set(col.values.filter(v => v != null)).size;
  if (uniqueCount <= 10) {
    charts.push({ type: "pie", columnName: col.name, label: "Distribución" });
  } else {
    charts.push({ type: "bar", columnName: col.name, xAxis: col.name, label: "Distribución" });
  }
  charts.push({ type: "table", columnName: col.name, label: "Detalle" });
  return charts;
};

// FIX 1: params como objeto directo (YAML dict), no JSON string
const tableChartYaml = ({ tableName, columnName, dsUuid, chartUuid }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "table",
    url_params: {},
    time_grain_sqla: null,
    time_range: "No filter",
    query_mode: "aggregate",
    groupby: [columnName],
    metrics: [countMetric],
    all_columns: [],
    percent_metrics: [],
    adhoc_filters: [],
    order_by_cols: [],
    order_desc: true,
    row_limit: 10000,
    include_time: false,
    show_cell_bars: true,
    align_pn: false,
    page_length: 25,
    include_search: true,
    extra_form_data: {},
  };
  return dump({
    slice_name: `${tableName} - ${columnName} (Tabla)`,
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

// FIX 1: params como objeto directo (YAML dict), no JSON string
const pieChartYaml = ({ tableName, columnName, dsUuid, chartUuid }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "pie",
    url_params: {},
    time_range: "No filter",
    metric: countMetric,
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
    slice_name: `${tableName} - ${columnName} (Torta)`,
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

const buildDashboardConfig = ({ etlName, dashUuid, charts }) => {
  const rows = [];
  for (let i = 0; i < charts.length; i += 2) {
    rows.push(charts.slice(i, i + 2));
  }

  const position = {
    DASHBOARD_VERSION_KEY: "v2",
    ROOT_ID: {
      type: "ROOT",
      id: "ROOT_ID",
      children: ["GRID_ID"],
    },
    GRID_ID: {
      type: "GRID",
      id: "GRID_ID",
      children: rows.map((_, idx) => `ROW-${idx}`),
      parents: ["ROOT_ID"],
    },
  };

  rows.forEach((row, rowIdx) => {
    const rowId = `ROW-${rowIdx}`;
    const chartIds = row.map(c => `CHART-${c.chartUuid.slice(0, 8)}`);
    position[rowId] = {
      type: "ROW",
      id: rowId,
      children: chartIds,
      meta: { background: "BACKGROUND_TRANSPARENT" },
      parents: ["ROOT_ID", "GRID_ID"],
    };
    row.forEach((c, colIdx) => {
      const chartId = chartIds[colIdx];
      position[chartId] = {
        type: "CHART",
        id: chartId,
        children: [],
        meta: {
          width: 6,
          height: 50,
          chartId: 0,
          sliceName: c.sliceName,
          uuid: c.chartUuid,
        },
        parents: ["ROOT_ID", "GRID_ID", rowId],
      };
    });
  });

  const metadata = {
    show_native_filters: true,
    default_filters: "{}",  // FIX 3: string JSON, Superset llama json.loads() sobre este valor
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
  };

  return {
    dashboard_title: `ETL - ${etlName}`,
    description: null,
    css: "",
    slug: null,
    uuid: dashUuid,
    position,
    metadata,
    version: VERSION,
    is_managed_externally: false,
    external_url: null,
    certified_by: null,
    certification_details: null,
    published: false,
  };
};

// Cambio 4: nuevos tipos de chart
const lineChartYaml = ({ tableName, columnName, xAxis, dsUuid, chartUuid }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "echarts_timeseries_line",
    x_axis: xAxis,
    metrics: [countMetric],
    groupby: [],
    adhoc_filters: [],
    row_limit: 10000,
    time_range: "No filter",
    color_scheme: "supersetColors",
    extra_form_data: {},
  };
  return dump({
    slice_name: `${tableName} - ${columnName} (Línea)`,
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

const bigNumberYaml = ({ tableName, columnName, dsUuid, chartUuid }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "big_number_total",
    metric: countMetric,
    adhoc_filters: [],
    time_range: "No filter",
    extra_form_data: {},
  };
  return dump({
    slice_name: `${tableName} - ${columnName} (KPI)`,
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

const dashboardYaml = (cfg) => dump(buildDashboardConfig(cfg));

const slugify = (s) =>
  String(s).normalize("NFD").replace(/[̀-ͯ]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 60) || "etl";

// FIX 4: sqlalchemyUri como parámetro opcional (default: placeholder)
export async function generateSupersetZip(etl, sqlalchemyUri = "postgresql://user:password@host:5432/dwh") {
  const dwhSample = etl?.result?.dwh_sample ?? {};
  const tables = buildTables(dwhSample);
  if (!tables.length) {
    throw new Error("No hay datos en el DWH para exportar a Superset.");
  }

  const zip = new JSZip();
  const root = `etl_${slugify(etl.name)}_export`;
  const folder = zip.folder(root);

  const dbUuid = uuid();
  const dashUuid = uuid();
  const charts = [];

  folder.file("metadata.yaml", metadataYaml());
  folder.file(`databases/${DB_NAME}.yaml`, databaseYaml(dbUuid, sqlalchemyUri));

  // Cambio 5: selección inteligente de charts según tipos semánticos
  for (const table of tables) {
    const dsUuid = uuid();
    folder.file(`datasets/${DB_NAME}/${table.name}.yaml`, datasetYaml(table, dsUuid, dbUuid));

    const chartSpecs = selectChartsForTable(table);

    for (const spec of chartSpecs) {
      const chartUuid = uuid();
      const chartLabel = `${table.name} - ${spec.columnName} (${spec.label})`;

      let yamlContent;
      if (spec.type === "table") {
        yamlContent = tableChartYaml({ tableName: table.name, columnName: spec.columnName, dsUuid, chartUuid });
      } else if (spec.type === "pie") {
        yamlContent = pieChartYaml({ tableName: table.name, columnName: spec.columnName, dsUuid, chartUuid });
      } else if (spec.type === "line") {
        yamlContent = lineChartYaml({ tableName: table.name, columnName: spec.columnName, xAxis: spec.xAxis, dsUuid, chartUuid });
      } else if (spec.type === "big_number") {
        yamlContent = bigNumberYaml({ tableName: table.name, columnName: spec.columnName, dsUuid, chartUuid });
      } else if (spec.type === "bar") {
        // bar usa tableChartYaml como fallback hasta implementar barChartYaml completo
        yamlContent = tableChartYaml({ tableName: table.name, columnName: spec.columnName, dsUuid, chartUuid });
      }

      folder.file(
        `charts/${slugify(chartLabel)}_${chartUuid.slice(0, 8)}.yaml`,
        yamlContent,
      );
      charts.push({ chartUuid, sliceName: chartLabel });
    }
  }

  folder.file(
    `dashboards/${slugify(etl.name)}_${dashUuid.slice(0, 8)}.yaml`,
    dashboardYaml({ etlName: etl.name, dashUuid, charts }),
  );

  const readme = `# Dashboard Superset - ${etl.name}

Importar en Superset:
1. Settings -> Import Dashboards -> seleccionar este ZIP.
2. Si la URI de base de datos no está configurada, editar en Settings -> Database Connections -> ETL_DWH.

Tablas incluidas: ${tables.map(t => t.name).join(", ")}
Charts generados: ${charts.length} (1 tabla + 1 torta por tabla).
`;
  folder.file("README.md", readme);

  return await zip.generateAsync({ type: "blob" });
}
