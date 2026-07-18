"""Orquestación del import de dashboards: fallback paso a paso cuando assets/import/
falla, fix de chartId post-import, y resolución de la URL final del dashboard."""

from __future__ import annotations

import io
import logging
import zipfile

import httpx
import yaml

from app.services.superset_client.charts import create_charts_from_zip, list_all_charts
from app.services.superset_client.constants import DB_NAME
from app.services.superset_client.datasets import create_datasets_from_zip
from app.services.superset_client.dwh_tables import create_dwh_tables
from app.services.superset_client.errors import SupersetError
from app.services.superset_client.zip_tools import _extract_dashboard_uuid, _make_section_zip

logger = logging.getLogger(__name__)


async def import_step_by_step(
    client: httpx.AsyncClient,
    base: str,
    headers: dict,
    zip_bytes: bytes,
    real_table_status: dict[str, dict] | None = None,
) -> None:
    """
    Importa datasets → charts → dashboard, luego hace PUT para vincular
    los charts al dashboard con los IDs numéricos reales.
    """
    auth_headers = {"Authorization": headers["Authorization"]}
    write_headers = {
        **auth_headers,
        "X-CSRFToken": headers.get("X-CSRFToken", ""),
        "Referer": base,
    }

    # 0a. Obtener db_id de ETL_DWH para crear datasets directamente
    db_id: int | None = None
    resp = await client.get(
        f"{base}/api/v1/database/",
        headers=auth_headers,
        params={"q": "(page_size:100)"},
        timeout=10,
    )
    if resp.status_code == 200:
        for db in resp.json().get("result", []):
            if db.get("database_name") == DB_NAME:
                db_id = db.get("id")
                break

    # 0b. Crear tablas físicas del DWH antes de dataset/import/
    access_token = headers["Authorization"].removeprefix("Bearer ")
    csrf_token = headers.get("X-CSRFToken", "")
    await create_dwh_tables(client, base, access_token, csrf_token, {}, zip_bytes, real_table_status)

    # 0c. Crear datasets directamente con el UUID exacto del ZIP
    if db_id:
        await create_datasets_from_zip(client, base, auth_headers, write_headers, zip_bytes, db_id)
    else:
        logger.warning("No se encontró db_id de ETL_DWH — saltando creación directa de datasets")

    # 1. Datasets
    section_zip = _make_section_zip(zip_bytes, "datasets", "SqlaTable")

    resp = await client.post(
        f"{base}/api/v1/dataset/import/",
        headers=headers,
        files={"formData": ("export.zip", section_zip, "application/zip")},
        data={"overwrite": "true"},
        timeout=30,
    )
    logger.info(
        "/api/v1/dataset/import/ → %d: %s", resp.status_code, resp.text[:2000]
    )
    if resp.status_code not in (200, 201):
        raise SupersetError(
            f"Import datasets falló ({resp.status_code}): {resp.text[:400]}"
        )

    # 2. Obtener mapeo dataset_uuid → id numérico
    dataset_uuid_to_id: dict[str, int] = {}
    ds_resp = await client.get(
        f"{base}/api/v1/dataset/",
        headers=auth_headers,
        params={"q": "(page_size:200)"},
        timeout=15,
    )
    if ds_resp.status_code == 200:
        for ds in ds_resp.json().get("result", []):
            uid = ds.get("uuid", "")
            did = ds.get("id")
            if uid and did:
                dataset_uuid_to_id[uid] = did
    logger.info("Datasets disponibles en Superset: %d", len(dataset_uuid_to_id))

    write_headers_charts = {
        **auth_headers,
        "X-CSRFToken": headers["X-CSRFToken"],
        "Referer": base,
    }

    # 3. Crear charts directamente via POST /api/v1/chart/
    # (chart/import/ con overwrite=true no crea charts nuevos en esta versión de Superset)
    uuid_to_id = await create_charts_from_zip(
        client, base, auth_headers, write_headers_charts, zip_bytes, dataset_uuid_to_id
    )
    logger.info("Charts creados/actualizados: %s", uuid_to_id)

    # 4. Dashboard — reescribir chartId con IDs numéricos reales antes de importar
    section_zip = _make_section_zip(
        zip_bytes, "dashboards", "Dashboard", chart_uuid_to_id=uuid_to_id
    )
    resp = await client.post(
        f"{base}/api/v1/dashboard/import/",
        headers=headers,
        files={"formData": ("export.zip", section_zip, "application/zip")},
        data={"overwrite": "true"},
        timeout=30,
    )
    logger.info(
        "/api/v1/dashboard/import/ → %d: %s", resp.status_code, resp.text[:300]
    )
    if resp.status_code not in (200, 201):
        raise SupersetError(
            f"Import dashboard falló ({resp.status_code}): {resp.text[:400]}"
        )

    if not uuid_to_id:
        logger.warning(
            "No se pudieron resolver chart IDs — dashboard importado sin charts vinculados"
        )
        return

    # 5. Obtener ID numérico del dashboard
    dash_uuid = _extract_dashboard_uuid(zip_bytes)
    if not dash_uuid:
        logger.warning("No se encontró UUID del dashboard")
        return

    resp = await client.get(
        f"{base}/api/v1/dashboard/{dash_uuid}",
        headers=auth_headers,
        timeout=10,
    )
    if resp.status_code != 200:
        logger.warning(
            "No se pudo obtener el dashboard: %d %s",
            resp.status_code,
            resp.text[:200],
        )
        return
    dash_id = resp.json().get("result", {}).get("id")
    if not dash_id:
        logger.warning("Dashboard result sin id")
        return

    # 6. Vincular cada chart al dashboard vía PUT /api/v1/chart/{id}
    #    ChartDAO.update maneja explícitamente dashboards → actualiza dashboard_slices M2M
    write_headers = {
        **auth_headers,
        "X-CSRFToken": headers["X-CSRFToken"],
        "Referer": base,
        "Content-Type": "application/json",
    }
    linked = 0
    for chart_id in uuid_to_id.values():
        put = await client.put(
            f"{base}/api/v1/chart/{chart_id}",
            headers=write_headers,
            json={"dashboards": [dash_id]},
            timeout=10,
        )
        if put.status_code in (200, 201):
            linked += 1
        else:
            logger.warning(
                "Chart %s PUT → %d: %s", chart_id, put.status_code, put.text[:200]
            )

    logger.info(
        "Import step-by-step OK — %d/%d charts vinculados al dashboard %s",
        linked,
        len(uuid_to_id),
        dash_id,
    )


