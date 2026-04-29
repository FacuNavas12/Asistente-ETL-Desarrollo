import { useState } from "react";
import Layout from "../components/Layout";
import StagingForm from "../components/etl/StagingForm";
import OrigenInput from "../components/etl/OrigenInput";
import EtlChecks from "../components/etl/EtlChecks";
import ReglasNegocio from "../components/etl/ReglasNegocio";
import DwhModel from "../components/etl/DwhModel";
import ChartPanel from "../components/etl/ChartPanel";
import ExplanationPanel from "../components/etl/ExplanationPanel";
import "../css/createETL.css";

export default function CreateETL() {
  const [step, setStep] = useState("form"); // form | processing | result
  const [responseData, setResponseData] = useState(null);
  const [origenText, setOrigenText] = useState("");
  const [stagingDef, setStagingDef] = useState({ tableName: "", columns: [] });
  const [reglasNegocio, setReglasNegocio] = useState("");
  const [dwhModel, setDwhModel] = useState({ tables: [] });

  const handleCreate = () => {
    setStep("processing");
    setTimeout(() => {
      setResponseData({
        chartData: [12, 19, 3, 5, 2, 3],
        explanation: "Los datos fueron limpiados y transformados correctamente.",
      });
      setStep("result");
    }, 2000);
  };

  return (
    <Layout>
      <div className="etl-page">
        <h1 className="etl-title">Crear ETL</h1>

        {step === "processing" && (
          <div className="etl-processing">
            <EtlChecks />
          </div>
        )}

        {(step === "form" || step === "result") && (
          <div className={`etl-body ${step === "result" ? "split" : ""}`}>

            {/* IZQUIERDA: formulario siempre visible */}
            <div className="etl-form-side">
              <OrigenInput value={origenText} onChange={setOrigenText} />
              <StagingForm value={stagingDef} onChange={setStagingDef} />
              <DwhModel value={dwhModel} onChange={setDwhModel} />
              <ReglasNegocio value={reglasNegocio} onChange={setReglasNegocio} />
              {step === "form" && (
                <button className="etl-submit-btn" onClick={handleCreate}>
                  Crear ETL
                </button>
              )}
            </div>

            {/* DERECHA: aparece al hacer submit */}
            <div className="etl-right-side">
              <ChartPanel data={responseData?.chartData} />
              <ExplanationPanel text={responseData?.explanation} />
            </div>

          </div>
        )}
      </div>
    </Layout>
  );
}
