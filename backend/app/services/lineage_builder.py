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
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES
from app.services.ktr_builder.contracts import normalize_config
from app.services.ktr_builder.contracts import parse_cfg as _parse_config

logger = logging.getLogger(__name__)

# Steps cuyo config tiene un campo "table" directo (post-normalize_config —
# ver _extract_table). DBLookup incluido (H11): antes quedaba invisible para
# el linaje pese a tocar tabla en modo lectura (ver H19 en 01-hallazgos.md).
_TABLE_FIELD_TYPES = {
    "TableOutput",
    "InsertUpdate",
    "Update",
    "Delete",
    "DimensionLookup",
    "CombinationLookup",
    "DBLookup",
}

# Regex para extraer nombres de tabla de un SQL SELECT (FROM y cualquier JOIN).
_TABLE_RE = re.compile(
    r"\b(?:FROM|JOIN)\s+(?:\"?[\w]+\"?\.)?"  # FROM o JOIN, esquema opcional
    r"\"?([\w]+)\"?",                         # nombre de tabla
    re.IGNORECASE,
)


def _canonical(raw_type: str) -> str:
    return STEP_TYPE_ALIASES.get(raw_type, raw_type)


def _extract_table(canonical_type: str, config: dict) -> Optional[str]:
    if canonical_type in _TABLE_FIELD_TYPES:
        # H4: alias de tabla (target_table/table_name -> table) resuelto vía
        # contracts.STEP_CONTRACTS.key_aliases — misma fuente que usa el
        # builder XML, no una copia propia que puede divergir.
        return normalize_config(canonical_type, config).get("table") or None
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


def _resolve_table_endpoints(
    ktr_data_list: list[dict],
) -> tuple[dict[str, tuple[str, int]], list[tuple[str, int, list[str]]], list[dict], list[dict]]:
    """Recorre ktr_data_list namespaceando steps/hops por índice de archivo
    (prefijo "F1::", "F2::", ... — el índice 0 sin prefijo) y detecta, por
    archivo, los sinks (TableOutput sin hop saliente propio) y sources
    (TableInput sin hop entrante propio) — el mismo matching escritor→lector
    que usa stitch_lineage_many() para coser el linaje, extraído acá para que
    otro caller (D23, validador de contrato entre KTR) pueda reusar el
    matching por nombre de tabla sin reimplementarlo.

    Devuelve (sinks, pending_sources, all_steps, all_hops):
      - sinks: {tabla_lower: (step_name, file_idx)} — último-en-ganar si dos
        archivos escriben la misma tabla (setdefault: primero-en-ganar).
      - pending_sources: [(step_name, file_idx, [tabla_lower, ...])].
      - all_steps/all_hops: steps y hops YA namespaceados, listos para
        build_lineage() una vez agregados los hops sintéticos.

    Solo tabla — nombre. Sin campos ni tipos: eso vive en una capa aparte
    (contracts.py del lado escritor + DDL parseado del lado lector), esta
    función no lo resuelve."""
    all_steps: list[dict] = []
    all_hops: list[dict] = []
    sinks: dict[str, tuple[str, int]] = {}
    pending_sources: list[tuple[str, int, list[str]]] = []

    for idx, ktr_data in enumerate(ktr_data_list):
        prefix = f"F{idx}::" if idx > 0 else ""
        steps = [
            {**s, "name": f"{prefix}{s.get('name', '')}"}
            for s in ktr_data.get("steps", [])
        ]
        hops = [
            {**h, "from": f"{prefix}{h.get('from', '')}", "to": f"{prefix}{h.get('to', '')}"}
            for h in ktr_data.get("hops", [])
        ]

        out_deg: dict[str, int] = {s.get("name", ""): 0 for s in steps}
        in_deg: dict[str, int] = {s.get("name", ""): 0 for s in steps}
        for h in hops:
            if h.get("from") in out_deg:
                out_deg[h["from"]] += 1
            if h.get("to") in in_deg:
                in_deg[h["to"]] += 1

        for s in steps:
            name = s.get("name", "")
            canonical = _canonical(s.get("type", "Dummy"))
            # Sink: TableOutput sin hop saliente dentro de su propio archivo
            # (es el final de su rama).
            if canonical == "TableOutput" and out_deg.get(name, 0) == 0:
                tabla = _extract_table("TableOutput", _parse_config(s.get("config", {})))
                if tabla:
                    sinks.setdefault(tabla.strip().lower(), (name, idx))
            # Source: TableInput sin hop entrante dentro de su propio archivo
            # (es el inicio de su rama).
            if canonical == "TableInput" and in_deg.get(name, 0) == 0:
                tablas = _extract_table("TableInput", _parse_config(s.get("config", {})))
                if tablas:
                    pending_sources.append((name, idx, [t.strip().lower() for t in tablas.split(",")]))

        all_steps.extend(steps)
        all_hops.extend(hops)

    return sinks, pending_sources, all_steps, all_hops


