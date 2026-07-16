import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import ConfirmModal from "@/components/ui/ConfirmModal";
import EtlCard from "./components/EtlCard";
import "./Home.css";
import logo from "@/assets/Logo_blanco_esp.png";

function EmptyState() {
  return (
    <div className="home-empty">
      <span className="home-empty__icon">📋</span>
      <p>No hay Transformaciones creadas todavía.</p>
      <p className="home-empty__sub">Usá el botón + en la barra lateral para crear tu primer ETL.</p>
    </div>
  );
}

export default function Home() {
  const navigate = useNavigate();
  const { visibleEtls, hideEtlLocally, deleteEtlPermanently } = useEtl();
  const [hideTarget, setHideTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);

  const isEmpty = visibleEtls.length === 0;

  return (
    <Layout>
      {hideTarget && (
        <ConfirmModal
          title="¿Quitar esta Transformación de tu vista?"
          message="Se oculta solo en este navegador. Sigue existiendo en el servidor y podés volver a acceder a ella desde otro dispositivo."
          confirmLabel="Quitar"
          cancelLabel="Cancelar"
          onConfirm={() => { hideEtlLocally(hideTarget); setHideTarget(null); }}
          onCancel={() => setHideTarget(null)}
        />
      )}
      {deleteTarget && (
        <ConfirmModal
          title="¿Eliminar esta Transformación definitivamente?"
          message="Esta acción borra el registro del servidor de forma permanente. No hay forma de recuperarlo."
          confirmLabel="Eliminar definitivamente"
          cancelLabel="Cancelar"
          onConfirm={() => { deleteEtlPermanently(deleteTarget); setDeleteTarget(null); }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
      <div className="home-page">
        <div className="home-header">
          <div className="home-header__left">
            <img src={logo} alt="Logo" className="home-header__logo" />
            <h1 className="home-title">Inicio</h1>
            <div className="home-count">
              <span className="home-count__label">Transformaciones</span>
              <span className="home-count__badge">{visibleEtls.length}</span>
            </div>
          </div>
        </div>

        {isEmpty ? (
          <EmptyState />
        ) : (
          <div className="home-grid">
            {visibleEtls.map((etl, i) => (
              <EtlCard
                key={etl.id}
                etl={etl}
                index={i}
                onClick={() => {
                  if (etl.status === "pending" || etl.status === "en_proceso") {
                    navigate("/etl-create", { state: { initialFormData: etl.formData, etlId: etl.id } });
                  } else {
                    navigate(`/etl/${etl.id}`);
                  }
                }}
                onDelete={() => setHideTarget(etl.id)}
                onDeletePermanent={() => setDeleteTarget(etl.id)}
              />
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
