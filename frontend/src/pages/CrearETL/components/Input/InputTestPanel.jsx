import { useState } from "react";
import { runAllOrigenInputTests } from "../../__tests__/origenInputTests";

const STATUS_ICON  = { pass: "✓", fail: "✗", error: "!" };
const STATUS_CLASS = { pass: "test-status--pass", fail: "test-status--fail", error: "test-status--error" };

function CheckRow({ chk }) {
  return (
    <li className={`test-check ${chk.pass ? "test-check--pass" : "test-check--fail"}`}>
      <span className="test-check__icon">{chk.pass ? "✓" : "✗"}</span>
      <span className="test-check__label">{chk.label}</span>
      <span className="test-check__value">
        {JSON.stringify(chk.actual)}
        {!chk.pass && (
          <span className="test-check__expected"> (esperado: {JSON.stringify(chk.expected)})</span>
        )}
      </span>
    </li>
  );
}

function TestCard({ result }) {
  const [open, setOpen] = useState(result.status !== "pass");

  return (
    <div className={`test-card test-card--${result.status}`}>
      <button className="test-card__header" onClick={() => setOpen(o => !o)}>
        <span className={`test-status ${STATUS_CLASS[result.status]}`}>
          {STATUS_ICON[result.status]}
        </span>
        <span className="test-card__name">{result.name}</span>
        <span className="test-card__toggle">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="test-card__body">
          {result.error && (
            <p className="test-error-msg">{result.error}</p>
          )}
          {result.checks.length > 0 && (
            <ul className="test-check-list">
              {result.checks.map((c, i) => <CheckRow key={i} chk={c} />)}
            </ul>
          )}
          {result.tables?.length > 0 && (
            <details className="test-raw">
              <summary>Salida del parser ({result.tables.length} tabla{result.tables.length !== 1 ? "s" : ""})</summary>
              <pre className="test-raw__code">{JSON.stringify(result.tables, null, 2)}</pre>
            </details>
          )}
        </div>
      )}
    </div>
  );
}

export default function OrigenInputTestPanel() {
  const [results,  setResults]  = useState(null);
  const [running,  setRunning]  = useState(false);

  const handleRun = async () => {
    setRunning(true);
    setResults(null);
    const res = await runAllOrigenInputTests();
    setResults(res);
    setRunning(false);
  };

  const passed = results ? results.filter(r => r.status === "pass").length : 0;
  const total  = results?.length ?? 0;

  return (
    <div className="test-panel">
      <div className="test-panel__header">
        <span className="test-panel__title">Tests - OrigenInput parsers</span>
        <button
          className="staging-add-btn test-run-btn"
          onClick={handleRun}
          disabled={running}
        >
          {running ? "Ejecutando: " : "Correr tests"}
        </button>
        {results && (
          <span className={`test-summary ${passed === total ? "test-summary--pass" : "test-summary--fail"}`}>
            {passed}/{total} pasaron
          </span>
        )}
      </div>

      {results && (
        <div className="test-cards">
          {results.map((r, i) => <TestCard key={i} result={r} />)}
        </div>
      )}
    </div>
  );
}


