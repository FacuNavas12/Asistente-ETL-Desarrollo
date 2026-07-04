import { useState } from "react";
import { listTables } from "@/api/connections";
import "../../css/shared.css";
import "../../css/inputConnection.css";
import ConnectionForm from "./ConnectionForm";
import TableCatalogConnection from "../Tables/TableCatalogConnection";

export default function InputConection({ value, onChange }) {
  const [tables, setTables]     = useState([]);
  const [connId, setConnId]     = useState(null);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState("");

  const handleConnected = async (id) => {
    setConnId(id);
    setTables([]);
    setError("");
    setLoading(true);
    try {
      const tableList = await listTables(id);
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
          value={value}
          onChange={onChange}
        />
      )}
    </div>
  );
}
