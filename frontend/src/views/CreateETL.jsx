import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "../context/EtlContext";
import Layout from "../components/Layout";
import StagingForm from "../components/etl/StagingForm";
import OrigenInput from "../components/etl/OrigenInput";
import EtlChecks from "../components/etl/EtlChecks";
import ReglasNegocio from "../components/etl/ReglasNegocio";
import DwhModel from "../components/etl/DwhModel";
import DescripcionObjetivo from "../components/etl/DescripcionObjetivo";
import HomeModal from "../components/HomeModal";
import validateForm from "../validation/etlform";
import "../css/createETL.css";
import "../css/etl-error.css";

const EMPTY_DWH = { tables: [] };

function isDirty(origenTables, stagingDef, reglasNegocio, dwhModel, descripcionObjetivo) {
  return (
    origenTables.length > 0 ||
    stagingDef.length > 0 ||
    reglasNegocio.trim().length > 0 ||
    dwhModel.tables.length > 0 ||
    descripcionObjetivo.trim().length > 0
  );
}

export default function CreateETL() {
  const navigate = useNavigate();
  const { draft, saveDraft, clearDraft, addEtl } = useEtl();

  const [step, setStep] = useState("form");
  const [showModal, setShowModal] = useState(false);

  const [descripcionObjetivo, setDescripcionObjetivo] = useState(draft?.descripcionObjetivo ?? "");
  const [origenTables, setOrigenTables] = useState(draft?.origenTables ?? []);
  const [stagingDef, setStagingDef] = useState(Array.isArray(draft?.stagingDef) ? draft.stagingDef : []);
  const [reglasNegocio, setReglasNegocio] = useState(draft?.reglasNegocio ?? "");
  const [dwhModel, setDwhModel] = useState(draft?.dwhModel ?? EMPTY_DWH);
  const [errors, setErrors] = useState([]);

  useEffect(() => {
    saveDraft({ descripcionObjetivo, origenTables, stagingDef, reglasNegocio, dwhModel });
  }, [descripcionObjetivo, origenTables, stagingDef, reglasNegocio, dwhModel]);

  const dirty = isDirty(origenTables, stagingDef, reglasNegocio, dwhModel, descripcionObjetivo);

  const handleLimpiar = () => {
    setDescripcionObjetivo("");
    setOrigenTables([]);
    setStagingDef([]);
    setReglasNegocio("");
    setDwhModel(EMPTY_DWH);
    clearDraft();
    setErrors([]);
  };

  const handleCreate = async () => {
    const result = validateForm({ origenTables, stagingDef, reglasNegocio, dwhModel });
    if (!result.isValid) { setErrors(result.errors); return; }
    setErrors([]);
    setStep("processing");

    try {
      const res = await fetch("http://localhost:8000/api/ai/etl", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ descripcionObjetivo, origenTables, stagingDef, dwhModel, reglasNegocio }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: `HTTP ${res.status}` }));
        throw new Error(err.detail ?? `HTTP ${res.status}`);
      }
      const apiResult = await res.json();
      const id = addEtl({ origenTables, stagingDef, reglasNegocio, dwhModel }, apiResult);
      navigate(`/etl/${id}`);
    } catch (err) {
      setStep("form");
      setErrors([`Error al enviar al servidor: ${err.message}`]);
    }
  };

  return (
    <Layout onHomeClick={() => setShowModal(true)}>
      {showModal && (
        <HomeModal
          onConfirm={() => navigate("/home")}
          onCancel={() => setShowModal(false)}
        />
      )}

      <div className="etl-page">
        <div className="etl-page__header">
          <h1 className="etl-title">Crear ETL</h1>
          <button className="etl-clear-btn" disabled={!dirty} onClick={handleLimpiar}>
            Limpiar
          </button>
        </div>

        {step === "processing" && (
          <div className="etl-processing">
            <EtlChecks />
          </div>
        )}

        {step === "form" && (
          <div className="etl-body">
            <div className="etl-form-side">
              <DescripcionObjetivo value={descripcionObjetivo} onChange={setDescripcionObjetivo} />
              <OrigenInput value={origenTables} onChange={setOrigenTables} />
              <StagingForm value={stagingDef} onChange={setStagingDef} origenTables={origenTables} />
              <DwhModel value={dwhModel} onChange={setDwhModel} stagingTables={stagingDef} />
              <ReglasNegocio value={reglasNegocio} onChange={setReglasNegocio} />

              <button className="etl-submit-btn" onClick={handleCreate}>
                Crear ETL
              </button>

              {errors.length > 0 && (
                <div className="etl-errors-box">
                  <ul>
                    {errors.map((err, i) => <li key={i}>{err}</li>)}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}
