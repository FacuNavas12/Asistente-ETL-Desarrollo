"""
Lint post-generación del .kjb — última barrera, análoga a ktr_xml_validator.py
pero para Jobs PDI (ver job_analyzer.build_kjb_xml). Valida invariantes
estructurales que Spoon necesita para abrir/ejecutar el job: coordenadas de
<entry> en formato plano (JobEntryCopy — sin <GUI>, que es el formato de
StepMeta usado en .ktr), al menos una entrada TRANS, ningún hop hacia un
nombre de entrada inexistente, y un camino conectado START→...→SUCCESS.
"""
from __future__ import annotations

from xml.etree.ElementTree import Element, fromstring


class KjbXmlValidationError(ValueError):
    """El .kjb generado no cumple una invariante estructural fatal. issues
    trae el detalle completo (uno o más problemas) para mostrarlo al usuario."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("KJB inválido: " + " | ".join(issues))


def _check_flat_coords(root: Element) -> list[str]:
    issues: list[str] = []
    for entry in root.findall("./entries/entry"):
        name = entry.findtext("name", "")
        if entry.find("GUI") is not None:
            issues.append(
                f"Entrada '{name}': coordenadas dentro de <GUI> — ese es el formato de step de "
                ".ktr (StepMeta), no de entry de .kjb (JobEntryCopy). Spoon no las encuentra ahí, "
                "las pone en (0,0) apiladas en la esquina y el canvas parece vacío."
            )
        if entry.find("xloc") is None or entry.find("yloc") is None:
            issues.append(f"Entrada '{name}': sin coordenadas xloc/yloc como hijos directos de <entry>.")
    return issues


def _check_has_trans_entry(root: Element) -> list[str]:
    """Al menos una entrada que orqueste trabajo real: TRANS (.ktr) o JOB
    (.kjb hijo — H7/F2.5). Un job_master.kjb de la jerarquía de 3 niveles
    puede ser enteramente JOB (delega en job_origen_stg.kjb/job_stg_dwh.kjb,
    que a su vez tienen las entradas TRANS) — exigir TRANS acá lo rechazaría
    aunque sea válido."""
    types = {e.findtext("type") for e in root.findall("./entries/entry")}
    if not (types & {"TRANS", "JOB"}):
        return ["El job no tiene ninguna entrada TRANS ni JOB — no orquesta ninguna transformación .ktr ni job .kjb hijo."]
    return []


def _check_hops_reference_existing_entries(root: Element) -> list[str]:
    issues: list[str] = []
    names = {e.findtext("name") for e in root.findall("./entries/entry")}
    for hop in root.findall("./hops/hop"):
        src, dst = hop.findtext("from"), hop.findtext("to")
        if src not in names:
            issues.append(f"Hop referencia entrada inexistente en origen: '{src}'.")
        if dst not in names:
            issues.append(f"Hop referencia entrada inexistente en destino: '{dst}'.")
    return issues


def _check_connected_path(root: Element) -> list[str]:
    names = {e.findtext("name") for e in root.findall("./entries/entry")}
    if "START" not in names or "SUCCESS" not in names:
        return []  # entrada START/SUCCESS faltante ya es un problema distinto, no lo duplicamos acá

    adj: dict[str, list[str]] = {n: [] for n in names}
    for hop in root.findall("./hops/hop"):
        if (hop.findtext("enabled", "Y") or "Y") != "Y":
            continue
        src, dst = hop.findtext("from"), hop.findtext("to")
        if src in adj and dst in adj:
            adj[src].append(dst)

    seen = {"START"}
    stack = ["START"]
    while stack:
        n = stack.pop()
        for m in adj.get(n, []):
            if m not in seen:
                seen.add(m)
                stack.append(m)

    if "SUCCESS" not in seen:
        return ["No hay camino conectado START→...→SUCCESS siguiendo hops habilitados."]
    return []


def validate_kjb_xml(kjb_xml: str) -> None:
    """Levanta KjbXmlValidationError si el XML ya serializado viola alguna
    invariante fatal. No hace nada (silencioso) si todo está OK."""
    root = fromstring(kjb_xml)

    issues: list[str] = [
        *_check_flat_coords(root),
        *_check_has_trans_entry(root),
        *_check_hops_reference_existing_entries(root),
        *_check_connected_path(root),
    ]
    if issues:
        raise KjbXmlValidationError(issues)
