"""Crea datasets en Superset directamente desde los YAMLs de datasets/ del ZIP,
usando el UUID exacto de cada uno para que overwrite=true los reconozca."""

from __future__ import annotations

import io
import logging
import zipfile

import httpx
import yaml

from app.services.superset_client.constants import STAGING_PREFIXES

logger = logging.getLogger(__name__)


async def create_datasets_from_zip(
    client: httpx.AsyncClient,
    base: str,
    auth_headers: dict,
    write_headers: dict,
    zip_bytes: bytes,
    db_id: int,
) -> None:
    """Crea datasets en Superset directamente desde los YAMLs del ZIP usando el UUID exacto."""

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for name in zf.namelist():
            parts = name.split("/")
            if not (len(parts) >= 3 and parts[1] == "datasets" and name.endswith(".yaml")):
                continue
            try:
                data = yaml.safe_load(zf.read(name).decode("utf-8"))
                table_name = data.get("table_name", "")
                dataset_uuid = data.get("uuid", "")
                if not table_name or not dataset_uuid:
                    continue
                if any(table_name.lower().startswith(p) for p in STAGING_PREFIXES):
                    continue

                # Verificar si ya existe con ese UUID exacto.
                # El operador DatasetUUID puede no existir en Superset 6.x —
                # si falla, intentamos crear igualmente.
                already_exists = False
                try:
                    check = await client.get(
                        f"{base}/api/v1/dataset/",
                        headers=auth_headers,
                        params={"q": f'(filters:!((col:uuid,opr:DatasetUUID,val:"{dataset_uuid}")))'},
                        timeout=10,
                    )
                    if check.status_code == 200 and check.json().get("count", 0) > 0:
                        logger.info("Dataset '%s' ya existe con UUID %s", table_name, dataset_uuid)
                        already_exists = True
                except Exception:
                    pass

                if already_exists:
                    continue

                # Crear dataset con UUID exacto del ZIP
                create_resp = await client.post(
                    f"{base}/api/v1/dataset/",
                    headers={**write_headers, "Content-Type": "application/json"},
                    json={
                        "database": db_id,
                        "schema": "public",
                        "table_name": table_name,
                        "uuid": dataset_uuid,
                    },
                    timeout=15,
                )
                if create_resp.status_code in (200, 201):
                    logger.info("Dataset '%s' creado con UUID %s", table_name, dataset_uuid)
                elif create_resp.status_code == 422:
                    # Ya existe — buscar por table_name y corregir UUID si no coincide
                    logger.info("Dataset '%s' ya existe (422) — buscando id para corregir UUID", table_name)
                    existing_id = None
                    search = await client.get(
                        f"{base}/api/v1/dataset/",
                        headers=auth_headers,
                        params={"q": "(page_size:200)"},
                        timeout=15,
                    )
                    if search.status_code == 200:
                        for ds in search.json().get("result", []):
                            if ds.get("table_name") == table_name and ds.get("uuid") != dataset_uuid:
                                existing_id = ds.get("id")
                                break
                    if existing_id:
                        put = await client.put(
                            f"{base}/api/v1/dataset/{existing_id}",
                            headers={**write_headers, "Content-Type": "application/json"},
                            json={"uuid": dataset_uuid},
                            timeout=10,
                        )
                        if put.status_code in (200, 201):
                            logger.info("Dataset '%s' UUID actualizado a %s", table_name, dataset_uuid)
                        else:
                            logger.warning(
                                "No se pudo actualizar UUID de '%s' (%d): %s",
                                table_name, put.status_code, put.text[:200],
                            )
                    else:
                        logger.info("Dataset '%s' ya tiene el UUID correcto o no se encontró", table_name)
                else:
                    logger.warning(
                        "No se pudo crear dataset '%s' (%d): %s",
                        table_name, create_resp.status_code, create_resp.text[:300],
                    )
            except Exception as exc:
                logger.warning("Error procesando dataset YAML '%s': %s", name, exc)
