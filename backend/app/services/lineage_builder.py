"""
Generador de linaje de datos a partir del dict KTR o de su XML serializado.
Funciones puras y deterministas: no llaman al modelo, no emiten tokens.
Producen un grafo dirigido origen → staging → DWH listo para el frontend.
"""
from __future__ import annotations

import json
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

# Regex para extraer nombres de tabla de un SQL SELECT (FROM y cualquier JOIN).
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:\"?[\w]+\"?\.)?"  # FROM o JOIN, esquema opcional
    r"\"?([\w]+)\"?",                         # nombre de tabla
    re.IGNORECASE,
)


def _canonical(raw_type: str) -> str:
    return STEP_TYPE_ALIASES.get(raw_type, raw_type)


def _parse_config(raw) -> dict:
    """El LLM a veces serializa 'config' como string JSON en vez de objeto."""
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    return raw or {}


def _extract_table(canonical_type: str, config: dict) -> Optional[str]:
    if canonical_type in _TABLE_FIELD_TYPES:
        return config.get("table") or None
    if canonical_type == "CsvInput":
        return config.get("filename") or None
    if canonical_type == "TableInput":
        tables = _TABLE_RE.findall(config.get("sql", ""))
        return ", ".join(tables) if tables else None
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
        tabla = _extract_table(c_type, _parse_config(step.get("config", {})))
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


_K2_PREFIX = "K2::"


def stitch_lineage(ktr_data_1: dict, ktr_data_2: dict) -> Lineage:
    """
    Cose el linaje de KTR_1 (origen→STG) y KTR_2 (STG→DWH) en un único grafo
    origen→STG→DWH continuo, agregando un hop sintético por cada tabla de
    staging que un TableOutput sink de KTR_1 escribe y un TableInput source de
    KTR_2 lee (matcheados por nombre de tabla, no por posición).

    Los steps de KTR_2 se namespacean con el prefijo "K2::" — son 2 archivos
    generados por llamadas separadas al modelo, sin garantía de nombres de
    step únicos entre sí. Los de KTR_1 no se tocan.

    No modifica build_lineage(): la reusa tal cual sobre el grafo ya combinado,
    para que la clasificación de capa (que depende del grado del nodo) vea el
    grafo completo en vez de dos mitades desconectadas — un TableInput que hoy
    sería in_deg==0 dentro de KTR_2 solo (mal clasificado como "origen") deja
    de serlo una vez agregado el hop sintético que lo conecta al sink de KTR_1.

    Tolerante: si un TableInput de KTR_2 no matchea ningún sink de KTR_1 (el
    modelo no respetó los nombres de tabla fijados en el prompt), esa rama
    queda sin costura y build_lineage() la clasifica "origen" igual que hoy —
    señal visual del mismatch en vez de una excepción.
    """
    steps_1 = list(ktr_data_1.get("steps", []))
    hops_1  = list(ktr_data_1.get("hops", []))

    steps_2 = [
        {**s, "name": f"{_K2_PREFIX}{s.get('name', '')}"}
        for s in ktr_data_2.get("steps", [])
    ]
    hops_2 = [
        {**h, "from": f"{_K2_PREFIX}{h.get('from', '')}", "to": f"{_K2_PREFIX}{h.get('to', '')}"}
        for h in ktr_data_2.get("hops", [])
    ]

    out_deg_1: dict[str, int] = {s.get("name", ""): 0 for s in steps_1}
    for h in hops_1:
        if h.get("from") in out_deg_1:
            out_deg_1[h["from"]] += 1

    # Tablas STG escritas por un TableOutput sink en KTR_1 (sin hop saliente
    # dentro de KTR_1 — es el final de su rama).
    stg_sinks: dict[str, str] = {}
    for s in steps_1:
        name = s.get("name", "")
        if _canonical(s.get("type", "Dummy")) != "TableOutput" or out_deg_1.get(name, 0) != 0:
            continue
        tabla = _extract_table("TableOutput", _parse_config(s.get("config", {})))
        if tabla:
            stg_sinks[tabla.strip().lower()] = name

    in_deg_2: dict[str, int] = {s.get("name", ""): 0 for s in steps_2}
    for h in hops_2:
        if h.get("to") in in_deg_2:
            in_deg_2[h["to"]] += 1

    # Tablas STG leídas por un TableInput source en KTR_2 (sin hop entrante
    # dentro de KTR_2 — es el inicio de su rama) → hop sintético al sink que
    # escribió esa misma tabla en KTR_1.
    synthetic_hops: list[dict] = []
    for s in steps_2:
        name = s.get("name", "")
        if _canonical(s.get("type", "Dummy")) != "TableInput" or in_deg_2.get(name, 0) != 0:
            continue
        tablas = _extract_table("TableInput", _parse_config(s.get("config", {})))
        if not tablas:
            continue
        for tabla in (t.strip().lower() for t in tablas.split(",")):
            sink_step = stg_sinks.get(tabla)
            if sink_step:
                synthetic_hops.append({"from": sink_step, "to": name, "enabled": True})

    merged = {
        "steps": steps_1 + steps_2,
        "hops": hops_1 + hops_2 + synthetic_hops,
    }
    return build_lineage(merged)


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
