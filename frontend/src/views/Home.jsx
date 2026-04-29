import { useAuth0 } from "@auth0/auth0-react";
import { useNavigate } from "react-router-dom";
import Layout from "../components/Layout";
import "../css/home.css";

export default function Home() {
  const { user } = useAuth0();
  const navigate = useNavigate();

  return (
    <Layout>
      <div className="home-content">
        <h1 className="home-title">Bienvenido, {user?.given_name || user?.name}</h1>
        <p className="home-subtitle">¿Qué querés hacer hoy?</p>
        <button className="etl-create-btn" onClick={() => navigate("/etl-create")}>
          + Crear ETL
        </button>
      </div>
    </Layout>
  );
}
