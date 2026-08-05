import { useState, useEffect } from "react";
import { createConnection, testConnection, listConnections } from "@/api/connections";
import SavedConnectionSelect from "./SavedConnectionSelect";
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
  ssl_mode: "require",
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
  // Conexiones guardadas (metadata sin password) para reusar sin re-ingresar todo.
  const [savedConns, setSavedConns] = useState([]);
  // id de la Connection reusada; null = se va a crear una nueva al conectar.
  const [reuseId, setReuseId]       = useState(null);

  useEffect(() => {
    let alive = true;
    listConnections()
      .then(list => { if (alive) setSavedConns(Array.isArray(list) ? list : []); })
      .catch(() => { /* sin conexiones guardadas o backend sin auth: se ignora */ });
    return () => { alive = false; };
  }, []);

  // Editar cualquier campo de identidad invalida el reuso: pasa a crear una nueva
  // Connection. El password no es identidad, así que no rompe el reuso.
  const set = (field, v) =>
    setForm(prev => ({ ...prev, [field]: v }));

  const setIdentity = (field, v) => {
    setReuseId(null);
    set(field, v);
  };

  const handlePickSaved = (id) => {
    if (!id) { setReuseId(null); setForm(EMPTY_FORM); return; }
    const c = savedConns.find(x => String(x.id) === String(id));
    if (!c) return;
    setReuseId(c.id);
    setError("");
    setStatus("idle");
    setForm({
      db_type:  c.db_type,
      name:     c.name ?? "",
      host:     c.host ?? "",
      port:     c.port ?? PORT_DEFAULTS[c.db_type] ?? "",
      database: c.database ?? "",
      username: c.username ?? "",
      password: "",  // nunca llega del backend — se tipea a mano
      ssl_mode: c.ssl_mode ?? "require",
      trustServerCert: Boolean(c.extra_options?.trust_server_certificate),
    });
  };

  const handleDbType = (newType) => {
    const currentPort = Number(form.port);
    const isDefault = Object.values(PORT_DEFAULTS).includes(currentPort);
    setReuseId(null);
    setForm(prev => ({
      ...prev,
      db_type: newType,
      port: isDefault ? PORT_DEFAULTS[newType] : prev.port,
    }));
  };

  const handleConnect = async () => {
    setError("");
    try {
      let conn;
      if (reuseId) {
        // Conexión guardada reusada: la metadata ya existe, no se crea de nuevo.
        conn = { id: reuseId };
      } else {
        setStatus("creating");
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
          : {
              ...base,
              ssl_mode: form.ssl_mode,
              ...(form.trustServerCert ? { extra_options: { trust_server_certificate: true } } : {}),
            };

        conn = await createConnection(payload);
      }

      setStatus("testing");
      const testResult = await testConnection(conn.id, form.password);
      if (!testResult.success) {
        setStatus("error");
        setError(testResult.message);
        return;
      }

      setStatus("success");
      // El password nunca se persiste — se lo pasamos al padre para que lo
      // mantenga en memoria (nunca en sessionStorage/localStorage) mientras
      // dure la sesión de armado del ETL, y lo reenvíe en cada operación que
      // vuelva a necesitar conectar de verdad (explorar tablas, etc).
      onConnected?.(conn.id, { name: form.name, db_type: form.db_type }, form.password);
    } catch (err) {
      setStatus("error");
      setError(err.message);
    }
  };

  return (
    <div>
      {/* Conexiones guardadas: reusar sin re-ingresar todo (solo se tipea el password) */}
      <SavedConnectionSelect
        conns={savedConns}
        value={reuseId ?? ""}
        onSelect={c => handlePickSaved(c ? c.id : "")}
      />

      {reuseId && (
        <p className="conn-reuse-hint">
          Conexión reusada — solo ingresá la contraseña. Si editás algún dato, se creará una conexión nueva.
        </p>
      )}

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
            onChange={e => setIdentity("name", e.target.value)}
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
            onChange={e => setIdentity("host", e.target.value)}
            placeholder="localhost"
          />
        </div>
        <div className="form-field">
          <label>Puerto</label>
          <input
            type="number"
            value={form.port}
            onChange={e => setIdentity("port", e.target.value)}
          />
        </div>
        <div className="form-field">
          <label>Base de datos</label>
          <input
            type="text"
            value={form.database}
            onChange={e => setIdentity("database", e.target.value)}
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
            onChange={e => setIdentity("username", e.target.value)}
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

        <div className="form-field">
          <label>Modo SSL</label>
          <select value={form.ssl_mode} onChange={e => setIdentity("ssl_mode", e.target.value)}>
            {SSL_MODES.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>

        {form.db_type === "sqlserver" && (
          <div className="form-field" style={{ justifyContent: "flex-end" }}>
            <label className="conn-checkbox-label">
              <input
                type="checkbox"
                checked={form.trustServerCert}
                onChange={e => setIdentity("trustServerCert", e.target.checked)}
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
