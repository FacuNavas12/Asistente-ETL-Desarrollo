import "../../css/shared.css";
import "../../css/inputConnection.css";

const SSL_MODES = ["disable", "allow", "prefer", "require", "verify-ca", "verify-full"];

const PORT_DEFAULTS = { postgresql: 5432, sqlserver: 1433 };

export const EMPTY_DESTINATION_CONNECTION = {
  db_type: "postgresql",
  host: "",
  port: PORT_DEFAULTS.postgresql,
  database: "",
  username: "",
  ssl_mode: "require",
};

// Metadata mínima requerida por el backend (InlineConnection, ver
// etl_schemas.py) para resolver la conexión — sin esto el .ktr queda con
// placeholder en esa capa.
export function isDestinationConnectionComplete(value) {
  return Boolean(value?.host && value?.port && value?.database && value?.username);
}

// Mapea una Connection guardada (ver SavedConnectionSelect) a la forma de
// este formulario. Nunca trae password — DestinationConnectionForm no lo pide.
export function fromSavedConnection(c) {
  return {
    db_type:  c.db_type,
    host:     c.host ?? "",
    port:     c.port ?? PORT_DEFAULTS[c.db_type] ?? "",
    database: c.database ?? "",
    username: c.username ?? "",
    ssl_mode: c.ssl_mode ?? "require",
  };
}

// Formulario de metadata de conexión destino (staging/DWH) — NUNCA pide
// password: esta app no conecta de verdad contra staging/DWH, solo hornea
// esta metadata en el .ktr y deja el password como variable Kettle que se
// completa a mano en Spoon/kettle.properties (ver decisión de diseño de
// no-custodia de credenciales). Controlado (value/onChange): el padre decide
// cuándo mandar esto al backend — el checkbox "Completar en Spoon" puede
// reemplazar este form por completo sin pasar por acá.
export default function DestinationConnectionForm({ value, onChange }) {
  const set = (field, v) => onChange({ ...value, [field]: v });

  const handleDbType = (newType) => {
    const currentPort = Number(value.port);
    const isDefault = Object.values(PORT_DEFAULTS).includes(currentPort);
    onChange({
      ...value,
      db_type: newType,
      port: isDefault ? PORT_DEFAULTS[newType] : value.port,
    });
  };

  return (
    <div>
      <div className="form-grid form-grid--mb">
        <div className="form-field">
          <label>Motor de base de datos</label>
          <select value={value.db_type} onChange={e => handleDbType(e.target.value)}>
            <option value="postgresql">PostgreSQL</option>
            <option value="sqlserver">SQL Server</option>
          </select>
        </div>
        <div className="form-field">
          <label>Host</label>
          <input
            type="text"
            value={value.host}
            onChange={e => set("host", e.target.value)}
            placeholder="localhost"
          />
        </div>
        <div className="form-field">
          <label>Puerto</label>
          <input
            type="number"
            value={value.port}
            onChange={e => set("port", e.target.value)}
          />
        </div>
      </div>

      <div className="form-grid form-grid--mb">
        <div className="form-field">
          <label>Base de datos</label>
          <input
            type="text"
            value={value.database}
            onChange={e => set("database", e.target.value)}
          />
        </div>
        <div className="form-field">
          <label>Usuario</label>
          <input
            type="text"
            value={value.username}
            onChange={e => set("username", e.target.value)}
          />
        </div>
        <div className="form-field">
          <label>Modo SSL</label>
          <select value={value.ssl_mode} onChange={e => set("ssl_mode", e.target.value)}>
            {SSL_MODES.map(m => <option key={m} value={m}>{m}</option>)}
          </select>
        </div>
      </div>
    </div>
  );
}
