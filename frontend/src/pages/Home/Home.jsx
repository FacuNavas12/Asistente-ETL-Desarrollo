import { useAuth0 } from "@auth0/auth0-react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import "./Home.css";

function EtlCard({ etl, onClick }) {
  return (
    <div className="etl-card" onClick={onClick}>
      <span className="etl-card__name">{etl.name}</span>
      <span className="etl-card__date">
        {new Date(etl.createdAt).toLocaleDateString("es-AR", { dateStyle: "medium" })}
      </span>
    </div>
  );
}

export default function Home() {
  const { user } = useAuth0();
  const navigate = useNavigate();
  const { etls, draft, clearDraft } = useEtl();

  return (
    <Layout>
      <div className="home-layout">
        <aside className="home-sidebar">
          <p className="home-sidebar__greeting">
            Hola, {user?.given_name || user?.name}
          </p>

          <button className="etl-create-btn" onClick={() => navigate("/etl-create")}>
            {draft ? "Reanudar ETL" : "+ Crear ETL"}
          </button>

          <button
            className="etl-clear-btn"
            disabled={!draft}
            onClick={clearDraft}
          >
            Limpiar borrador
          </button>
        </aside>

        <main className="home-main">
          {etls.length === 0 ? (
            <div className="home-empty">
              <span className="home-empty__icon">📋</span>
              <p>No hay ETLs creados todaví­a.</p>
              <p className="home-empty__sub">Crea tu primer ETL para empezar.</p>
            </div>
          ) : (
            <div className="home-grid">
              {etls.map(etl => (
                <EtlCard
                  key={etl.id}
                  etl={etl}
                  onClick={() => navigate(`/etl/${etl.id}`)}
                />
              ))}
            </div>
          )}
        </main>
      </div>
    </Layout>
  );
}


