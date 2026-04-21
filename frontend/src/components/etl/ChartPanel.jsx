import "../../css/etlResult.css";

export default function ChartPanel({ data }) {
  return (
    <div className="result-card">
      <h2 className="result-title">Gráfica</h2>
      <div className="chart-placeholder">
        {data ? "Aquí irá la gráfica real" : "Procesando..."}
      </div>
    </div>
  );
}