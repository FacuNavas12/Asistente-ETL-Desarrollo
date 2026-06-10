import { STAGING_METADATA_ENABLED, getAutoSourceSystem } from "./stagingMetadata";
import "../../css/shared.css";
import "../../css/stagingForm.css";

export function StagingMetadataSection({ meta, origenVinculado, onChange }) {
  if (!STAGING_METADATA_ENABLED) return null;
  return (
    <div className="stg-metadata-section">
      <p className="stg-section-label">Metadatos inyectados</p>
      <div className="stg-metadata-row">
        <div className="stg-meta-auto-item">
          <span className="stg-meta-auto-badge">AUTO</span>
          <span className="stg-meta-field-name">load_date</span>
          <span className="stg-meta-field-desc">Fecha y hora de carga</span>
        </div>
        <div className="stg-meta-auto-item">
          <span className="stg-meta-auto-badge">AUTO</span>
          <span className="stg-meta-field-name">batch_id</span>
          <span className="stg-meta-field-desc">ID de corrida · formato b_N</span>
        </div>
        <div className="stg-meta-source-item">
          <span className="stg-meta-field-name">source_system</span>
          <div className="form-field" style={{ flex: 1 }}>
            <input
              type="text"
              placeholder={origenVinculado ? `${origenVinculado}_ORIGEN` : "Seleccionar origen primero"}
              value={meta.sourceSystem}
              onChange={(e) => onChange(e.target.value)}
              disabled={!origenVinculado}
            />
            {origenVinculado && !meta.sourceSystem && (
              <span className="stg-meta-hint">Auto: {getAutoSourceSystem(origenVinculado)}</span>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

export function StagingMetaBadges({ table }) {
  if (!STAGING_METADATA_ENABLED) return null;
  const sourceSystem = table.metadata?.sourceSystem || getAutoSourceSystem(table.origenVinculado);
  return (
    <div className="stg-saved-meta">
      <span className="stg-saved-meta-badge">load_date</span>
      <span className="stg-saved-meta-badge">batch_id</span>
      {sourceSystem && (
        <span className="stg-saved-meta-badge stg-saved-meta-badge--source">{sourceSystem}</span>
      )}
    </div>
  );
}

