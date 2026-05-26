import { useMemo, useState } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, CartesianGrid,
} from "recharts";
import "@/styles/etlResult.css";

const PIE_COLORS = [
  "#6366f1", "#22c55e", "#f59e0b", "#ef4444", "#06b6d4",
  "#a855f7", "#ec4899", "#14b8a6", "#f97316", "#84cc16",
];

function buildDistribution(values) {
  const map = new Map();
  for (const raw of values) {
    const v = raw === "" || raw === null || raw === undefined ? "(vacío)" : String(raw);
    map.set(v, (map.get(v) ?? 0) + 1);
  }
  return [...map.entries()]
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);
}

function buildTablesFromSample(dwhSample) {
  return Object.entries(dwhSample ?? {})
    .map(([name, rows]) => {
      if (!Array.isArray(rows) || !rows.length) return null;
      const columnNames = Array.from(rows.reduce((set, row) => {
        Object.keys(row ?? {}).forEach(k => set.add(k));
        return set;
      }, new Set()));
      const columns = columnNames.map(col => ({
        name: col,
        data: rows.map(r => r?.[col] ?? ""),
      }));
      return { name, columns, rows };
    })
    .filter(Boolean);
}

export default function DataChartPanel({ dwhSample = {}, origenTables = [] }) {
  const tables = useMemo(() => {
    const fromDwh = buildTablesFromSample(dwhSample);
    if (fromDwh.length) return fromDwh;
    return (origenTables ?? [])
      .filter(t => t.columns?.some(c => c.data?.length))
      .map(t => ({
        name: t.tableName,
        columns: (t.columns ?? [])
          .filter(c => c.data?.length)
          .map(c => ({ name: c.name, data: c.data })),
        rows: null,
      }));
  }, [dwhSample, origenTables]);

  const [tableIdx, setTableIdx]   = useState(0);
  const [columnIdx, setColumnIdx] = useState(0);
  const [chartType, setChartType] = useState("bar");

  if (!tables.length) {
    return (
      <div className="result-card">
        <h2 className="result-title">Datos cargados en el DWH</h2>
        <div className="chart-placeholder">No hay datos para graficar</div>
      </div>
    );
  }

  const table  = tables[Math.min(tableIdx, tables.length - 1)];
  const column = table.columns[Math.min(columnIdx, table.columns.length - 1)];
  const distribution = column ? buildDistribution(column.data) : [];

  return (
    <div className="result-card">
      <h2 className="result-title">Datos cargados en el DWH</h2>

      <div className="data-chart-controls">
        <label className="data-chart-control">
          <span>Tabla DWH</span>
          <select
            value={tableIdx}
            onChange={e => { setTableIdx(Number(e.target.value)); setColumnIdx(0); }}
          >
            {tables.map((t, i) => (
              <option key={t.name ?? i} value={i}>{t.name}</option>
            ))}
          </select>
        </label>

        <label className="data-chart-control">
          <span>Columna</span>
          <select
            value={columnIdx}
            onChange={e => setColumnIdx(Number(e.target.value))}
          >
            {table.columns.map((c, i) => (
              <option key={c.name ?? i} value={i}>{c.name}</option>
            ))}
          </select>
        </label>

        <div className="data-chart-toggle">
          <button
            className={`data-chart-toggle__btn ${chartType === "bar" ? "is-active" : ""}`}
            onClick={() => setChartType("bar")}
          >
            Barras
          </button>
          <button
            className={`data-chart-toggle__btn ${chartType === "pie" ? "is-active" : ""}`}
            onClick={() => setChartType("pie")}
          >
            Torta
          </button>
        </div>
      </div>

      {distribution.length === 0 ? (
        <div className="chart-placeholder">Sin datos</div>
      ) : chartType === "bar" ? (
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={distribution}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="name" />
            <YAxis allowDecimals={false} />
            <Tooltip />
            <Bar dataKey="value" fill={PIE_COLORS[0]} radius={[6, 6, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      ) : (
        <ResponsiveContainer width="100%" height={320}>
          <PieChart>
            <Pie
              data={distribution}
              dataKey="value"
              nameKey="name"
              innerRadius={60}
              outerRadius={110}
              paddingAngle={3}
              label
            >
              {distribution.map((entry, i) => (
                <Cell key={entry.name} fill={PIE_COLORS[i % PIE_COLORS.length]} />
              ))}
            </Pie>
            <Tooltip />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      )}

      {table.rows && (
        <details className="data-chart-rows">
          <summary>Ver filas de {table.name} ({table.rows.length})</summary>
          <div className="data-chart-rows__scroll">
            <table className="data-chart-rows__table">
              <thead>
                <tr>{table.columns.map(c => <th key={c.name}>{c.name}</th>)}</tr>
              </thead>
              <tbody>
                {table.rows.map((row, i) => (
                  <tr key={i}>
                    {table.columns.map(c => <td key={c.name}>{String(row?.[c.name] ?? "")}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      )}
    </div>
  );
}
