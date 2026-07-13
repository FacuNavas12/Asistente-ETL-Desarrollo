import { useState, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import { ETL_STATUS } from "@/constants/status";
import Layout from "@/components/layout/Layout";
import ConfirmModal from "@/components/ui/ConfirmModal";
import { useToast } from "@/components/ui/Toast";
import { parseEtlFile } from "@/utils/etlImport";
import EtlCard from "./components/EtlCard";
import "./Home.css";

const JOB_ICONS  = ["🤖", "🛠️", "🔧", "📋", "🔩", "💾", "🚀", "🎯"];
const FILTERS    = [
  { key: "all", label: "Todo" },
  { key: "etl", label: "TF" },
  { key: "job", label: "Job" },
];

function JobCard({ job, index, onClick }) {
  const status = ETL_STATUS[job.status] ?? ETL_STATUS.done;

  return (
    <div className="etl-card etl-card--job" style={{ animationDelay: `${index * 60}ms` }} onClick={onClick}>
      <div className="etl-card__icon etl-card__icon--job">{JOB_ICONS[index % JOB_ICONS.length]}</div>
      <span className="etl-card__type-tag etl-card__type-tag--job">Job</span>
      <span className="etl-card__name">{job.name}</span>
      <span className="etl-card__date">
        {new Date(job.createdAt).toLocaleDateString("es-AR", { dateStyle: "medium" })}
      </span>
      <span className="etl-card__status" style={{ "--status-color": status.color }}>
        {status.label}
      </span>
      <div className="etl-card__footer">
        <span className="etl-card__action">Ver detalle →</span>
      </div>
    </div>
  );
}

function EmptyState({ filter }) {
  const messages = {
    etl: {
      text: "No hay Transformaciónes creadas todavía.",
      sub:  "Usá el botón + en la barra lateral para crear tu primer ETL.",
    },
    job: {
      text: "No hay Jobs creados todavía.",
      sub:  "Usá el botón + en la barra lateral para crear tu primer Job.",
    },
    all: {
      text: "No hay elementos creados todavía.",
      sub:  "Usá el botón + en la barra lateral para comenzar.",
    },
  };
  const { text, sub } = messages[filter];

  return (
    <div className="home-empty">
      <span className="home-empty__icon">📋</span>
      <p>{text}</p>
      <p className="home-empty__sub">{sub}</p>
    </div>
  );
}

export default function Home() {
  const navigate = useNavigate();
  const { visibleEtls: allVisibleEtls, jobs, hideEtlLocally, deleteEtlPermanently, addEtl } = useEtl();
  const { addToast } = useToast();
  const [filter, setFilter] = useState("all");
  const [hideTarget, setHideTarget] = useState(null);
  const [deleteTarget, setDeleteTarget] = useState(null);
  const importInputRef = useRef(null);

  const visibleEtls = filter !== "job" ? allVisibleEtls : [];
  const visibleJobs = filter !== "etl" ? jobs : [];
  const isEmpty     = visibleEtls.length === 0 && visibleJobs.length === 0;

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
            <h1 className="home-title">Inicio</h1>
            <div className="home-count">
              <span className="home-count__label">Transformaciones</span>
              <span className="home-count__badge">{allVisibleEtls.length}</span>
            </div>
            <div className="home-count">
              <span className="home-count__label">Jobs</span>
              <span className="home-count__badge">{jobs.length}</span>
            </div>
          </div>

          <div className="home-header__right">
            <div className="home-filter">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  className={`home-filter__btn${filter === f.key ? " home-filter__btn--active" : ""}`}
                  onClick={() => setFilter(f.key)}
                >
                  {f.label}
                </button>
              ))}
            </div>
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
          <EmptyState filter={filter} />
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
            {visibleJobs.map((job, i) => (
              <JobCard
                key={job.id}
                job={job}
                index={i}
                onClick={() => {}}
              />
            ))}
          </div>
        )}
      </div>
    </Layout>
  );
}
