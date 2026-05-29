import { useState } from "react";
import { createConnection, testConnection, listTables, getTableData, getColumns } from "@/api/connections";
import "../etlForm.css";

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
  idle:          "Conectar",
  creating:      "Creando conexión...",
  testing:       "Probando conexión...",
  loadingTables: "Cargando tablas...",
  success:       "Conectar de nuevo",
  error:         "Conectar",
};

const BUSY = new Set(["creating", "testing", "loadingTables"]);

/** Splits "schema.table" by the first dot only. */
function splitTable(qualified) {
  const dotIdx = qualified.indexOf(".");
  return dotIdx === -1
    ? { schema: "", table: qualified }
    : { schema: qualified.slice(0, dotIdx), table: qualified.slice(dotIdx + 1) };
}

function mapDbType(dbType) {
  const t = (dbType || "").toLowerCase();
  if (t.includes("int") || t.includes("serial")) return "int";
  if (t.includes("float") || t.includes("double") || t.includes("numeric") ||
      t.includes("decimal") || t.includes("real") || t.includes("money")) return "float";
  if (t.includes("bool")) return "bool";
  if (t.includes("date") || t.includes("time") || t.includes("timestamp")) return "date";
  return "string";
}

export default function InputConection({ value, onChange }) {
  const [form, setForm]     = useState(EMPTY_FORM);
  const [status, setStatus] = useState("idle");
  const [error, setError]   = useState("");
  const [tables, setTables] = useState([]);
  const [connId, setConnId] = useState(null);

  // Data preview state
  const [selectedTable, setSelectedTable] = useState(null);   // {schema, table, qualified}
  const [tableData, setTableData]         = useState(null);   // TableDataResponse
  const [dataPage, setDataPage]           = useState(1);
  const [loadingData, setLoadingData]     = useState(false);
  const [dataError, setDataError]         = useState("");

  // Confirmed tables state
  const [confirmedNames, setConfirmedNames] = useState(new Set());
  const [confirmingTable, setConfirmingTable] = useState(null);
  const [confirmError, setConfirmError]     = useState("");

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
    setTables([]);
    setConnId(null);
    setSelectedTable(null);
    setTableData(null);
    setConfirmedNames(new Set());
    setConfirmError("");
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
      setConnId(conn.id);

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

  const handleSelectTable = async (qualified, page = 1) => {
    if (!connId) return;
    const { schema, table } = splitTable(qualified);
    setSelectedTable({ schema, table, qualified });
    setDataPage(page);
    setLoadingData(true);
    setDataError("");
    setTableData(null);
    try {
      const data = await getTableData(connId, schema, table, page);
      setTableData(data);
    } catch (err) {
      setDataError(err.message);
    } finally {
      setLoadingData(false);
    }
  };

  const handlePageChange = (newPage) => {
    if (!selectedTable) return;
    handleSelectTable(selectedTable.qualified, newPage);
  };

  const handleConfirmTable = async (qualified) => {
    if (!connId || confirmingTable) return;
    setConfirmingTable(qualified);
    setConfirmError("");
    try {
      const cols = await getColumns(connId, qualified);

      // Use sample data from tableData if this table is currently loaded in preview
      const isCurrentTable = selectedTable?.qualified === qualified && tableData;
      const columns = cols.map(col => {
        const colIdx = isCurrentTable ? (tableData.columns || []).indexOf(col.name) : -1;
        const sampleData = colIdx >= 0
          ? tableData.rows.slice(0, 5).map(row => row[colIdx] !== null ? String(row[colIdx]) : "").filter(Boolean)
          : [];
        return {
          name:       col.name,
          dataType:   mapDbType(col.type),
          dataFormat: "",
          role:       "atributo",
          data:       sampleData,
        };
      });

      const newTable = { tableName: qualified, columns };
      onChange([...(Array.isArray(value) ? value : []), newTable]);
      setConfirmedNames(prev => new Set([...prev, qualified]));
    } catch (err) {
      setConfirmError(`No se pudo confirmar "${qualified}": ${err.message}`);
    } finally {
      setConfirmingTable(null);
    }
  };

  const handleRemoveConfirmed = (qualified) => {
    onChange((Array.isArray(value) ? value : []).filter(t => t.tableName !== qualified));
    setConfirmedNames(prev => {
      const next = new Set(prev);
      next.delete(qualified);
      return next;
    });
  };

  const isLastPage = tableData
    ? tableData.rows.length < tableData.page_size ||
      (tableData.total_pages > 0 && dataPage >= tableData.total_pages)
    : true;

  return (
    <div>
      {/* Motor y nombre */}
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

      {/* Credenciales y opciones por motor */}
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

      {/* Catálogo de tablas */}
      {status === "success" && (
        <div style={{ marginTop: "20px" }}>
          <p style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-h)", marginBottom: "8px" }}>
            Tablas disponibles ({tables.length})
            {tables.length > 0 && (
              <span style={{ fontWeight: 400, fontSize: "12px", marginLeft: "8px", opacity: 0.7 }}>
                — clic en el nombre para previsualizar · confirmar para usar en el ETL
              </span>
            )}
          </p>

          {confirmError && (
            <p style={{ fontSize: "13px", color: "var(--error, #e55)", marginBottom: "8px" }}>
              {confirmError}
            </p>
          )}

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
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {tables.map((t, i) => {
                    const confirmed   = confirmedNames.has(t);
                    const isConfirming = confirmingTable === t;
                    return (
                      <tr
                        key={t}
                        style={{
                          backgroundColor:
                            selectedTable?.qualified === t
                              ? "var(--accent-subtle, rgba(99,102,241,0.12))"
                              : undefined,
                        }}
                      >
                        <td style={{ opacity: 0.5, width: "40px" }}>{i + 1}</td>
                        <td
                          style={{ fontFamily: "monospace", cursor: "pointer" }}
                          onClick={() => handleSelectTable(t)}
                        >
                          {t}
                          {confirmed && (
                            <span style={{
                              marginLeft: "8px",
                              fontSize: "11px",
                              fontFamily: "sans-serif",
                              color: "var(--success, #4ade80)",
                              fontWeight: 600,
                            }}>
                              ✓ confirmada
                            </span>
                          )}
                        </td>
                        <td style={{ textAlign: "right", whiteSpace: "nowrap", paddingRight: "6px" }}>
                          {confirmed ? (
                            <button
                              className="staging-remove-btn"
                              onClick={() => handleRemoveConfirmed(t)}
                            >
                              Quitar
                            </button>
                          ) : (
                            <button
                              className="staging-add-btn"
                              onClick={() => handleConfirmTable(t)}
                              disabled={!!confirmingTable}
                              style={{ padding: "3px 12px", fontSize: "12px" }}
                            >
                              {isConfirming ? "Cargando..." : "Confirmar"}
                            </button>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Preview de datos */}
      {selectedTable && (
        <div style={{ marginTop: "28px" }}>
          <div style={{ display: "flex", alignItems: "baseline", gap: "12px", marginBottom: "10px", flexWrap: "wrap" }}>
            <span style={{ fontSize: "13px", fontWeight: "600", color: "var(--text-h)", fontFamily: "monospace" }}>
              {selectedTable.qualified}
            </span>
            {tableData && (
              <span style={{ fontSize: "12px", color: "var(--text)", opacity: 0.7 }}>
                {tableData.total_count === -1
                  ? "sin estadísticas de filas"
                  : `~${tableData.total_count.toLocaleString()} filas${tableData.count_is_estimate ? " (estimado)" : ""}`
                }
              </span>
            )}
          </div>

          {loadingData && (
            <p style={{ fontSize: "13px", color: "var(--text)", opacity: 0.7 }}>
              Cargando datos...
            </p>
          )}

          {dataError && (
            <p style={{ fontSize: "13px", color: "var(--error, #e55)" }}>{dataError}</p>
          )}

          {tableData && !loadingData && (
            <>
              <div className="staging-table-wrapper" style={{ overflowX: "auto" }}>
                <table className="staging-table">
                  <thead>
                    <tr>
                      {tableData.columns.map(col => (
                        <th key={col} style={{ fontFamily: "monospace", whiteSpace: "nowrap" }}>
                          {col}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {tableData.rows.length === 0 ? (
                      <tr>
                        <td
                          colSpan={tableData.columns.length}
                          style={{ textAlign: "center", opacity: 0.6, padding: "16px" }}
                        >
                          Sin filas en esta página
                        </td>
                      </tr>
                    ) : (
                      tableData.rows.map((row, i) => (
                        <tr key={i}>
                          {row.map((cell, j) => (
                            <td
                              key={j}
                              style={{
                                fontFamily: "monospace",
                                maxWidth: "220px",
                                overflow: "hidden",
                                textOverflow: "ellipsis",
                                whiteSpace: "nowrap",
                              }}
                              title={cell === null ? "NULL" : String(cell)}
                            >
                              {cell === null
                                ? <span style={{ opacity: 0.35 }}>NULL</span>
                                : String(cell)}
                            </td>
                          ))}
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>

              {/* Controles de paginación */}
              <div style={{ display: "flex", alignItems: "center", gap: "12px", marginTop: "10px", fontSize: "13px" }}>
                <button
                  className="staging-add-btn"
                  onClick={() => handlePageChange(dataPage - 1)}
                  disabled={dataPage <= 1 || loadingData}
                  style={{ padding: "4px 14px", fontSize: "13px" }}
                >
                  ← Anterior
                </button>
                <span style={{ color: "var(--text)", opacity: 0.8 }}>
                  Página {dataPage}
                  {tableData.total_pages > 0
                    ? ` de ${tableData.total_pages}${tableData.count_is_estimate ? " (aprox.)" : ""}`
                    : ""}
                </span>
                <button
                  className="staging-add-btn"
                  onClick={() => handlePageChange(dataPage + 1)}
                  disabled={isLastPage || loadingData}
                  style={{ padding: "4px 14px", fontSize: "13px" }}
                >
                  Siguiente →
                </button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
