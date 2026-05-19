import { useState } from "react";
import { createConnection, testConnection, listTables } from "@/api/connections";
import "../etlForm.css";

const SSL_MODES = ["disable", "require", "verify-ca", "verify-full"];

const PORT_DEFAULTS = { postgresql: 5432, sqlserver: 1433 };

const EMPTY_FORM = {
  db_type: "postgresql",
  name: "",
  host: "",
  port: PORT_DEFAULTS.postgresql,
  database: "",
  username: "",
  password: "",
  ssl_mode: "require",
  trustServerCert: false,
};

const STATUS_LABELS = {
  idle:          "Conectar",
  creating:      "Creando conexión...",
  testing:       "Probando conexión...",
  loadingTables: "Cargando tablas...",
  success:       "Conectar de nuevo",
  error:         "Conectar",
};

const BUSY = new Set(["creating", "testing", "loadingTables"]);

export default function InputConection() {
  const [form, setForm]     = useState(EMPTY_FORM);
  const [status, setStatus] = useState("idle");
  const [error, setError]   = useState("");
  const [tables, setTables] = useState([]);

  const set = (field, value) =>
    setForm(prev => ({ ...prev, [field]: value }));

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
    setTables([]);
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

      let payload;
      if (form.db_type === "postgresql") {
        payload = { ...base, ssl_mode: form.ssl_mode };
      } else {
        payload = form.trustServerCert
          ? { ...base, extra_options: { trust_server_certificate: true } }
          : { ...base };
      }

      const conn = await createConnection(payload);

      setStatus("testing");
      const testResult = await testConnection(conn.id);
      if (!testResult.success) {
        setStatus("error");
        setError(testResult.message);
        return;
      }

      setStatus("loadingTables");
      const tableList = await listTables(conn.id);
      setTables(tableList);
      setStatus("success");
    } catch (err) {
      setStatus("error");
      setError(err.message);
    }
  };

  return (
    <div>
      {/* Tipo de motor y nombre */}
      <div className="form-grid" style={{ marginBottom: "18px" }}>
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
      <div className="form-grid" style={{ marginBottom: "18px" }}>
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

      {/* Credenciales y opciones específicas por motor */}
      <div className="form-grid" style={{ marginBottom: "18px" }}>
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
            <label style={{ display: "flex", alignItems: "center", gap: "8px", cursor: "pointer" }}>
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
        {STATUS_LABELS[status]}
      </button>

      {status === "error" && error && (
        <p style={{ marginTop: "12px", color: "var(--error, #e55)", fontSize: "14px" }}>
          {error}
        </p>
      )}

      {status === "success" && (
        <div style={{ marginTop: "20px" }}>
          <p style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-h)", marginBottom: "8px" }}>
            Tablas disponibles ({tables.length})
          </p>
          {tables.length === 0 ? (
            <p style={{ fontSize: "14px", color: "var(--text)" }}>
              La conexión no expone tablas accesibles.
            </p>
          ) : (
            <div className="staging-table-wrapper">
              <table className="staging-table">
                <thead>
                  <tr>
                    <th>#</th>
                    <th>Tabla</th>
                  </tr>
                </thead>
                <tbody>
                  {tables.map((t, i) => (
                    <tr key={t}>
                      <td style={{ opacity: 0.5, width: "40px" }}>{i + 1}</td>
                      <td style={{ fontFamily: "monospace" }}>{t}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
