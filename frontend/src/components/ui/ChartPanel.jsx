import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer,
  PieChart, Pie, Cell, Legend, CartesianGrid,
} from "recharts";
import "@/styles/etlResult.css";

const VALIDATION_COLORS = { error: "#ef4444", warning: "#f59e0b", info: "#3b82f6" };
const STEP_COLOR = "#6366f1";

function countBy(items, key) {
  const map = new Map();
  for (const it of items) {
    const k = it[key] ?? "Otro";
    map.set(k, (map.get(k) ?? 0) + 1);
  }
  return [...map.entries()].map(([name, value]) => ({ name, value }));
}

export default function ChartPanel({ data }) {
  const steps = data?.proceso_etl?.steps ?? [];
  const validaciones = data?.validaciones ?? [];

  if (!data) {
    return (
      <div className="result-card">
        <h2 className="result-title">Gráfica</h2>
        <div className="chart-placeholder">Procesando...</div>
      </div>
    );
  }

  const stepsByType = countBy(steps, "tipo_step_pdi");
  const validationsByType = countBy(validaciones, "tipo");
  const stepsByOrder = steps
    .slice()
    .sort((a, b) => a.orden - b.orden)
    .map(s => ({ name: `${s.orden}. ${s.nombre}`, tipo: s.tipo_step_pdi, value: 1 }));

  return (
    <div className="result-card">
      <h2 className="result-title">Visualización del ETL</h2>

      <div className="chart-grid">
        <div className="chart-block">
          <h3 className="chart-block__title">Tipos de step PDI</h3>
          <ResponsiveContainer width="100%" height={260}>
            <BarChart data={stepsByType}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="name" />
              <YAxis allowDecimals={false} />
              <Tooltip />
              <Bar dataKey="value" fill={STEP_COLOR} radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>

        <div className="chart-block">
          <h3 className="chart-block__title">Validaciones</h3>
          {validationsByType.length === 0 ? (
            <div className="chart-empty">Sin validaciones</div>
          ) : (
            <ResponsiveContainer width="100%" height={260}>
              <PieChart>
                <Pie
                  data={validationsByType}
                  dataKey="value"
                  nameKey="name"
                  innerRadius={50}
                  outerRadius={90}
                  paddingAngle={3}
                  label
                >
                  {validationsByType.map((entry) => (
                    <Cell key={entry.name} fill={VALIDATION_COLORS[entry.name] ?? "#9ca3af"} />
                  ))}
                </Pie>
                <Tooltip />
                <Legend />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>

        <div className="chart-block chart-block--full">
          <h3 className="chart-block__title">Pasos por orden de ejecución</h3>
          <table className="steps-table">
            <thead>
              <tr>
                <th className="steps-table__th steps-table__th--num">#</th>
                <th className="steps-table__th">Operación</th>
                <th className="steps-table__th">Step PDI</th>
              </tr>
            </thead>
            <tbody>
              {stepsByOrder.map((s, i) => (
                <tr key={i} className="steps-table__row">
                  <td className="steps-table__td steps-table__td--num">{s.name.split(".")[0]}</td>
                  <td className="steps-table__td">{s.name.replace(/^\d+\.\s*/, "")}</td>
                  <td className="steps-table__td steps-table__td--tipo">{s.tipo}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
