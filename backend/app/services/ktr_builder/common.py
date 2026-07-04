"""Helper compartido por todos los builders de steps."""
from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement


def _sub(parent: Element, tag: str, text: str = "") -> Element:
    el = SubElement(parent, tag)
    if text:
        el.text = str(text)
    return el
