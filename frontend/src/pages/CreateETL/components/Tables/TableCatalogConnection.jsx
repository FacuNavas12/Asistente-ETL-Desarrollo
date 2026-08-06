import { useState } from "react";
import { getTableData, getTableProfile } from "@/api/connections";
import TableConfirmPanel from "./TableConfirmPanel";
import { tableKey } from "./tableUtils";
import "../../css/shared.css";
import "../../css/inputConnection.css";

function splitTable(qualified) {
  const dotIdx = qualified.indexOf(".");
  return dotIdx === -1
    ? { schema: "", table: qualified }
    : { schema: qualified.slice(0, dotIdx), table: qualified.slice(dotIdx + 1) };
}

function mapCanonicalType(canonicalType) {
  switch (canonicalType) {
    case "integer":  return "int";
    case "number":   return "float";
    case "boolean":  return "bool";
    case "date":
    case "datetime":
    case "time":     return "date";
    default:         return "string";
  }
}

export default function TableCatalogConnection({ tables, connId, password, value, onChange }) {
  const [open, setOpen]                       = useState(false);
  const [selectedTable, setSelectedTable]     = useState(null);
  const [tableData, setTableData]             = useState(null);
  const [dataPage, setDataPage]               = useState(1);
  const [loadingData, setLoadingData]         = useState(false);
  const [dataError, setDataError]             = useState("");
  const [confirmingTable, setConfirmingTable] = useState(null);
  const [confirmError, setConfirmError]       = useState("");

  const handleSelectTable = async (qualified, page = 1) => {
    if (!connId) return;
    if (page === 1 && selectedTable?.qualified === qualified) {
      setSelectedTable(null);
      setTableData(null);
      setDataError("");
      return;
    }
    const { schema, table } = splitTable(qualified);
    setSelectedTable({ schema, table, qualified });
    setDataPage(page);
    setLoadingData(true);
    setDataError("");
    setTableData(null);
    try {
      const data = await getTableData(connId, schema, table, password, page);
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
      const canonicalSchema = await getTableProfile(connId, qualified, password);
      const columns = (canonicalSchema.fields ?? []).map(field => ({
        name:       field.name,
        dataType:   mapCanonicalType(field.type),
        dataFormat: field.format !== "default" ? field.format : "",
        role:       "atributo",
        data:       [],
      }));

      const { schema, table } = splitTable(qualified);
      const newTable = { tableName: table, connection_id: connId, schema_name: schema, columns };
      const rest = (Array.isArray(value) ? value : []).filter(t => tableKey(t) !== tableKey(newTable));
      onChange([...rest, newTable]);
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
    <div className="conn-catalog">
      <p className="conn-catalog-header">
        Tablas disponibles ({tables.length})
        {tables.length > 0 && (
          <span className="conn-catalog-hint">
            — clic en el nombre para previsualizar · confirmar para usar en el ETL
          </span>
        )}
      </p>
      <button className="origen-preview__toggle" onClick={() => setOpen(o => !o)}>
        {open ? "Ocultar" : "Ver tablas"}
      </button>
      {tables.length === 0 && (
        <p className="conn-catalog-empty">La conexión no expone tablas accesibles.</p>
      )}

      {tables.length > 0 && open && (
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
  );
}
