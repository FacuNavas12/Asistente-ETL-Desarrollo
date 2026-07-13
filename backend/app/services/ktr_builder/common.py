"""Helper compartido por todos los builders de steps."""
from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement


def _sub(parent: Element, tag: str, text: str = "") -> Element:
    el = SubElement(parent, tag)
    if text:
        el.text = str(text)
    return el


def _yn(value, default: bool = False) -> str:
    """Normaliza un valor de config (bool | 'Y'/'N' | 'true'/'false' | None) a
    'Y'/'N' para XML PDI. Un string no vacío es truthy en Python — sin este
    helper, config.get('truncate') == 'N' (string literal del LLM) evalúa
    truthy y emite 'Y', invirtiendo la intención declarada."""
    if value is None:
        value = default
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("y", "yes", "true", "1"):
            return "Y"
        if v in ("n", "no", "false", "0", ""):
            return "N"
        return "Y"
    return "Y" if value else "N"


class KtrBuilderError(ValueError):
    """El ktr JSON no se puede serializar de forma segura: step type sin
    emisor registrado o grafo de campos inconsistente (campo referenciado que
    ningún step aguas arriba produce). No es un bug del builder — señala que
    el JSON del modelo está mal formado; abortar acá evita entregar un .ktr
    que Spoon rechaza sin explicación."""
