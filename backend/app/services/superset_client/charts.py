"""Lista y crea/actualiza charts en Superset directamente vía POST/PUT /api/v1/chart/
desde los YAMLs de charts/ del ZIP — chart/import/ no crea charts nuevos, solo los actualiza."""

from __future__ import annotations

import io
import json
import logging
import zipfile

import httpx
import yaml

logger = logging.getLogger(__name__)


async def list_all_charts(
    client: httpx.AsyncClient,
    base: str,
    auth_headers: dict,
) -> tuple[dict[str, int], dict[str, int]]:
    """
    Devuelve (uuid_to_id, slice_name_to_id) de TODOS los charts existentes.
    Pagina sin filtro de columna — evita operadores como 'ChartAllTextSearch'
    que Superset rechaza con 400 (no es un operador válido de la REST API).
    """
    uuid_to_id: dict[str, int] = {}
    slice_name_to_id: dict[str, int] = {}
    page = 0
    page_size = 100
    while True:
        resp = await client.get(
            f"{base}/api/v1/chart/",
            headers=auth_headers,
            params={"q": f"(page_size:{page_size},page:{page})"},
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning("No se pudo listar charts (página %d): %d", page, resp.status_code)
            break
        results = resp.json().get("result", [])
        if not results:
            break
        for c in results:
            cid = c.get("id")
            cuuid = str(c.get("uuid") or "")
            cname = c.get("slice_name", "")
            if cuuid and cid:
                uuid_to_id[cuuid] = cid
            if cname and cid:
                slice_name_to_id[cname] = cid
        if len(results) < page_size:
            break
        page += 1
    return uuid_to_id, slice_name_to_id


async def create_charts_from_zip(
    client: httpx.AsyncClient,
    base: str,
    auth_headers: dict,
    write_headers: dict,
    zip_bytes: bytes,
    dataset_uuid_to_id: dict[str, int],
) -> dict[str, int]:
    """
    Crea o actualiza charts directamente via POST/PUT /api/v1/chart/.
    Devuelve {chart_uuid: chart_id_numerico} para uso en el dashboard.

    chart/import/ con overwrite=true solo actualiza charts existentes por UUID
    pero NO crea charts nuevos — por eso se usa POST /api/v1/chart/ directo.
    La detección de "ya existe?" se hace matcheando en Python contra un
    listado completo (no con un filtro server-side, que requeriría un
    operador registrado en Superset).
    """
    uuid_to_id: dict[str, int] = {}

    existing_by_uuid, existing_by_name = await list_all_charts(client, base, auth_headers)

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            parts = name.split("/")
            if not (len(parts) >= 3 and parts[1] == "charts" and name.endswith(".yaml")):
                continue
            try:
                data = yaml.safe_load(zf.read(name).decode("utf-8"))
                slice_name = data.get("slice_name", "")
                chart_uuid = data.get("uuid", "")
                viz_type = data.get("viz_type", "table")
                dataset_uuid = data.get("dataset_uuid", "")
                params = data.get("params", {})

                if not slice_name or not dataset_uuid:
                    continue

                datasource_id = dataset_uuid_to_id.get(dataset_uuid)
                if not datasource_id:
                    logger.warning(
                        "No se encontro datasource_id para dataset_uuid=%s (chart '%s')",
                        dataset_uuid, slice_name,
                    )
                    continue

                params_str = json.dumps(params) if isinstance(params, dict) else (params or "{}")

                existing_id = existing_by_uuid.get(chart_uuid) or existing_by_name.get(slice_name)

                if existing_id:
                    put = await client.put(
                        f"{base}/api/v1/chart/{existing_id}",
                        headers={**write_headers, "Content-Type": "application/json"},
                        json={
                            "slice_name": slice_name,
                            "viz_type": viz_type,
                            "datasource_id": datasource_id,
                            "datasource_type": "table",
                            "params": params_str,
                        },
                        timeout=15,
                    )
                    if put.status_code in (200, 201):
                        uuid_to_id[chart_uuid] = existing_id
                        logger.info("Chart '%s' actualizado (id=%s)", slice_name, existing_id)
                    else:
                        logger.warning(
                            "No se pudo actualizar chart '%s' (%d): %s",
                            slice_name, put.status_code, put.text[:200],
                        )
                    continue

                create = await client.post(
                    f"{base}/api/v1/chart/",
                    headers={**write_headers, "Content-Type": "application/json"},
                    json={
                        "slice_name": slice_name,
                        "viz_type": viz_type,
                        "datasource_id": datasource_id,
                        "datasource_type": "table",
                        "params": params_str,
                        "uuid": chart_uuid,
                    },
                    timeout=15,
                )
                if create.status_code in (200, 201):
                    new_id = create.json().get("id")
                    if new_id:
                        uuid_to_id[chart_uuid] = new_id
                        logger.info("Chart '%s' creado (id=%s)", slice_name, new_id)
                elif create.status_code == 422:
                    # Probablemente ya existía pero no estaba en el listado inicial.
                    # Reintentamos con un refetch antes de rendirnos.
                    logger.info("Chart '%s' -> 422 al crear, reintentando lookup", slice_name)
                    refreshed_by_uuid, refreshed_by_name = await list_all_charts(client, base, auth_headers)
                    retry_id = refreshed_by_uuid.get(chart_uuid) or refreshed_by_name.get(slice_name)
                    if retry_id:
                        put = await client.put(
                            f"{base}/api/v1/chart/{retry_id}",
                            headers={**write_headers, "Content-Type": "application/json"},
                            json={
                                "slice_name": slice_name,
                                "viz_type": viz_type,
                                "datasource_id": datasource_id,
                                "datasource_type": "table",
                                "params": params_str,
                            },
                            timeout=15,
                        )
                        if put.status_code in (200, 201):
                            uuid_to_id[chart_uuid] = retry_id
                            logger.info("Chart '%s' actualizado tras 422 (id=%s)", slice_name, retry_id)
                        else:
                            logger.warning(
                                "No se pudo actualizar chart '%s' tras 422 (%d): %s",
                                slice_name, put.status_code, put.text[:200],
                            )
                    else:
                        logger.warning(
                            "No se pudo crear chart '%s' (422) y no se encontro para actualizar: %s",
                            slice_name, create.text[:300],
                        )
                else:
                    logger.warning(
                        "No se pudo crear chart '%s' (%d): %s",
                        slice_name, create.status_code, create.text[:200],
                    )

            except Exception as exc:
                logger.warning("Error procesando chart YAML '%s': %s", name, exc)

    return uuid_to_id