async def fix_dashboard_chart_ids(
    client: httpx.AsyncClient,
    base: str,
    headers: dict,
    zip_bytes: bytes,
) -> None:
    """
    assets/import/ crea datasets+charts+dashboard en un solo POST, pero NO
    reescribe el chartId numérico dentro del position_json del dashboard —
    el ZIP trae chartId:0 (ver supersetExport.js) y Superset no lo re-resuelve
    desde el uuid al importar. Resultado: cada celda del dashboard muestra
    "There is no chart definition associated with this component".

    Se resuelve uuid→id de los charts recién creados (ya existen en Superset,
    assets/import/ preserva los uuids del ZIP) y se reimporta SOLO la sección
    dashboards con overwrite=true y los chartId corregidos — mismo mecanismo
    que ya usa import_step_by_step (paso 4), aplicado también al camino feliz.
    """
    auth_headers = {"Authorization": headers["Authorization"]}
    uuid_to_id, _ = await list_all_charts(client, base, auth_headers)

    zip_chart_uuids: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            parts = name.split("/")
            if len(parts) >= 3 and parts[1] == "charts" and name.endswith(".yaml"):
                try:
                    data = yaml.safe_load(zf.read(name).decode("utf-8"))
                    cu = data.get("uuid", "")
                    if cu:
                        zip_chart_uuids.add(cu)
                except Exception as exc:
                    logger.warning("fix_dashboard_chart_ids: no se pudo leer '%s': %s", name, exc)

    chart_uuid_to_id = {u: uuid_to_id[u] for u in zip_chart_uuids if u in uuid_to_id}
    if not chart_uuid_to_id:
        logger.warning(
            "fix_dashboard_chart_ids: no se resolvió ningún chart id (%d en el ZIP, %d en Superset) "
            "— el dashboard queda con chartId:0",
            len(zip_chart_uuids), len(uuid_to_id),
        )
        return

    section_zip = _make_section_zip(zip_bytes, "dashboards", "Dashboard", chart_uuid_to_id=chart_uuid_to_id)
    resp = await client.post(
        f"{base}/api/v1/dashboard/import/",
        headers=headers,
        files={"formData": ("export.zip", section_zip, "application/zip")},
        data={"overwrite": "true"},
        timeout=30,
    )
    if resp.status_code in (200, 201):
        logger.info(
            "fix_dashboard_chart_ids: dashboard reimportado con %d/%d chartId reales",
            len(chart_uuid_to_id), len(zip_chart_uuids),
        )
    else:
        logger.warning(
            "fix_dashboard_chart_ids: no se pudo reimportar el dashboard (%d): %s",
            resp.status_code, resp.text[:300],
        )


async def resolve_dashboard_url(
    client: httpx.AsyncClient,
    base: str,
    access_token: str,
    zip_bytes: bytes,
) -> str:
    """Extrae el UUID del dashboard del ZIP y devuelve la URL directa, o el listado si falla."""
    dashboard_uuid = _extract_dashboard_uuid(zip_bytes)
    if not dashboard_uuid:
        logger.warning("No se encontró UUID del dashboard — redirigiendo al listado")
        return f"{base}/superset/dashboard/list/"

    resp = await client.get(
        f"{base}/api/v1/dashboard/{dashboard_uuid}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=10,
    )
    if resp.status_code == 200:
        dash_id = resp.json()["result"]["id"]
        return f"{base}/superset/dashboard/{dash_id}/"

    # Fallback: buscar por UUID en el listado
    resp = await client.get(
        f"{base}/api/v1/dashboard/",
        headers={"Authorization": f"Bearer {access_token}"},
        params={
            "q": f'(filters:!((col:uuid,opr:DashboardUUID,val:"{dashboard_uuid}")))'
        },
        timeout=10,
    )
    if resp.status_code == 200:
        results = resp.json().get("result", [])
        if results:
            return f"{base}/superset/dashboard/{results[0]['id']}/"

    return f"{base}/superset/dashboard/list/"
