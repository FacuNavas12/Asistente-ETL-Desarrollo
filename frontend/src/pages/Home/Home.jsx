import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "@/context/EtlContext";
import Layout from "@/components/layout/Layout";
import ConfirmModal from "@/components/ui/ConfirmModal";
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
  const { etls, jobs, deleteEtl } = useEtl();
  const [filter, setFilter] = useState("all");
  const [deleteTarget, setDeleteTarget] = useState(null);

  const visibleEtls = filter !== "job" ? etls : [];
  const visibleJobs = filter !== "etl" ? jobs : [];
  const isEmpty     = visibleEtls.length === 0 && visibleJobs.length === 0;

  return (
    <Layout>
      {deleteTarget && (
        <ConfirmModal
          title="¿Eliminar esta Transformación?"
          message="Esta acción la eliminará permanentemente del almacenamiento local. Si no la descargaste antes, no hay forma de recuperarla."
          confirmLabel="Eliminar"
          cancelLabel="Cancelar"
          onConfirm={() => { deleteEtl(deleteTarget); setDeleteTarget(null); }}
          onCancel={() => setDeleteTarget(null)}
        />
      )}
      <div className="home-page">
        <div className="home-header">
          <div className="home-header__left">
            <h1 className="home-title">Inicio</h1>
            <div className="home-count">
              <span className="home-count__label">Transformaciones</span>
              <span className="home-count__badge">{etls.length}</span>
            </div>
            <div className="home-count">
              <span className="home-count__label">Jobs</span>
              <span className="home-count__badge">{jobs.length}</span>
            </div>
          </div>

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
                onDelete={() => setDeleteTarget(etl.id)}
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
