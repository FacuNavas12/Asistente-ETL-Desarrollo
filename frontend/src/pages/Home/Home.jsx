import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import ConfirmModal from "@/components/ui/ConfirmModal";
import { useToast } from "@/components/ui/Toast";
import { parseEtlFile } from "@/utils/etlImport";
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
  const { visibleEtls, hideEtlLocally, deleteEtlPermanently, addEtl } = useEtl();
  const { addToast } = useToast();
  const [hideTarget, setHideTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const importInputRef = useRef(null);

  const isEmpty = visibleEtls.length === 0;

  const handleImport = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    try {
      const parsed = await parseEtlFile(file);
      if (parsed.type === "full") {
        const id = await addEtl(parsed.etl.formData, parsed.etl.result, parsed.etl.name);
        navigate(`/etl/${id}`);
      } else {
        navigate("/etl-create", { state: { initialFormData: parsed.formData } });
      }
    } catch (err) {
      addToast(`Error al importar: ${err.message}`);
    }
  };

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

          <div className="home-header__right">
            <button className="home-import-btn" onClick={() => importInputRef.current?.click()}>
              Importar
            </button>
            <input
              type="file"
              accept=".json,application/json"
              ref={importInputRef}
              style={{ display: "none" }}
              onChange={handleImport}
            />
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
