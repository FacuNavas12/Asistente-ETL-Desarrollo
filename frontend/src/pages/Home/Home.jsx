import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import { ETL_STATUS } from "@/constants/etlStatus";
import Layout from "@/components/layout/Layout";
import "./Home.css";

const CARD_ICONS = ["⚡", "🔄", "📊", "🔗", "🗃️", "⚙️", "🧩", "📦"];

function EtlCard({ etl, index, onClick }) {
  const status = ETL_STATUS[etl.status] ?? ETL_STATUS.done;
  const action = etl.status === ETL_STATUS.pending.key ? "Continuar →" : "Ver detalle →";

  return (
    <div
      className="etl-card"
      style={{ animationDelay: `${index * 60}ms` }}
      onClick={onClick}
    >
      <div className="etl-card__icon">
        {CARD_ICONS[index % CARD_ICONS.length]}
      </div>
      <span className="etl-card__name">{etl.name}</span>
      <span className="etl-card__date">
        {new Date(etl.createdAt).toLocaleDateString("es-AR", { dateStyle: "medium" })}
      </span>
      <span
        className="etl-card__status"
        style={{ "--status-color": status.color }}
      >
        {status.label}
      </span>
      <div className="etl-card__footer">
        <span className="etl-card__action">{action}</span>
      </div>
    </div>
  );
}

export default function Home() {
  const navigate = useNavigate();
  const { etls } = useEtl();

  return (
    <Layout>
      <div className="home-page">
        <div className="home-header">
          <h1 className="home-title">Inicio</h1>
          <div className="home-count">
            <span className="home-count__label">ETLs creados</span>
            <span className="home-count__badge">{etls.length}</span>
          </div>
        </div>

        {etls.length === 0 ? (
          <div className="home-empty">
            <span className="home-empty__icon">📋</span>
            <p>No hay ETLs creados todavía.</p>
            <p className="home-empty__sub">
              Usá el botón + en la barra lateral para crear tu primer ETL.
            </p>
          </div>
        ) : (
          <div className="home-grid">
            {etls.map((etl, i) => (
              <EtlCard
                key={etl.id}
                etl={etl}
                index={i}
                onClick={() => navigate(`/etl/${etl.id}`)}
              />
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
