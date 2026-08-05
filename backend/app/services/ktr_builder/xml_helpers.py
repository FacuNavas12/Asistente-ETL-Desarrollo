"""
Helper de serialización XML — infraestructura: arma nodos de
`xml.etree.ElementTree`, sin conocimiento de dominio. Split de common.py
(sesión de arquitectura O2-a): el criterio que separa este módulo de
common.py es el mismo de step_types.py/step_emitters.py — acá vive cómo se
arma el árbol XML, no qué significa un valor de config (eso quedó en
common.py, domain).
"""
from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement


def _sub(parent: Element, tag: str, text: str = "") -> Element:
    el = SubElement(parent, tag)
    if text:
        el.text = str(text)
    return el
