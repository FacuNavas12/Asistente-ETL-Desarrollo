"""SupersetClient: login + orquestador principal del import de un dashboard —
alinea ETL_DWH, limpia/reescribe el ZIP, siembra tablas, importa y arma la URL final."""

from __future__ import annotations

import logging

import httpx

from app.services.superset_client.database import get_or_create_database
from app.services.superset_client.dashboard import (
    fix_dashboard_chart_ids,
    import_step_by_step,
    resolve_dashboard_url,
)
from app.services.superset_client.dwh_tables import create_dwh_tables
from app.services.superset_client.errors import SupersetError
from app.services.superset_client.zip_tools import _log_zip_contents, _strip_and_rewrite_zip

logger = logging.getLogger(__name__)


class SupersetClient:
    def __init__(self, base_url: str, username: str, password: str) -> None:
        self._base = base_url.rstrip("/")
        self._username = username
        self._password = password

    # ── Auth ──────────────────────────────────────────────────────────────────

    async def _auth(self, client: httpx.AsyncClient) -> tuple[str, str]:
        """Devuelve (access_token, csrf_token)."""
        resp = await client.post(
            f"{self._base}/api/v1/security/login",
            json={
                "username": self._username,
                "password": self._password,
                "provider": "db",
                "refresh": True,
            },
            timeout=15,
        )
        if resp.status_code != 200:
            raise SupersetError(
                f"Login fallido ({resp.status_code}): {resp.text[:200]}"
            )
        access_token: str = resp.json()["access_token"]

        resp = await client.get(
            f"{self._base}/api/v1/security/csrf_token/",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        if resp.status_code != 200:
            raise SupersetError(
                f"CSRF token fallido ({resp.status_code}): {resp.text[:200]}"
            )
        csrf_token: str = resp.json()["result"]
        return access_token, csrf_token

    # ── Import ────────────────────────────────────────────────────────────────

    async def import_dashboard(
        self,
        zip_bytes: bytes,
        dwh_sample: dict | None = None,
        real_table_status: dict[str, dict] | None = None,
        real_uri: str | None = None,
    ) -> str:
        """
        Importa el ZIP a Superset y devuelve la URL directa al dashboard.
        Alinea el database_uuid de los datasets con el UUID real de ETL_DWH.

        real_table_status (opcional): estado real (existe + rowCount) de las
        tablas DWH, resuelto por el caller contra conn_dwh — ver
        dwh_tables.create_dwh_tables para el write-gate que evita pisar datos reales.
        real_uri (opcional): sqlalchemy_uri real de conn_dwh — si se provee,
        alinea/crea ETL_DWH en Superset con esa URI en vez del placeholder.
        """
        async with httpx.AsyncClient() as client:
            access_token, csrf_token = await self._auth(client)

            # Obtener/alinear UUID real de ETL_DWH en Superset
            actual_db_uuid = await get_or_create_database(
                client, self._base, access_token, csrf_token, real_uri
            )

            headers = {
                "Authorization": f"Bearer {access_token}",
                "X-CSRFToken": csrf_token,
                "Referer": self._base,
            }

            # Construir ZIP sin databases/ y con database_uuid corregido
            clean_zip = _strip_and_rewrite_zip(zip_bytes, actual_db_uuid)
            _log_zip_contents(clean_zip)

            # Crear tablas del DWH en Superset antes de importar el ZIP
            await create_dwh_tables(
                client, self._base, access_token, csrf_token, dwh_sample or {}, clean_zip, real_table_status
            )

            # Intentar primero con el endpoint unificado
            resp = await client.post(
                f"{self._base}/api/v1/assets/import/",
                headers=headers,
                files={"bundle": ("export.zip", clean_zip, "application/zip")},
                data={"overwrite": "true"},
                timeout=60,
            )
            if resp.status_code not in (200, 201):
                logger.error(
                    "assets/import/ falló (%d): %s", resp.status_code, resp.text[:500]
                )
                # Fallback: importar tipo a tipo para aislar el error
                await import_step_by_step(client, self._base, headers, clean_zip, real_table_status)
            else:
                # assets/import/ no reescribe el chartId numérico del dashboard —
                # ver dashboard.fix_dashboard_chart_ids para el porqué.
                await fix_dashboard_chart_ids(client, self._base, headers, clean_zip)
            logger.info("Superset import OK")

            # Extraer UUID del dashboard para construir la URL
            return await resolve_dashboard_url(client, self._base, access_token, zip_bytes)
