"""
Lint post-generación: parsea el .ktr XML YA serializado (no el JSON del modelo)
y RECHAZA con KtrXmlValidationError si quedó estructuralmente inválido para
Spoon. Última barrera, después de ktr_builder.build_ktr() haber aplicado sus
propias correcciones (conexión GENERIC con driver, GetSystemInfo con fields
por defecto, etc.) — si algo se escapa igual, mejor fallar acá con un mensaje
claro que entregar un .ktr que Spoon rechaza sin explicación.
"""
from __future__ import annotations

from xml.etree.ElementTree import Element, fromstring

# Steps que requieren, además de existir, al menos un elemento hijo específico
# con contenido — sin esto el step queda "vacío" y Spoon lo marca inválido.
# (tag_contenedor, tag_hijo_requerido)
_STEP_REQUIRED_CHILDREN: dict[str, tuple[str, str]] = {
    "GetSystemInfo": ("fields", "field"),
}


class KtrXmlValidationError(ValueError):
    """El .ktr generado no cumple una invariante estructural fatal. issues
    trae el detalle completo (uno o más problemas) para mostrarlo al usuario."""

    def __init__(self, issues: list[str]):
        self.issues = issues
        super().__init__("KTR inválido: " + " | ".join(issues))


def _attribute_value(attributes_el: Element | None, code: str) -> str | None:
    if attributes_el is None:
        return None
    for attr in attributes_el.findall("attribute"):
        if attr.findtext("code") == code:
            return attr.findtext("attribute")
    return None


def _check_generic_connections(root: Element, strict_connections: bool = False) -> list[str]:
    issues: list[str] = []
    for conn in root.findall("connection"):
        conn_name = conn.findtext("name", "")
        conn_type = (conn.findtext("type") or "").strip().upper()
        if conn_type != "GENERIC":
            continue
        attributes = conn.find("attributes")
        driver = _attribute_value(attributes, "CUSTOM_DRIVER_CLASS")
        url = _attribute_value(attributes, "CUSTOM_URL")
        if not driver or not driver.strip():
            issues.append(f"Conexión '{conn_name}': tipo GENERIC sin CUSTOM_DRIVER_CLASS.")
        if not url or not url.strip():
            issues.append(f"Conexión '{conn_name}': tipo GENERIC sin CUSTOM_URL.")
        if strict_connections:
            server = (conn.findtext("server") or "").strip().upper()
            database = (conn.findtext("database") or "").strip().upper()
            if server == "PLACEHOLDER_HOST" or "PLACEHOLDER_" in database:
                issues.append(
                    f"Conexión '{conn_name}': quedó sin resolver (host/base de datos placeholder) "
                    "después de intentar resolver las conexiones reales del job — no se puede "
                    "entregar un .ktr final con credenciales de conexión sin completar. Verificar "
                    f"que '{conn_name}' esté correctamente asociada en el paso de conexiones del job."
                )
    return issues


def _check_step_required_children(root: Element) -> list[str]:
    issues: list[str] = []
    for step in root.findall("step"):
        step_name = step.findtext("name", "")
        step_type = step.findtext("type", "")
        required = _STEP_REQUIRED_CHILDREN.get(step_type)
        if required is None:
            continue
        container_tag, child_tag = required
        container = step.find(container_tag)
        if container is None or not container.findall(child_tag):
            issues.append(
                f"Step '{step_name}' (type {step_type}): falta <{container_tag}><{child_tag}>, "
                "queda vacío/inválido para Spoon."
            )
    return issues


def _check_hops_reference_existing_steps(root: Element) -> list[str]:
    issues: list[str] = []
    step_names = {s.findtext("name") for s in root.findall("step")}
    order = root.find("order")
    if order is None:
        return issues
    for hop in order.findall("hop"):
        src, dst = hop.findtext("from"), hop.findtext("to")
        if src not in step_names:
            issues.append(f"Hop referencia step inexistente en origen: '{src}'.")
        if dst not in step_names:
            issues.append(f"Hop referencia step inexistente en destino: '{dst}'.")
    return issues


def validate_ktr_xml(ktr_xml: str, strict_connections: bool = False) -> None:
    """Levanta KtrXmlValidationError si el XML ya serializado viola alguna
    invariante fatal. No hace nada (silencioso) si todo está OK.

    strict_connections=True agrega el chequeo de conexiones sin resolver
    (server/database placeholder) como error fatal — usar SOLO en el flujo
    que ya intentó resolver conexiones reales (ver _try_build en
    etl_generator.py); en los demás flujos (preview sin conexiones aún
    elegidas) las conexiones placeholder son esperadas."""
    root = fromstring(ktr_xml)

    issues: list[str] = [
        *_check_generic_connections(root, strict_connections),
        *_check_step_required_children(root),
        *_check_hops_reference_existing_steps(root),
    ]
    if issues:
        raise KtrXmlValidationError(issues)
