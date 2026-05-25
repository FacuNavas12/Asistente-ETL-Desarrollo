export default function JobResult({ result, onNew }) {
  const handleDownload = () => {
    const blob = new Blob([result.kjb_xml], { type: "application/xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = result.kjb_filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="job-body">
      <div className="job-result">
        <div className="job-result__success">
          <span>✅</span>
          <span>Job generado: {result.job_plan.job_name}</span>
        </div>

        <div className="job-result__explanation">{result.explanation}</div>

        <div className="job-result__actions">
          <button className="job-btn--primary" onClick={handleDownload}>
            Descargar {result.kjb_filename}
          </button>
          <button className="job-btn--secondary" onClick={onNew}>
            Crear otro Job
          </button>
        </div>
      </div>
    </div>
  );
}
