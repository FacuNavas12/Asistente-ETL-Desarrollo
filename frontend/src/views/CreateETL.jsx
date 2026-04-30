import { useState, useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { useEtl } from "../context/EtlContext";
import Layout from "../components/Layout";
import StagingForm from "../components/etl/StagingForm";
import OrigenInput from "../components/etl/OrigenInput";
import EtlChecks from "../components/etl/EtlChecks";
import ReglasNegocio from "../components/etl/ReglasNegocio";
import DwhModel from "../components/etl/DwhModel";
import HomeModal from "../components/HomeModal";
import validateForm from "../validation/etlform";
import "../css/createETL.css";
import "../css/etl-error.css";

const EMPTY_STAGING = { tableName: "", columns: [] };
const EMPTY_DWH = { tables: [] };

function isDirty(origenText, stagingDef, reglasNegocio, dwhModel) {
  return (
    origenText.trim().length > 0 ||
    stagingDef.tableName.length > 0 ||
    stagingDef.columns.length > 0 ||
    reglasNegocio.trim().length > 0 ||
    dwhModel.tables.length > 0
  );
}

export default function CreateETL() {
  const navigate = useNavigate();
  const { draft, saveDraft, clearDraft, addEtl } = useEtl();

  const [step, setStep] = useState("form");
  const [showModal, setShowModal] = useState(false);

  const [origenText, setOrigenText] = useState(draft?.origenText ?? "");
  const [stagingDef, setStagingDef] = useState(draft?.stagingDef ?? EMPTY_STAGING);
  const [reglasNegocio, setReglasNegocio] = useState(draft?.reglasNegocio ?? "");
  const [dwhModel, setDwhModel] = useState(draft?.dwhModel ?? EMPTY_DWH);
  const [errors, setErrors] = useState([]);

  useEffect(() => {
    saveDraft({ origenText, stagingDef, reglasNegocio, dwhModel });
  }, [origenText, stagingDef, reglasNegocio, dwhModel]);

  const dirty = isDirty(origenText, stagingDef, reglasNegocio, dwhModel);

  const handleLimpiar = () => {
    setOrigenText("");
    setStagingDef(EMPTY_STAGING);
    setReglasNegocio("");
    setDwhModel(EMPTY_DWH);
    clearDraft();
    setErrors([]);
  };

  const handleCreate = () => {
    const result = validateForm({ origenText, stagingDef, reglasNegocio, dwhModel });
    if (!result.isValid) { setErrors(result.errors); return; }
    setErrors([]);
    setStep("processing");
    setTimeout(() => {
      const id = addEtl({ origenText, stagingDef, reglasNegocio, dwhModel });
      navigate(`/etl/${id}`);
    }, 2000);
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
              <OrigenInput value={origenText} onChange={setOrigenText} />
              <StagingForm value={stagingDef} onChange={setStagingDef} />
              <DwhModel value={dwhModel} onChange={setDwhModel} />
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
