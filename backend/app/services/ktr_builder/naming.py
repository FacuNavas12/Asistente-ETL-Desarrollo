"""Punto único de generación de nombres de archivo .ktr/.kjb.

Ningún otro módulo arma estos strings a mano — todos importan de acá. Evita
que la convención de nombres diverja entre build.py (.ktr por etapa/corte) y
etl_generator.py (.kjb maestro/orquestador), que hoy la generaban cada uno
por su lado.

No confundir con `EtapaOutput.nombre` (schemas/job_schemas.py vía
etl_generator._etapa_output) — ese es el label de etapa que consume el
frontend (folder del ZIP, UI del drawer, progress polling) y vive fuera de
este módulo a propósito: cambiarlo tiene blast radius grande (CreateETL.jsx,
progressLog.js, ModelResponsesDrawer.jsx, job_progress.py). `_STAGE_TOKENS`
de acá abajo es una traducción cosmética SOLO para texto de archivo, no
reemplaza ni renombra esos labels.

Convención (orden fijo tipo-keyword-ETAPA-fecha_hora; partido: N-tipo-keyword-ETAPA-fecha_hora):
    ktr-<keyword>-<ETAPA>-<fecha_hora>.ktr
    N-ktr-<keyword>-<ETAPA>-<fecha_hora>.ktr      (N = 1-based, ktr partido por compute_cut())
    job-<keyword>-principal-<fecha_hora>.kjb      (kjb maestro)
    job-<keyword>-<ETAPA>-<fecha_hora>.kjb        (kjb orquestador de una etapa partida)

'-' separa CAMPOS, '_' queda reservado a texto dentro de un campo (ej.
ORG_STG). El keyword nunca puede contener '-'/'_' — corrompería el conteo de
campos para quien lee el nombre a simple vista (ver _keyword_sanitize)."""

from __future__ import annotations

import random
import re
import string
import unicodedata
from datetime import datetime

_ID_ALPHABET = string.ascii_lowercase + string.digits


def _random_id(n: int = 4) -> str:
    """Última red de seguridad: nombrar un archivo nunca puede ser la razón
    por la que se corta una generación. Si no hay ni un solo caracter
    aprovechable en process_name, un id random reemplaza al keyword en vez
    de fallar."""
    return "".join(random.choices(_ID_ALPHABET, k=n))


_STAGE_TOKENS = {
    "origen_stg": "ORG_STG",
    "stg_dwh": "STG_DWH",
    "proceso": "ETL",
}

# Palabras de relleno típicas de un nombre de proceso ETL en español — se
# descartan al buscar la primera palabra "con contenido" para el keyword.
_FILLER_WORDS = frozenset({
    "consolidacion", "consolidado", "actualizacion", "actualizado",
    "proceso", "procesos", "etl", "carga", "cargas", "generacion",
    "integracion", "sincronizacion", "migracion", "staging", "stg", "dwh",
    "datos", "dato", "base", "origen",
})
_STOPWORDS = frozenset({
    "de", "del", "la", "el", "los", "las", "a", "al", "con", "para",
    "por", "en", "y", "o", "un", "una", "unos", "unas",
})


def _strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def _keyword_sanitize(word: str) -> str:
    """Un único token de keyword: alfanumérico puro, sin '-'/'_' (son
    separadores de campo en el nombre de archivo)."""
    return re.sub(r"[^a-zA-Z0-9]", "", _strip_accents(word)) or "etl"


def derive_keyword(process_name: str) -> str:
    """1 palabra corta para diferenciar archivos a simple vista — heurística,
    no exacta (el usuario renombra a mano si hace falta). Descarta stopwords +
    relleno típico de nombres de proceso ETL y toma la primera palabra que
    sobrevive; si ninguna sobrevive, usa la primera palabra tal cual."""
    words = re.findall(r"[^\W_]+", process_name or "", flags=re.UNICODE)
    for w in words:
        wl = _strip_accents(w.lower())
        # len<2 filtra fragmentos sin contenido propio (ej. "e-commerce" -> "e") —
        # no son stopwords conocidas pero tampoco sirven para diferenciar nada.
        if len(wl) < 2 or wl in _STOPWORDS or wl in _FILLER_WORDS:
            continue
        return _keyword_sanitize(w.lower())
    if words:
        return _keyword_sanitize(words[0].lower())
    # process_name vacío/sin ningún caracter alfanumérico — "falta de nombre"
    # real, no solo relleno. Id random en vez de fallar la generación por esto.
    return _random_id()


def stage_token(etapa_label: str) -> str:
    return _STAGE_TOKENS.get(etapa_label, etapa_label.upper()) if etapa_label else "ETL"


def _timestamp() -> str:
    """Fecha+hora, sin milisegundos — un campo compuesto (no dos): '_' separa
    fecha de hora ADENTRO de este único campo, '-' sigue separando campos
    distintos alrededor de él."""
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def ktr_filename(process_name: str, etapa_label: str = "", index: int | None = None) -> str:
    base = f"ktr-{derive_keyword(process_name)}-{stage_token(etapa_label)}-{_timestamp()}.ktr"
    return f"{index}-{base}" if index else base


def kjb_filename(process_name: str, etapa_label: str | None = None) -> str:
    stage = stage_token(etapa_label) if etapa_label else "principal"
    return f"job-{derive_keyword(process_name)}-{stage}-{_timestamp()}.kjb"
