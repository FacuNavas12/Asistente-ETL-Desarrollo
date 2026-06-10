export const STAGING_METADATA_ENABLED = true;

export const EMPTY_METADATA = { sourceSystem: "" };

export const getAutoSourceSystem = (origenVinculado) =>
  origenVinculado ? `${origenVinculado}_ORIGEN` : "";

