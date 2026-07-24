"""
KTR builder — paquete que serializa el ktr JSON del LLM a XML .ktr para Pentaho PDI.

Reexporta la API pública (y los símbolos privados que ya cubren tests/otros
servicios) para que `from app.services.ktr_builder import X` siga funcionando
igual que cuando este era un único módulo.

Ver build.py para el orquestador, registry.py para el mapeo de step types,
connection.py para resolución/serialización de conexiones, steps/ para los
builders de cada familia de step, layout.py para el auto-layout y validate.py
para la validación de estructura pre-XML.
"""
from app.services.ktr_builder.build import build_ktr
from app.services.ktr_builder.contracts import ConfigParseError, normalize_step_configs
from app.services.ktr_builder.connection import (
    _build_connection,
    _DB_TYPE_TO_KETTLE,
    _GENERIC_DRIVER_CLASS,
    _resolve_connection,
    resolve_real_connections,
)
from app.services.ktr_builder.dimension_step_policy import (
    OVERRIDE_STEP_PREFIX,
    derive_dimension_step_type,
    enforce_dimension_step_policy,
)
from app.services.ktr_builder.fragmentation import compute_cut, split_ktr_by_cut
from app.services.ktr_builder.layout import _auto_layout
from app.services.ktr_builder.registry import (
    KNOWN_PDI_STEP_TYPES,
    STEP_BUILDERS,
    STEP_TYPE_ALIASES,
)
from app.services.ktr_builder.repair import repair_integrity_gaps, repair_ktr_steps
from app.services.ktr_builder.validate import _validate_ktr

__all__ = [
    "build_ktr",
    "resolve_real_connections",
    "STEP_TYPE_ALIASES",
    "STEP_BUILDERS",
    "KNOWN_PDI_STEP_TYPES",
    "repair_ktr_steps",
    "repair_integrity_gaps",
    "derive_dimension_step_type",
    "enforce_dimension_step_policy",
    "OVERRIDE_STEP_PREFIX",
    "normalize_step_configs",
    "ConfigParseError",
    "compute_cut",
    "split_ktr_by_cut",
]
