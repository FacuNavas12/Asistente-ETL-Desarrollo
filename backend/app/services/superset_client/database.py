"""Get-or-create asíncrono de la conexión ETL_DWH en Superset — busca por nombre,
alinea la URI real si se conoce, o la crea con URI placeholder si aún no existe."""

from __future__ import annotations

import json
import logging

import httpx

from app.services.superset_client.constants import DB_NAME, DB_UUID_FRONTEND

logger = logging.getLogger(__name__)


async def get_or_create_database(
    client: httpx.AsyncClient,
    base: str,
    access_token: str,
    csrf_token: str,
    real_uri: str | None = None,
) -> str:
    """
    Devuelve el UUID de ETL_DWH en Superset.

    Si la BD no existe, la crea — con real_uri si está resuelto (conn_dwh
    ya configurado por el usuario), o con una URI placeholder si no (el
    usuario debe configurarla a mano en Settings → Database Connections).
    Si ya existe y real_uri está disponible, actualiza la URI para que
    quede alineada — idempotente, PUT del mismo valor no hace daño.
    """
    auth_headers = {"Authorization": f"Bearer {access_token}"}
    write_headers = {
        **auth_headers,
        "X-CSRFToken": csrf_token,
        "Referer": base,
        "Content-Type": "application/json",
    }

    # Listar todas las BDs y buscar ETL_DWH por nombre
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

                if real_uri:
                    update = await client.put(
                        f"{base}/api/v1/database/{db_id}",
                        headers=write_headers,
                        json={"sqlalchemy_uri": real_uri},
                        timeout=15,
                    )
                    if update.status_code in (200, 201):
                        logger.info("ETL_DWH (id=%s): URI actualizada a la conexión real", db_id)
                    else:
                        logger.warning(
                            "ETL_DWH (id=%s): no se pudo actualizar la URI (%d): %s",
                            db_id, update.status_code, update.text[:200],
                        )

                # Intentar obtener el UUID del endpoint de detalle
                detail = await client.get(
                    f"{base}/api/v1/database/{db_id}",
                    headers=auth_headers,
                    timeout=10,
                )
                if detail.status_code == 200:
                    uuid_val = detail.json().get("result", {}).get("uuid", "")
                    if uuid_val:
                        logger.info(
                            "ETL_DWH existe en Superset (id=%s, uuid=%s)",
                            db_id,
                            uuid_val,
                        )
                        return uuid_val
                # Si no hay uuid en detalle, devolver el del listado
                uuid_val = db.get("uuid", "")
                if uuid_val:
                    logger.info(
                        "ETL_DWH existe en Superset (uuid del listado: %s)",
                        uuid_val,
                    )
                    return uuid_val
                logger.warning(
                    "ETL_DWH existe pero sin UUID expuesto — usando UUID frontend"
                )
                return DB_UUID_FRONTEND

    # No existe → crear con la URI real si está disponible, si no, placeholder
    logger.info(
        "Creando ETL_DWH en Superset con %s",
        "la URI real de conn_dwh" if real_uri else "URI placeholder",
    )
    create = await client.post(
        f"{base}/api/v1/database/",
        headers=write_headers,
        json={
            "database_name": DB_NAME,
            "sqlalchemy_uri": real_uri or "postgresql://user:password@localhost:5432/dwh",
            "expose_in_sqllab": True,
            "allow_run_async": False,
            "allow_ctas": False,
            "allow_cvas": False,
            "allow_dml": False,
            "allow_file_upload": False,
            "extra": json.dumps(
                {
                    "allows_virtual_table_explore": True,
                    "schemas_allowed_for_csv_upload": [],
                    "engine_params": {},
                    "metadata_params": {},
                }
            ),
            "uuid": DB_UUID_FRONTEND,
        },
        timeout=15,
    )
    if create.status_code in (200, 201):
        created_uuid = create.json().get("result", {}).get("uuid", DB_UUID_FRONTEND)
        logger.info("ETL_DWH creada (uuid=%s)", created_uuid)
        return created_uuid or DB_UUID_FRONTEND

    logger.warning(
        "No se pudo crear ETL_DWH (%d): %s", create.status_code, create.text[:300]
    )
    return DB_UUID_FRONTEND