def stitch_lineage_many(ktr_data_list: list[dict]) -> Lineage:
    """
    F3 punto 3 (03-plan.md): generaliza stitch_lineage de 2 KTR fijos a M
    archivos. Cose el linaje de ktr_data_list[0..M-1] (en el orden de
    ejecución que ya vino dado — el de compute_cut() dentro de una etapa,
    y el de las etapas entre sí) en un único grafo continuo, agregando un hop
    sintético por cada tabla que un TableOutput sink de un archivo escribe y
    un TableInput source de OTRO archivo (no necesariamente el siguiente) lee
    (matcheados por nombre de tabla, no por posición ni adyacencia).

    Cada archivo a partir del segundo se namespacea con un prefijo por índice
    ("F1::", "F2::", ...) — son archivos generados por llamadas/grupos
    separados, sin garantía de nombres de step únicos entre sí. El primero
    (índice 0) no se prefija, para no romper el linaje del flujo legacy de 1
    solo KTR ni el caso M=1.

    No modifica build_lineage(): la reusa tal cual sobre el grafo ya
    combinado, para que la clasificación de capa (que depende del grado del
    nodo) vea el grafo completo en vez de M mitades desconectadas — un
    TableInput que sería in_deg==0 dentro de un archivo solo (mal clasificado
    como "origen") deja de serlo una vez agregado el hop sintético que lo
    conecta al sink que escribió esa tabla en otro archivo.

    Un sink y su source nunca se conectan si están en el MISMO archivo (evita
    un falso hop sintético dentro de una rama ya conectada por hops reales) —
    la única diferencia real de comportamiento frente al M=2 original, que no
    podía darse ese caso porque comparaba archivos distintos por construcción.

    Tolerante: si un TableInput no matchea ningún sink de otro archivo (el
    modelo no respetó los nombres de tabla fijados en el prompt), esa rama
    queda sin costura y build_lineage() la clasifica "origen" igual que hoy —
    señal visual del mismatch en vez de una excepción.
    """
    if not ktr_data_list:
        return build_lineage({})
    if len(ktr_data_list) == 1:
        return build_lineage(ktr_data_list[0])

    sinks, pending_sources, all_steps, all_hops = _resolve_table_endpoints(ktr_data_list)

    synthetic_hops: list[dict] = []
    for name, src_idx, tablas in pending_sources:
        for tabla in tablas:
            sink = sinks.get(tabla)
            if sink is not None and sink[1] != src_idx:
                synthetic_hops.append({"from": sink[0], "to": name, "enabled": True})

    return build_lineage({"steps": all_steps, "hops": all_hops + synthetic_hops})


def stitch_lineage(ktr_data_1: dict, ktr_data_2: dict) -> Lineage:
    """Caso M=2 de stitch_lineage_many() — origen→STG (KTR_1) y STG→DWH
    (KTR_2). Firma preservada por compatibilidad: la usa stitch_lineage_from_xml
    (routers/ai.py, endpoint público /api/ai/lineage-from-ktr que re-deriva
    linaje a partir de 2 XML ya servidos)."""
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
