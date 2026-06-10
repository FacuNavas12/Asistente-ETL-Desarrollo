import "@/styles/etlResult.css";

export default function ExplanationPanel({ text }) {
  return (
    <div className="result-card">
      <h2 className="result-title">Explicacion</h2>
      <p className="result-text">{text}</p>
    </div>
  );
}
