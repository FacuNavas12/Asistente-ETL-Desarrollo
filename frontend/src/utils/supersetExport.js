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
  if (upper === "ID" || upper.endsWith("_ID")) return false;
  return true;
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
      const columns = columnNames.map(col => ({
        name: col,
        values: rows.map(r => r?.[col]),
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

const databaseYaml = (dbUuid) => dump({
  database_name: DB_NAME,
  sqlalchemy_uri: "postgresql://user:password@host:5432/dwh",
  cache_timeout: null,
  expose_in_sqllab: true,
  allow_run_async: false,
  allow_ctas: false,
  allow_cvas: false,
  allow_dml: false,
  allow_file_upload: false,
  extra: JSON.stringify({ allows_virtual_table_explore: true }),
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

const countMetric = {
  label: "COUNT(*)",
  expressionType: "SIMPLE",
  column: null,
  aggregate: "COUNT",
  hasCustomLabel: false,
  sqlExpression: null,
  isNew: false,
  optionName: "metric_count",
};

const barChartYaml = ({ tableName, columnName, dsUuid, chartUuid }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "dist_bar",
    slice_id: null,
    url_params: {},
    granularity_sqla: null,
    time_grain_sqla: null,
    time_range: "No filter",
    metrics: [countMetric],
    adhoc_filters: [],
    groupby: [columnName],
    columns: [],
    row_limit: 10000,
    color_scheme: "supersetColors",
    show_legend: true,
    rich_tooltip: true,
    bar_stacked: false,
    y_axis_format: "SMART_NUMBER",
    extra_form_data: {},
  };
  return dump({
    slice_name: `${tableName} - ${columnName} (Barras)`,
    description: null,
    certified_by: null,
    certification_details: null,
    viz_type: "dist_bar",
    params: JSON.stringify(params),
    query_context: null,
    cache_timeout: null,
    uuid: chartUuid,
    version: VERSION,
    dataset_uuid: dsUuid,
    is_managed_externally: false,
    external_url: null,
  });
};

const pieChartYaml = ({ tableName, columnName, dsUuid, chartUuid }) => {
  const params = {
    datasource: `${dsUuid}__table`,
    viz_type: "pie",
    slice_id: null,
    url_params: {},
    granularity_sqla: null,
    time_grain_sqla: null,
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
    params: JSON.stringify(params),
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

const dashboardYaml = (cfg) => dump(buildDashboardConfig(cfg));

const slugify = (s) =>
  String(s).normalize("NFD").replace(/[\u0300-\u036f]/g, "")
    .replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_|_$/g, "").slice(0, 60) || "etl";

export async function generateSupersetZip(etl) {
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
  folder.file(`databases/${DB_NAME}.yaml`, databaseYaml(dbUuid));

  for (const table of tables) {
    const dsUuid = uuid();
    folder.file(`datasets/${DB_NAME}/${table.name}.yaml`, datasetYaml(table, dsUuid, dbUuid));

    const barUuid = uuid();
    const pieUuid = uuid();
    const barName = `${table.name} - ${table.pickColumn.name} (Barras)`;
    const pieName = `${table.name} - ${table.pickColumn.name} (Torta)`;

    folder.file(
      `charts/${slugify(barName)}_${barUuid.slice(0, 8)}.yaml`,
      barChartYaml({ tableName: table.name, columnName: table.pickColumn.name, dsUuid, chartUuid: barUuid }),
    );
    folder.file(
      `charts/${slugify(pieName)}_${pieUuid.slice(0, 8)}.yaml`,
      pieChartYaml({ tableName: table.name, columnName: table.pickColumn.name, dsUuid, chartUuid: pieUuid }),
    );

    charts.push({ chartUuid: barUuid, sliceName: barName });
    charts.push({ chartUuid: pieUuid, sliceName: pieName });
  }

  folder.file(
    `dashboards/${slugify(etl.name)}_${dashUuid.slice(0, 8)}.yaml`,
    dashboardYaml({ etlName: etl.name, dashUuid, charts }),
  );

  const readme = `# Dashboard Superset - ${etl.name}

Antes de importar:
1. Editar databases/${DB_NAME}.yaml y reemplazar sqlalchemy_uri por la URI real de tu DWH.
2. En Superset: Settings -> Import Dashboards -> seleccionar este ZIP.
3. Confirmar la base de datos cuando Superset lo solicite.

Tablas incluidas: ${tables.map(t => t.name).join(", ")}
Charts generados: ${charts.length} (1 barra + 1 torta por tabla).
`;
  folder.file("README.md", readme);

  return await zip.generateAsync({ type: "blob" });
}
