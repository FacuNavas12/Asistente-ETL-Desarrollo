import "@/styles/etlResult.css";

export default function ChartPanel({ data }) {
  return (
    <div className="result-card">
      <h2 className="result-title">GrÃ¡fica</h2>
      <div className="chart-placeholder">
        {data ? "AquÃ­ irÃ¡ la grÃ¡fica real" : "Procesando..."}
      </div>
    </div>
  );
}
