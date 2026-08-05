"""
Borde de infraestructura del linaje: envuelve las reglas puras de
`app.domain.lineage` en el contrato de transporte real (`schemas.lineage.Lineage`,
Pydantic — no puede vivir en `domain/`, ver ese README) y parsea el XML .ktr
ya serializado para el camino inverso (`/api/ai/lineage-from-ktr`).

Split O2-c: `build_lineage`/`stitch_lineage_many`/`stitch_lineage` (grafo puro
sobre el dict KTR) viven ahora en `app.domain.lineage`. Acá solo queda la
conversión a `Lineage` y la lectura de XML.
"""
from __future__ import annotations

import logging
from xml.etree import ElementTree as ET

from app.domain.lineage import LineageGraphData
from app.domain.lineage import build_lineage as _build_lineage_graph
from app.domain.lineage import stitch_lineage_many as _stitch_lineage_graphs_many
from app.schemas.lineage import Lineage, LineageEdge, LineageNode

logger = logging.getLogger(__name__)


def _to_schema(graph: LineageGraphData) -> Lineage:
    return Lineage(
        nodes=[
            LineageNode(step_name=n.step_name, tipo_step=n.tipo_step, tabla=n.tabla, capa=n.capa)
            for n in graph.nodes
        ],
        edges=[LineageEdge(from_step=e.from_step, to_step=e.to_step) for e in graph.edges],
    )


def build_lineage(ktr_data: dict) -> Lineage:
    """Construye el grafo de linaje a partir del dict KTR devuelto por el LLM."""
    return _to_schema(_build_lineage_graph(ktr_data))


def stitch_lineage_many(ktr_data_list: list[dict]) -> Lineage:
    """Cose el linaje de M archivos KTR en un único grafo continuo. Ver
    `app.domain.lineage.stitch_lineage_many` para el algoritmo."""
    return _to_schema(_stitch_lineage_graphs_many(ktr_data_list))


def stitch_lineage(ktr_data_1: dict, ktr_data_2: dict) -> Lineage:
    """Caso M=2 de stitch_lineage_many() — origen→STG (KTR_1) y STG→DWH (KTR_2)."""
    return stitch_lineage_many([ktr_data_1, ktr_data_2])


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


def stitch_lineage_from_xml(ktr_xml_1: str, ktr_xml_2: str) -> Lineage:
    """Igual que stitch_lineage() pero parseando ambos KTR desde su XML serializado."""
    return stitch_lineage(_parse_ktr_xml(ktr_xml_1), _parse_ktr_xml(ktr_xml_2))
