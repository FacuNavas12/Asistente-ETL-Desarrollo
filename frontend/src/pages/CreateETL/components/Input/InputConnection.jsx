import { useState } from "react";
import { listTables } from "@/api/connections";
import "../../css/shared.css";
import "../../css/inputConnection.css";
import ConnectionForm from "./ConnectionForm";
import TableCatalogConnection from "../Tables/TableCatalogConnection";

export default function InputConection({ value, onChange }) {
  const [tables, setTables]     = useState([]);
  const [connId, setConnId]     = useState(null);
  // El password nunca se persiste en el backend — se mantiene acá en memoria
  // (nunca en sessionStorage/localStorage) mientras dura esta pantalla, para
  // reenviarlo en cada llamada de exploración (list/columns/profile/data).
  const [password, setPassword] = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  const handleConnected = async (id, _meta, connPassword) => {
    setConnId(id);
    setPassword(connPassword);
    setTables([]);
    setError("");
    setLoading(true);
    try {
      const tableList = await listTables(id, connPassword);
      setTables(tableList);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <ConnectionForm onConnected={handleConnected} />

      {loading && <p>Cargando tablas...</p>}
      {error && <p className="conn-status-error">{error}</p>}

      {connId && !loading && (
        <TableCatalogConnection
          tables={tables}
          connId={connId}
          password={password}
          value={value}
          onChange={onChange}
        />
      )}
    </div>
  );
}
