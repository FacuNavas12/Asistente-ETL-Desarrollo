import { useState } from "react";
import { createConnection, testConnection } from "@/api/connections";
import "../../css/shared.css";
import "../../css/inputConnection.css";

const SSL_MODES = ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"];

const PORT_DEFAULTS = { postgresql: 5432, sqlserver: 1433 };

const EMPTY_FORM = {
  db_type: "postgresql",
  name: "",
  host: "",
  port: PORT_DEFAULTS.postgresql,
  database: "",
  username: "",
  password: "",
  ssl_mode: "prefer",
  trustServerCert: false,
};

const STATUS_LABELS = {
  idle:     "Conectar",
  creating: "Creando conexión...",
  testing:  "Probando conexión...",
  success:  "Conectar de nuevo",
  error:    "Conectar",
};

const BUSY = new Set(["creating", "testing"]);

// Formulario de conexión reusado tanto por InputConnection (origen, agrega
// selector de tablas después) como por los pickers de destino (staging/DWH,
// solo necesitan el connId). onConnected(connId) se llama recién después de
// crear la Connection y confirmar el test.
export default function ConnectionForm({ onConnected, submitLabel }) {
  const [form, setForm]     = useState(EMPTY_FORM);
  const [status, setStatus] = useState("idle");
  const [error, setError]   = useState("");

  const set = (field, v) =>
    setForm(prev => ({ ...prev, [field]: v }));

  const handleDbType = (newType) => {
    const currentPort = Number(form.port);
    const isDefault = Object.values(PORT_DEFAULTS).includes(currentPort);
    setForm(prev => ({
      ...prev,
      db_type: newType,
      port: isDefault ? PORT_DEFAULTS[newType] : prev.port,
    }));
  };

  const handleConnect = async () => {
    setStatus("creating");
    setError("");
    try {
      const base = {
        db_type:  form.db_type,
        name:     form.name,
        host:     form.host,
        port:     Number(form.port),
        database: form.database,
        username: form.username,
        password: form.password,
      };

      const payload = form.db_type === "postgresql"
        ? { ...base, ssl_mode: form.ssl_mode }
        : form.trustServerCert
          ? { ...base, extra_options: { trust_server_certificate: true } }
          : { ...base };

      const conn = await createConnection(payload);

      setStatus("testing");
      const testResult = await testConnection(conn.id);
      if (!testResult.success) {
        setStatus("error");
        setError(testResult.message);
        return;
      }

      setStatus("success");
      onConnected?.(conn.id, { name: form.name, db_type: form.db_type });
    } catch (err) {
      setStatus("error");
      setError(err.message);
    }
  };

  return (
    <div>
      {/* Motor y nombre */}
      <div className="form-grid form-grid--mb">
        <div className="form-field">
          <label>Motor de base de datos</label>
          <select value={form.db_type} onChange={e => handleDbType(e.target.value)}>
            <option value="postgresql">PostgreSQL</option>
            <option value="sqlserver">SQL Server</option>
          </select>
        </div>
        <div className="form-field">
          <label>Nombre de conexión</label>
          <input
            type="text"
            value={form.name}
            onChange={e => set("name", e.target.value)}
            placeholder="Mi conexión"
          />
        </div>
      </div>

      {/* Host, puerto, base de datos */}
      <div className="form-grid form-grid--mb">
        <div className="form-field">
          <label>Host</label>
          <input
            type="text"
            value={form.host}
            onChange={e => set("host", e.target.value)}
            placeholder="localhost"
          />
        </div>
        <div className="form-field">
          <label>Puerto</label>
          <input
            type="number"
            value={form.port}
            onChange={e => set("port", e.target.value)}
          />
        </div>
        <div className="form-field">
          <label>Base de datos</label>
          <input
            type="text"
            value={form.database}
            onChange={e => set("database", e.target.value)}
          />
        </div>
      </div>

      {/* Credenciales y opciones por motor */}
      <div className="form-grid form-grid--mb">
        <div className="form-field">
          <label>Usuario</label>
          <input
            type="text"
            value={form.username}
            onChange={e => set("username", e.target.value)}
          />
        </div>
        <div className="form-field">
          <label>Contraseña</label>
          <input
            type="password"
            value={form.password}
            onChange={e => set("password", e.target.value)}
          />
        </div>

        {form.db_type === "postgresql" && (
          <div className="form-field">
            <label>Modo SSL</label>
            <select value={form.ssl_mode} onChange={e => set("ssl_mode", e.target.value)}>
              {SSL_MODES.map(m => <option key={m} value={m}>{m}</option>)}
            </select>
          </div>
        )}

        {form.db_type === "sqlserver" && (
          <div className="form-field" style={{ justifyContent: "flex-end" }}>
            <label className="conn-checkbox-label">
              <input
                type="checkbox"
                checked={form.trustServerCert}
                onChange={e => set("trustServerCert", e.target.checked)}
              />
              Confiar en certificado del servidor
            </label>
          </div>
        )}
      </div>

      <button
        className="staging-add-btn"
        onClick={handleConnect}
        disabled={BUSY.has(status)}
      >
        {status === "success" && submitLabel ? submitLabel : STATUS_LABELS[status]}
      </button>

      {status === "error" && error && (
        <p className="conn-status-error">{error}</p>
      )}
    </div>
  );
}
