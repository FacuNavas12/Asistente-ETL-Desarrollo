import { useState } from "react";
import { createConnection, testConnection, listTables, getTableData, getColumns } from "@/api/connections";
import TableConfirmPanel from "../Tables/TableConfirmPanel";
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
  idle:          "Conectar",
  creating:      "Creando conexión...",
  testing:       "Probando conexión...",
  loadingTables: "Cargando tablas...",
  success:       "Conectar de nuevo",
  error:         "Conectar",
};

const BUSY = new Set(["creating", "testing", "loadingTables"]);

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

  const [selectedTable, setSelectedTable] = useState(null);
  const [tableData, setTableData]         = useState(null);
  const [dataPage, setDataPage]           = useState(1);
  const [loadingData, setLoadingData]     = useState(false);
  const [dataError, setDataError]         = useState("");

  const [confirmingTable, setConfirmingTable] = useState(null);
  const [confirmError, setConfirmError]       = useState("");

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

      const payload = form.db_type === "postgresql"
        ? { ...base, ssl_mode: form.ssl_mode }
        : form.trustServerCert
          ? { ...base, extra_options: { trust_server_certificate: true } }
          : { ...base };

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
    } catch (err) {
      setConfirmError(`No se pudo confirmar "${qualified}": ${err.message}`);
    } finally {
      setConfirmingTable(null);
    }
  };

  const isLastPage = tableData
    ? tableData.rows.length < tableData.page_size ||
      (tableData.total_pages > 0 && dataPage >= tableData.total_pages)
    : true;

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
        {STATUS_LABELS[status]}
      </button>

      {status === "error" && error && (
        <p className="conn-status-error">{error}</p>
      )}

      {/* Catálogo de tablas */}
      {status === "success" && (
        <div className="conn-catalog">
          <p className="conn-catalog-header">
            Tablas disponibles ({tables.length})
            {tables.length > 0 && (
              <span className="conn-catalog-hint">
                — clic en el nombre para previsualizar · confirmar para usar en el ETL
              </span>
            )}
          </p>

          {tables.length === 0 ? (
            <p className="conn-catalog-empty">La conexión no expone tablas accesibles.</p>
          ) : (
            <TableConfirmPanel
              candidates={tables}
              value={value}
              onChange={onChange}
              onConfirm={handleConfirmTable}
              confirmingTable={confirmingTable}
              confirmError={confirmError}
              onSelectTable={handleSelectTable}
              selectedTable={selectedTable?.qualified}
            >
              {/* Preview de filas de la DB */}
              {selectedTable && (
                <div className="conn-preview">
                  <div className="conn-preview-header">
                    <span className="conn-preview-name">{selectedTable.qualified}</span>
                    {tableData && (
                      <span className="conn-preview-meta">
                        {tableData.total_count === -1
                          ? "sin estadísticas de filas"
                          : `~${tableData.total_count.toLocaleString()} filas${tableData.count_is_estimate ? " (estimado)" : ""}`
                        }
                      </span>
                    )}
                  </div>

                  {loadingData && (
                    <p className="conn-preview-loading">Cargando datos...</p>
                  )}
                  {dataError && (
                    <p className="conn-preview-error">{dataError}</p>
                  )}

                  {tableData && !loadingData && (
                    <>
                      <div className="staging-table-wrapper" style={{ overflowX: "auto" }}>
                        <table className="staging-table">
                          <thead>
                            <tr>
                              {tableData.columns.map(col => (
                                <th key={col} className="conn-preview-col">{col}</th>
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
                                      className="conn-preview-cell-data"
                                      title={cell === null ? "NULL" : String(cell)}
                                    >
                                      {cell === null
                                        ? <span className="conn-preview-null">NULL</span>
                                        : String(cell)}
                                    </td>
                                  ))}
                                </tr>
                              ))
                            )}
                          </tbody>
                        </table>
                      </div>

                      {/* Paginación */}
                      <div className="conn-pagination">
                        <button
                          className="staging-add-btn conn-pagination-btn"
                          onClick={() => handlePageChange(dataPage - 1)}
                          disabled={dataPage <= 1 || loadingData}
                        >
                          ← Anterior
                        </button>
                        <span className="conn-pagination-info">
                          Página {dataPage}
                          {tableData.total_pages > 0
                            ? ` de ${tableData.total_pages}${tableData.count_is_estimate ? " (aprox.)" : ""}`
                            : ""}
                        </span>
                        <button
                          className="staging-add-btn conn-pagination-btn"
                          onClick={() => handlePageChange(dataPage + 1)}
                          disabled={isLastPage || loadingData}
                        >
                          Siguiente →
                        </button>
                      </div>
                    </>
                  )}
                </div>
              )}
            </TableConfirmPanel>
          )}
        </div>
      )}
    </div>
  );
}
