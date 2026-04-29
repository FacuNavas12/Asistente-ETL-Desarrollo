import { useParams, useNavigate } from "react-router-dom";
import { useEtl } from "../context/EtlContext";
import Layout from "../components/Layout";
import "../css/etlDetail.css";

const LABELS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun"];

function BarChart({ data }) {
  const max = Math.max(...data);
  return (
    <svg className="bar-chart" viewBox="0 0 310 180" xmlns="http://www.w3.org/2000/svg">
      {data.map((val, i) => {
        const barH = Math.max((val / max) * 130, 4);
        const x = 10 + i * 48;
        const y = 148 - barH;
        return (
          <g key={i}>
            <rect x={x} y={y} width="34" height={barH} rx="5" fill="var(--accent)" opacity="0.82" />
            <text x={x + 17} y={y - 6} textAnchor="middle" fontSize="11" fill="var(--text)" fontFamily="system-ui">
              {val}
            </text>
            <text x={x + 17} y="166" textAnchor="middle" fontSize="10" fill="var(--text)" fontFamily="system-ui">
              {LABELS[i]}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function EtlDetail() {
  const { id } = useParams();
  const { etls } = useEtl();
  const navigate = useNavigate();
  const etl = etls.find(e => e.id === id);

  if (!etl) {
    return (
      <Layout>
        <div className="etl-detail-notfound">
          ETL no encontrado.
          <button onClick={() => navigate("/home")}>Volver al inicio</button>
        </div>
      </Layout>
    );
  }

  return (
    <Layout>
      <div className="etl-detail">
        <div className="etl-detail__header">
          <h1 className="etl-detail__title">{etl.name}</h1>
          <span className="etl-detail__date">
            {new Date(etl.createdAt).toLocaleDateString("es-AR", { dateStyle: "long" })}
          </span>
        </div>

        <div className="etl-detail__body">
          <div className="etl-detail__chart-box">
            <h2>Registros procesados por período</h2>
            <BarChart data={etl.result.chartData} />
          </div>

          <div className="etl-detail__explanation">
            {etl.result.explanation.map((p, i) => (
              <p key={i}>{p}</p>
            ))}
          </div>
        </div>
      </div>
    </Layout>
  );
}
