import { useState, useEffect } from "react";
import CollapsibleSection from "../components/CollapsibleSection";
import { useEtl } from "@/context/EtlContext";
import { rebuildEtlConnections } from "@/services/etlService";
import { listConnections } from "@/api/connections";
import DestinationConnectionForm, {
  EMPTY_DESTINATION_CONNECTION,
  isDestinationConnectionComplete,
} from "@/pages/CreateETL/components/Input/DestinationConnectionForm";
import "../etlDetail-global.css";
import "./ConnectionView.css";

const _toDestinationValue = (raw) =>
  raw && typeof raw === "object" ? { ...EMPTY_DESTINATION_CONNECTION, ...raw } : EMPTY_DESTINATION_CONNECTION;

const _toPayload = (value) => ({ ...value, port: Number(value.port) });

// Mismo formulario/checkbox que DestinationConnections (armado del ETL) pero
// disponible para un ETL YA generado: permite adaptar la conexión de
// origen/staging/DWH de un .ktr existente sin reabrir el wizard — el
// equivalente a editar el conector en Spoon, pero desde acá (ver POST
// /api/etls/{id}/connections, que reconstruye el .ktr desde el raw_data
// guardado sin volver a llamar al LLM). Nunca pide password — esta app no
// conecta de verdad contra staging/DWH ni contra un origen sin fila
// Connection guardada.
export default function ConnectionView({ etl }) {
  const { patchEtlLocal } = useEtl();
  const connectionsMap = etl.formData?.connectionsMap ?? {};

  // conn_origen string = id de una Connection guardada (se resolvió con el
  // explorador de esquema en vivo) — se edita desde la lista de conexiones,
  // no acá. Objeto o ausente = metadata inline o "Completar en Spoon", mismo
  // formulario editable que staging/DWH.
  //
  // rawOrigenIsSavedId es optimista (confía en el string tal cual está
  // guardado); origenIdStale lo corrige de forma asíncrona contra las
  // Connection reales del usuario — una fila borrada (o de otro owner) dejaba
  // este ETL sin forma de reparar el origen desde acá (ver
  // docs/refactor/02-decisiones.md). origenIsSavedId es lo que de verdad
  // gatea el render y el payload de "Guardar y regenerar .ktr".
  const rawOrigenIsSavedId = typeof connectionsMap.conn_origen === "string" && connectionsMap.conn_origen.length > 0;
  const [origenIdStale, setOrigenIdStale] = useState(false);
  const origenIsSavedId = rawOrigenIsSavedId && !origenIdStale;

  useEffect(() => {
    if (!rawOrigenIsSavedId) return;
    let cancelled = false;
    listConnections()
      .then(conns => {
        if (cancelled) return;
        const exists = Array.isArray(conns) && conns.some(c => c.id === connectionsMap.conn_origen);
        if (!exists) setOrigenIdStale(true);
      })
      .catch(() => {
        // No se pudo confirmar (red, backend caído) — mejor pedir el origen a
        // mano que arriesgar reenviar un id que puede ya no existir.
        if (!cancelled) setOrigenIdStale(true);
      });
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connectionsMap.conn_origen]);

  const [origenValue,  setOrigenValue]  = useState(_toDestinationValue(connectionsMap.conn_origen));
  const [origenSkip,   setOrigenSkip]   = useState(!connectionsMap.conn_origen);
  const [stagingValue, setStagingValue] = useState(_toDestinationValue(connectionsMap.conn_staging));
  const [dwhValue,     setDwhValue]     = useState(_toDestinationValue(connectionsMap.conn_dwh));
  const [stagingSkip,  setStagingSkip]  = useState(!connectionsMap.conn_staging);
  const [dwhSkip,       setDwhSkip]      = useState(!connectionsMap.conn_dwh);
  const [saving,  setSaving]  = useState(false);
  const [error,   setError]   = useState("");
  const [success, setSuccess] = useState(false);

  const canSave =
    (origenIsSavedId || origenSkip || isDestinationConnectionComplete(origenValue)) &&
    (stagingSkip || isDestinationConnectionComplete(stagingValue)) &&
    (dwhSkip || isDestinationConnectionComplete(dwhValue));

  const handleSave = async () => {
    setSaving(true);
    setError("");
    setSuccess(false);
    const body = {
      conn_origen: origenIsSavedId
        ? connectionsMap.conn_origen
        : (origenSkip ? undefined : _toPayload(origenValue)),
      conn_staging: stagingSkip ? undefined : _toPayload(stagingValue),
      conn_dwh: dwhSkip ? undefined : _toPayload(dwhValue),
    };
    try {
      const newResult = await rebuildEtlConnections(etl.id, body);
      patchEtlLocal(etl.id, {
        result: newResult,
        formData: { ...etl.formData, connectionsMap: body },
      });
      setSuccess(true);
    } catch (err) {
      setError(err.message ?? "No se pudo actualizar la conexión.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="etl-detail__body">
      <CollapsibleSection title="Conexión de origen">
        {origenIsSavedId ? (
          <p className="etl-section__text">
            {`Conexión configurada (id ${connectionsMap.conn_origen}) — se edita desde la lista de conexiones guardadas, no desde acá.`}
          </p>
        ) : (
          <>
            {rawOrigenIsSavedId && origenIdStale && (
              <p className="etl-section__text etl-section__text--warning">
                ⚠ La conexión guardada del origen (id {connectionsMap.conn_origen}) ya no existe — completá los datos a mano.
              </p>
            )}
            <label className="etl-connection-skip">
              <input type="checkbox" checked={origenSkip} onChange={e => setOrigenSkip(e.target.checked)} />
              Completar en Spoon (dejar host/usuario/base sin completar acá)
            </label>
            {!origenSkip && (
              <DestinationConnectionForm value={origenValue} onChange={setOrigenValue} />
            )}
          </>
        )}
      </CollapsibleSection>

      <CollapsibleSection title="Conexión de Staging">
        <label className="etl-connection-skip">
          <input type="checkbox" checked={stagingSkip} onChange={e => setStagingSkip(e.target.checked)} />
          Completar en Spoon (dejar host/usuario/base sin completar acá)
        </label>
        {!stagingSkip && (
          <DestinationConnectionForm value={stagingValue} onChange={setStagingValue} />
        )}
      </CollapsibleSection>

      <CollapsibleSection title="Conexión de DWH">
        <label className="etl-connection-skip">
          <input type="checkbox" checked={dwhSkip} onChange={e => setDwhSkip(e.target.checked)} />
          Completar en Spoon (dejar host/usuario/base sin completar acá)
        </label>
        {!dwhSkip && (
          <DestinationConnectionForm value={dwhValue} onChange={setDwhValue} />
        )}
      </CollapsibleSection>

      <div className="etl-connection-save">
        <button className="staging-add-btn" onClick={handleSave} disabled={!canSave || saving}>
          {saving ? "Guardando..." : "Guardar y regenerar .ktr"}
        </button>
        {success && <p className="etl-connection-save__ok">✓ .ktr actualizado con la nueva conexión.</p>}
        {error && <p className="conn-status-error">{error}</p>}
      </div>

      <CollapsibleSection title="Notas">
        <p className="etl-section__text">
          Esta app no guarda contraseñas de conexión — el .ktr descargado
          trae host/usuario/base de datos reales, pero el password hay que
          completarlo a mano en kettle.properties o en el conector de Spoon
          antes de ejecutarlo.
        </p>
        <p className="etl-section__text">
          Para exportar a Superset con datos reales, primero configurá la
          conexión al Data Warehouse a mano en Superset (Configuración →
          Conexiones a bases de datos) usando los datos de la conexión de
          arriba — esta app tampoco la configura automáticamente ahí.
        </p>
      </CollapsibleSection>
    </div>
  );
}
