import { useState } from "react";
import UserOptions from "../components/UserOptions";
import StagingForm from "../components/etl/StagingForm";
import OrigenInput from "../components/etl/OrigenInput";
import EtlChecks from "../components/etl/EtlChecks";
import ChartPanel from "../components/etl/ChartPanel";
import ExplanationPanel from "../components/etl/ExplanationPanel";

import "../css/createETL.css";

export default function EtlCreate() {
  const [step, setStep] = useState("form"); // form → processing → result
  const [responseData, setResponseData] = useState(null);

  const handleCreate = () => {
    setStep("processing");

    // Simular delay de backend
    setTimeout(() => {
      // Simulación de respuesta
      setResponseData({
        chartData: [12, 19, 3, 5, 2, 3],
        explanation: "Los datos fueron limpiados y transformados correctamente."
      });
      setStep("result");
    }, 2000);
  };

  return (
    <div className="etl-container">
      <div className="etl-header">
        <UserOptions />
      </div>

      <h1 className="etl-title">Crear ETL</h1>

      {/* FORMULARIO COMPLETO */}
      {step === "form" && (
        <div className="etl-block etl-form-block">
          <OrigenInput />
          <StagingForm />
          <button className="etl-submit-btn" onClick={handleCreate}>
            Crear ETL
          </button>
        </div>
      )}

      {/* ANIMACIÓN DE PROCESAMIENTO */}
      {step === "processing" && (
        <div className="etl-processing">
          <EtlChecks />
        </div>
      )}

      {/* RESULTADO: GRÁFICA + EXPLICACIÓN */}
      {step === "result" && (
        <div className="etl-result-layout">
          <div className="etl-left">
            <EtlChecks done />
          </div>
          <div className="etl-right">
            <ChartPanel data={responseData.chartData} />
            <ExplanationPanel text={responseData.explanation} />
          </div>
        </div>
      )}
    </div>
  );
}