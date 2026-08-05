"""
JSON Schema definitions for all LLM structured outputs.

Rules applied to every schema:
- additionalProperties: false on all object nodes where structure is known.
- All fields in required[] (optionals converted to nullable + required).
- $ref/$defs avoided — schemas are fully inlined for Gemini compatibility.
- Fields whose values are truly variable-shape dicts (ktr step config,
  dwh_sample) use {"type": "object"} without additionalProperties constraint;
  these are documented with a comment in their respective schema files.
"""
from app.schemas.llm_output_schemas.etl_output import ETL_OUTPUT_SCHEMA
from app.schemas.llm_output_schemas.inference_output import INFERENCE_OUTPUT_SCHEMA
from app.schemas.llm_output_schemas.validator_output import VALIDATOR_OUTPUT_SCHEMA
from app.schemas.llm_output_schemas.document_output import DOCUMENT_OUTPUT_SCHEMA
from app.schemas.llm_output_schemas.job_plan_output import JOB_PLAN_OUTPUT_SCHEMA
from app.schemas.llm_output_schemas.job_explain_output import JOB_EXPLAIN_OUTPUT_SCHEMA
from app.schemas.llm_output_schemas.ddl_validation_output import DDL_VALIDATION_OUTPUT_SCHEMA

__all__ = [
    "ETL_OUTPUT_SCHEMA",
    "INFERENCE_OUTPUT_SCHEMA",
    "VALIDATOR_OUTPUT_SCHEMA",
    "DOCUMENT_OUTPUT_SCHEMA",
    "JOB_PLAN_OUTPUT_SCHEMA",
    "JOB_EXPLAIN_OUTPUT_SCHEMA",
    "DDL_VALIDATION_OUTPUT_SCHEMA",
]
