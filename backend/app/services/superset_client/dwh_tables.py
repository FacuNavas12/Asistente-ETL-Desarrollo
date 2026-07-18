"""Siembra las tablas del DWH en la BD ETL_DWH de Superset vía SQL Lab API, a partir
de las columnas de los dataset YAMLs del ZIP — con write-gate para no pisar datos reales."""

from __future__ import annotations

import io
import logging
import zipfile

import httpx
import yaml

from app.services.superset_client.constants import DB_NAME, STAGING_PREFIXES

logger = logging.getLogger(__name__)


async def create_dwh_tables(
    client: httpx.AsyncClient,
    base: str,
    access_token: str,
    csrf_token: str,
    dwh_sample: dict,
    zip_bytes: bytes,
    real_table_status: dict[str, dict] | None = None,
) -> None:
    """
    Crea las tablas del DWH en la BD ETL_DWH de Superset usando SQL Lab API.
    Lee columnas desde los datasets YAML del ZIP (fuente primaria) y usa
    dwh_sample como fallback cuando el ZIP no tiene datos útiles.

    real_table_status (opcional): {tabla_lower: {"exists": bool, "rowCount": int}}
    del chequeo directo contra la conexión real (db_connector.check_dwh_tables).
    Toda tabla con filas reales se salta por completo — nunca se le hace
    DROP/CREATE/INSERT. Sin este parámetro (conn_dwh no resoluble) el
    comportamiento es el de siempre: siembra sin preguntar (caso demo).
    """
    auth_headers = {
        "Authorization": f"Bearer {access_token}",
        "X-CSRFToken": csrf_token,
        "Referer": base,
        "Content-Type": "application/json",
    }

    resp = await client.get(
        f"{base}/api/v1/database/",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"q": "(page_size:100)"},
        timeout=10,
    )
    db_id = None
    if resp.status_code == 200:
        for db in resp.json().get("result", []):
            if db.get("database_name") == DB_NAME:
                db_id = db.get("id")
                break

    if not db_id:
        logger.warning("No se encontró ETL_DWH para crear tablas del DWH")
        return

    # Enriquecer dwh_sample con columnas reales desde los datasets YAML del ZIP
    enriched_sample: dict = {}
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) >= 3 and parts[1] == "datasets" and name.endswith(".yaml"):
                    try:
                        data = yaml.safe_load(zf.read(name).decode("utf-8"))
                        table_name = data.get("table_name", "")
                        columns = data.get("columns", [])
                        if not table_name or not columns:
                            continue
                        if any(table_name.lower().startswith(p) for p in STAGING_PREFIXES):
                            continue
                        row = {}
                        for col in columns:
                            col_name = col.get("column_name", "")
                            col_type = col.get("type", "VARCHAR")
                            if not col_name:
                                continue
                            if "INT" in col_type.upper():
                                row[col_name] = 1
                            elif any(t in col_type.upper() for t in ("NUMERIC", "FLOAT", "DOUBLE")):
                                row[col_name] = 0.0
                            elif "BOOL" in col_type.upper():
                                row[col_name] = True
                            else:
                                row[col_name] = "ejemplo"
                        if row:
                            enriched_sample[table_name] = [row]
                    except Exception as exc:
                        logger.warning("No se pudo leer dataset YAML '%s': %s", name, exc)
    except Exception as exc:
        logger.warning("No se pudo leer el ZIP para enriquecer dwh_sample: %s", exc)

    final_sample = enriched_sample if enriched_sample else dwh_sample

    analytics_tables = {
        name: rows for name, rows in final_sample.items()
        if not any(name.lower().startswith(p) for p in STAGING_PREFIXES)
        and rows and len(rows) > 0 and rows[0]
    }

    def infer_sql_type(value) -> str:
        if isinstance(value, bool):
            return "BOOLEAN"
        if isinstance(value, int):
            return "INTEGER"
        if isinstance(value, float):
            return "NUMERIC"
        if isinstance(value, str) and len(value) == 10 and value[4] == "-":
            return "VARCHAR(20)"
        return "VARCHAR(255)"

    for table_name, rows in analytics_tables.items():
        sample_row = rows[0] if rows else {}
        if not sample_row:
            continue

        status = (real_table_status or {}).get(table_name.lower())
        if status and status.get("exists") and status.get("rowCount", 0) > 0:
            logger.info(
                "Tabla '%s' ya tiene %d fila(s) reales — se salta el seed sintético",
                table_name, status["rowCount"],
            )
            continue

        col_defs = [
            f'    "{col_name.lower()}" {infer_sql_type(col_value)}'
            for col_name, col_value in sample_row.items()
        ]
        create_sql = (
            f'DROP TABLE IF EXISTS "{table_name}";\n'
            f'CREATE TABLE "{table_name}" (\n'
            + ",\n".join(col_defs)
            + "\n);"
        )

        cols = [f'"{k.lower()}"' for k in sample_row.keys()]
        vals = []
        for v in sample_row.values():
            if v is None:
                vals.append("NULL")
            elif isinstance(v, bool):
                vals.append("TRUE" if v else "FALSE")
            elif isinstance(v, (int, float)):
                vals.append(str(v))
            else:
                vals.append(f"'{str(v).replace(chr(39), chr(39)*2)}'")

        insert_sql = (
            f'INSERT INTO "{table_name}" ({", ".join(cols)}) '
            f'VALUES ({", ".join(vals)}) '
            f'ON CONFLICT DO NOTHING;'
        )

        logger.info("Creando tabla DWH en Superset: %s", table_name)
        resp = await client.post(
            f"{base}/api/v1/sqllab/execute/",
            headers=auth_headers,
            json={
                "database_id": db_id,
                "sql": f"{create_sql}\n{insert_sql}",
                "schema": "public",
                "runAsync": False,
                "queryLimit": 1,
            },
            timeout=30,
        )
        if resp.status_code in (200, 201):
            logger.info("Tabla '%s' creada/verificada en Superset", table_name)
        else:
            logger.warning(
                "No se pudo crear tabla '%s' en Superset (%d): %s",
                table_name, resp.status_code, resp.text[:300],
            )
