"""
Generador de linaje de datos a partir del dict KTR o de su XML serializado.
Funciones puras y deterministas: no llaman al modelo, no emiten tokens.
Producen un grafo dirigido origen → staging → DWH listo para el frontend.
"""
from __future__ import annotations

import logging
import re
from typing import Optional
from xml.etree import ElementTree as ET

from app.schemas.lineage import Lineage, LineageEdge, LineageNode
from app.services.ktr_builder import STEP_TYPE_ALIASES

logger = logging.getLogger(__name__)

# Steps cuyo config tiene un campo "table" directo.
_TABLE_FIELD_TYPES = {
    "TableOutput",
    "InsertUpdate",
    "Update",
    "Delete",
    "DimensionLookup",
    "CombinationLookup",
}

# Regex best-effort para extraer el nombre de tabla de un SQL SELECT.
_FROM_RE = re.compile(
    r"\bFROM\s+(?:\"?[\w]+\"?\.)?"  # esquema opcional
    r"\"?([\w]+)\"?",               # nombre de tabla
    re.IGNORECASE,
)


def _canonical(raw_type: str) -> str:
    return STEP_TYPE_ALIASES.get(raw_type, raw_type)


def _extract_table(canonical_type: str, config: dict) -> Optional[str]:
    if canonical_type in _TABLE_FIELD_TYPES:
        return config.get("table") or None
    if canonical_type == "CsvInput":
        return config.get("filename") or None
    if canonical_type == "TableInput":
        m = _FROM_RE.search(config.get("sql", ""))
        return m.group(1) if m else None
    return None


def _classify_layer(
    in_deg: int,
    out_deg: int,
    tabla: Optional[str],
) -> str:
    """
    Clasifica la capa del step por posición en el DAG (autoritativa).
    La convención de nombres refina solo en el caso de sinks (out_deg == 0)
    donde STG_ vs DIM_/FACT_ es la única señal disponible.
    """
    if in_deg == 0:
        return "origen"

    if out_deg == 0:
        if tabla:
            upper = tabla.upper()
            if upper.startswith(("DIM_", "FACT_")):
                return "dwh"
            if upper.startswith("STG_"):
                return "staging"
        return "dwh"

    return "staging"


def build_lineage(ktr_data: dict) -> Lineage:
    """
    Construye el grafo de linaje a partir del dict KTR devuelto por el LLM.
    Tolera hops rotos: los saltea con log.warning sin lanzar excepción.
    """
    steps = ktr_data.get("steps", [])
    hops = ktr_data.get("hops", [])

    step_index: dict[str, dict] = {s["name"]: s for s in steps}

    in_deg: dict[str, int] = {name: 0 for name in step_index}
    out_deg: dict[str, int] = {name: 0 for name in step_index}

    valid_hops: list[dict] = []
    for hop in hops:
        frm = hop.get("from", "")
        to = hop.get("to", "")
        if frm not in step_index:
            logger.warning("lineage: hop desde step desconocido '%s' — omitido", frm)
            continue
        if to not in step_index:
            logger.warning("lineage: hop hacia step desconocido '%s' — omitido", to)
            continue
        out_deg[frm] += 1
        in_deg[to] += 1
        valid_hops.append(hop)

    nodes: list[LineageNode] = []
    for name, step in step_index.items():
        raw_type = step.get("type", "Dummy")
        c_type = _canonical(raw_type)
        tabla = _extract_table(c_type, step.get("config", {}))
        capa = _classify_layer(in_deg[name], out_deg[name], tabla)
        nodes.append(LineageNode(
            step_name=name,
            tipo_step=c_type,
            tabla=tabla,
            capa=capa,
        ))

    edges: list[LineageEdge] = [
        LineageEdge(from_step=h["from"], to_step=h["to"])
        for h in valid_hops
    ]

    return Lineage(nodes=nodes, edges=edges)


def _parse_ktr_xml(ktr_xml: str) -> dict:
    """
    Reconstruye el dict mínimo que necesita build_lineage() a partir del XML .ktr.
    Solo extrae los campos que el builder de linaje consume: name, type, sql, table, filename.
    """
    try:
        root = ET.fromstring(ktr_xml)
    except ET.ParseError as exc:
        logger.error("lineage: XML inválido — %s", exc)
        return {}

    steps = []
    for step_el in root.findall("step"):
        name  = step_el.findtext("name",     "").strip()
        stype = step_el.findtext("type",     "Dummy").strip()
        if not name:
            continue
        steps.append({
            "name": name,
            "type": stype,
            "config": {
                "sql":      step_el.findtext("sql",      "") or "",
                "table":    step_el.findtext("table",    "") or "",
                "filename": step_el.findtext("filename", "") or "",
            },
        })

    hops = []
    for hop_el in root.findall("order/hop"):
        frm = hop_el.findtext("from", "").strip()
        to  = hop_el.findtext("to",   "").strip()
        if frm and to:
            hops.append({"from": frm, "to": to})

    return {"steps": steps, "hops": hops}


def build_lineage_from_xml(ktr_xml: str) -> Lineage:
    """Genera el linaje directamente desde el string XML de un .ktr ya serializado."""
    return build_lineage(_parse_ktr_xml(ktr_xml))
