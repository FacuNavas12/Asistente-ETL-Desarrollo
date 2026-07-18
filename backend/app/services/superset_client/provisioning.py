"""Variante síncrona de login + get-or-create de la conexión ETL_DWH en Superset,
usada por etl_generator para alinear la URI real apenas se conoce conn_dwh."""

import json
import logging

import httpx

from app.services.superset_client.constants import DB_NAME, DB_UUID_FRONTEND

logger = logging.getLogger(__name__)


def provision_database_sync(base_url: str, username: str, password: str, real_uri: str) -> None:
    """
    Variante SÍNCRONA de client._auth + database.get_or_create_database (con real_uri), para
    alinear la conexión ETL_DWH en Superset apenas se conoce conn_dwh.
    etl_generator._try_build es sync y puede correr en threadpool (handler
    sync) o dentro de un loop ya corriendo (generate_etl_async) — programar
    un asyncio.create_task cross-thread ahí es frágil; duplicar el mismo
    login→get-or-create-or-update en httpx.Client (sync) es más simple y
    confiable. Best-effort: nunca lanza, todo error queda en logger.warning.
    """
    base = base_url.rstrip("/")
    try:
        with httpx.Client(timeout=15) as client:
            resp = client.post(
                f"{base}/api/v1/security/login",
                json={"username": username, "password": password, "provider": "db", "refresh": True},
            )
            if resp.status_code != 200:
                logger.warning("provision_database_sync: login falló (%d)", resp.status_code)
                return
            access_token = resp.json()["access_token"]

            resp = client.get(
                f"{base}/api/v1/security/csrf_token/",
                headers={"Authorization": f"Bearer {access_token}"},
            )
            if resp.status_code != 200:
                logger.warning("provision_database_sync: csrf token falló (%d)", resp.status_code)
                return
            csrf_token = resp.json()["result"]

            auth_headers = {"Authorization": f"Bearer {access_token}"}
            write_headers = {
                **auth_headers, "X-CSRFToken": csrf_token,
                "Referer": base, "Content-Type": "application/json",
            }

            resp = client.get(
                f"{base}/api/v1/database/", headers=auth_headers, params={"q": "(page_size:100)"},
            )
            db_id = None
            if resp.status_code == 200:
                for db in resp.json().get("result", []):
                    if db.get("database_name") == DB_NAME:
                        db_id = db.get("id")
                        break

            if db_id:
                update = client.put(
                    f"{base}/api/v1/database/{db_id}", headers=write_headers,
                    json={"sqlalchemy_uri": real_uri},
                )
                if update.status_code in (200, 201):
                    logger.info("provision_database_sync: ETL_DWH (id=%s) alineada con conn_dwh", db_id)
                else:
                    logger.warning(
                        "provision_database_sync: no se pudo actualizar la URI (%d): %s",
                        update.status_code, update.text[:200],
                    )
            else:
                create = client.post(
                    f"{base}/api/v1/database/",
                    headers=write_headers,
                    json={
                        "database_name": DB_NAME,
                        "sqlalchemy_uri": real_uri,
                        "expose_in_sqllab": True,
                        "allow_run_async": False,
                        "allow_ctas": False,
                        "allow_cvas": False,
                        "allow_dml": False,
                        "allow_file_upload": False,
                        "extra": json.dumps({
                            "allows_virtual_table_explore": True,
                            "schemas_allowed_for_csv_upload": [],
                            "engine_params": {},
                            "metadata_params": {},
                        }),
                        "uuid": DB_UUID_FRONTEND,
                    },
                )
                if create.status_code in (200, 201):
                    logger.info("provision_database_sync: ETL_DWH creada con la URI real de conn_dwh")
                else:
                    logger.warning(
                        "provision_database_sync: no se pudo crear ETL_DWH (%d): %s",
                        create.status_code, create.text[:200],
                    )
    except Exception as exc:
        logger.warning("provision_database_sync: fallo inesperado — %s", exc)
