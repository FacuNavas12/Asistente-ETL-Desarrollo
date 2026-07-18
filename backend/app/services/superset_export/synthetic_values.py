"""Genera un valor sintetico tipado a partir del nombre de una columna DWH, para
poblar filas de demo cuando no hay datos reales todavia (DWH recien creado, o
dwh_sample vacio en el resultado del ETL). El tipo del valor (int/float/bool/str)
es lo que despues permite a semantic_types clasificar la columna correctamente.
Port 1:1 de _syntheticValue en frontend/src/utils/supersetExport.js."""

from __future__ import annotations


def synthetic_value(col_name: str):
    u = col_name.upper()

    if u.startswith("SK_") or u.startswith("FK_") or u.startswith("ID_") or u.endswith("_ID") or u == "ID":
        return 1

    date_kw = ["FECHA", "DATE", "DT", "INICIO", "FIN", "COMIENZO"]
    if any(k in u for k in date_kw):
        return "2024-01-01"

    if (
        u.startswith("ES_")
        or u.startswith("IS_")
        or u.startswith("FLAG_")
        or "VIGENTE" in u
        or "ACTIVO" in u
        or "CAPITAL" in u
    ):
        return True

    num_kw = [
        "MONTO", "TOTAL", "PRECIO", "CANTIDAD", "QTY", "AREA", "POBLACION",
        "DENSIDAD", "DURACION", "DIAS", "PORCENTAJE", "TASA", "COSTO",
    ]
    if any(k in u for k in num_kw):
        return 0.0

    int_kw = [
        "ANIO", "MES", "DIA", "TRIMESTRE", "YEAR", "MONTH", "DAY", "ORDEN",
        "ORDER", "NUMERO", "NUM", "COUNT",
    ]
    if any(k in u for k in int_kw):
        return 1

    return "ejemplo"
