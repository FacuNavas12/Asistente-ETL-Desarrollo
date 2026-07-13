"""
Cliente async para la API REST de Superset.

Flujo:
  1. POST /api/v1/security/login            → access_token + csrf_token
  2. GET  /api/v1/database/                 → busca ETL_DWH por nombre
  3. POST /api/v1/database/ (si no existe)  → crea conexión ETL_DWH
  4. _rewrite_db_uuid()                     → reemplaza database_uuid en dataset YAMLs
  5. POST /api/v1/assets/import/            → importa ZIP sin carpeta databases/
  6. GET  /api/v1/dashboard/{uuid}          → obtiene ID numérico
  7. Devuelve URL directa al dashboard

El UUID de la BD en el ZIP se alinea con el UUID real que tiene Superset,
evitando el error 1010 "Import failed for unknown reason" que ocurre cuando
los datasets referencian una database_uuid que no existe.
"""

from __future__ import annotations

import io
import json
import logging
import zipfile

import httpx
import yaml

logger = logging.getLogger(__name__)

# UUID fijo de referencia (frontend). Si Superset ya tiene ETL_DWH con otro UUID,
# se detecta y los dataset YAMLs se reescriben para usar el UUID real.
DB_UUID_FRONTEND = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
DB_NAME = "ETL_DWH"


class SupersetError(Exception):
    pass


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

    # ── Database — get or create ──────────────────────────────────────────────

    async def _get_or_create_database(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        csrf_token: str,
    ) -> str:
        """
        Devuelve el UUID de ETL_DWH en Superset.
        Si la BD no existe, la crea con una URI placeholder.
        El usuario debe configurar la URI real en Settings → Database Connections.
        """
        auth_headers = {"Authorization": f"Bearer {access_token}"}
        write_headers = {
            **auth_headers,
            "X-CSRFToken": csrf_token,
            "Referer": self._base,
            "Content-Type": "application/json",
        }

        # Listar todas las BDs y buscar ETL_DWH por nombre
        resp = await client.get(
            f"{self._base}/api/v1/database/",
            headers=auth_headers,
            params={"q": "(page_size:100)"},
            timeout=10,
        )
        if resp.status_code == 200:
            for db in resp.json().get("result", []):
                if db.get("database_name") == DB_NAME:
                    db_id = db.get("id")
                    # Intentar obtener el UUID del endpoint de detalle
                    detail = await client.get(
                        f"{self._base}/api/v1/database/{db_id}",
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

        # No existe → crear con URI placeholder
        logger.info("Creando ETL_DWH en Superset con URI placeholder")
        create = await client.post(
            f"{self._base}/api/v1/database/",
            headers=write_headers,
            json={
                "database_name": DB_NAME,
                "sqlalchemy_uri": "postgresql://user:password@localhost:5432/dwh",
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

    # ── Dataset creation ──────────────────────────────────────────────────────

    async def _create_datasets_from_zip(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        write_headers: dict,
        zip_bytes: bytes,
        db_id: int,
    ) -> None:
        """Crea datasets en Superset directamente desde los YAMLs del ZIP usando el UUID exacto."""
        STAGING_PREFIXES = ["stg_", "staging_", "tmp_", "temp_", "ods_", "raw_", "wrk_"]

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
                            f"{self._base}/api/v1/dataset/",
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
                        f"{self._base}/api/v1/dataset/",
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
                            f"{self._base}/api/v1/dataset/",
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
                                f"{self._base}/api/v1/dataset/{existing_id}",
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

    # ── Chart creation ────────────────────────────────────────────────────────

    async def _list_all_charts(
        self,
        client: httpx.AsyncClient,
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
                f"{self._base}/api/v1/chart/",
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

    async def _create_charts_from_zip(
        self,
        client: httpx.AsyncClient,
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

        existing_by_uuid, existing_by_name = await self._list_all_charts(client, auth_headers)

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
                            f"{self._base}/api/v1/chart/{existing_id}",
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
                        f"{self._base}/api/v1/chart/",
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
                        refreshed_by_uuid, refreshed_by_name = await self._list_all_charts(client, auth_headers)
                        retry_id = refreshed_by_uuid.get(chart_uuid) or refreshed_by_name.get(slice_name)
                        if retry_id:
                            put = await client.put(
                                f"{self._base}/api/v1/chart/{retry_id}",
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

    # ── Step-by-step import (diagnóstico) ────────────────────────────────────

    async def _import_step_by_step(
        self,
        client: httpx.AsyncClient,
        headers: dict,
        zip_bytes: bytes,
    ) -> None:
        """
        Importa datasets → charts → dashboard, luego hace PUT para vincular
        los charts al dashboard con los IDs numéricos reales.
        """
        auth_headers = {"Authorization": headers["Authorization"]}
        write_headers = {
            **auth_headers,
            "X-CSRFToken": headers.get("X-CSRFToken", ""),
            "Referer": self._base,
        }

        # 0a. Obtener db_id de ETL_DWH para crear datasets directamente
        db_id: int | None = None
        resp = await client.get(
            f"{self._base}/api/v1/database/",
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
        await self._create_dwh_tables(client, access_token, csrf_token, {}, zip_bytes)

        # 0c. Crear datasets directamente con el UUID exacto del ZIP
        if db_id:
            await self._create_datasets_from_zip(client, auth_headers, write_headers, zip_bytes, db_id)
        else:
            logger.warning("No se encontró db_id de ETL_DWH — saltando creación directa de datasets")

        # 1. Datasets
        section_zip = _make_section_zip(zip_bytes, "datasets", "SqlaTable")

        resp = await client.post(
            f"{self._base}/api/v1/dataset/import/",
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
            f"{self._base}/api/v1/dataset/",
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
            "Referer": self._base,
        }

        # 3. Crear charts directamente via POST /api/v1/chart/
        # (chart/import/ con overwrite=true no crea charts nuevos en esta versión de Superset)
        uuid_to_id = await self._create_charts_from_zip(
            client, auth_headers, write_headers_charts, zip_bytes, dataset_uuid_to_id
        )
        logger.info("Charts creados/actualizados: %s", uuid_to_id)

        # 4. Dashboard — reescribir chartId con IDs numéricos reales antes de importar
        section_zip = _make_section_zip(
            zip_bytes, "dashboards", "Dashboard", chart_uuid_to_id=uuid_to_id
        )
        resp = await client.post(
            f"{self._base}/api/v1/dashboard/import/",
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
            f"{self._base}/api/v1/dashboard/{dash_uuid}",
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
            "Referer": self._base,
            "Content-Type": "application/json",
        }
        linked = 0
        for chart_id in uuid_to_id.values():
            put = await client.put(
                f"{self._base}/api/v1/chart/{chart_id}",
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

    async def _resolve_chart_ids(
        self,
        client: httpx.AsyncClient,
        auth_headers: dict,
        zip_bytes: bytes,
    ) -> dict[str, int]:
        """
        Devuelve {chart_uuid: chart_id_numerico}.
        Busca cada chart del ZIP por slice_name exacto en el listing de Superset,
        paginando hasta encontrar todos o agotar los resultados.
        """
        # Leer slice_name → uuid desde el ZIP
        name_to_uuid: dict[str, str] = {}
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                parts = name.split("/")
                if len(parts) >= 3 and parts[1] == "charts" and name.endswith(".yaml"):
                    try:
                        data = yaml.safe_load(zf.read(name).decode("utf-8"))
                        slice_name = data.get("slice_name", "")
                        uid = data.get("uuid", "")
                        if slice_name and uid:
                            name_to_uuid[slice_name] = uid
                    except Exception:
                        pass

        if not name_to_uuid:
            return {}

        logger.info(
            "Charts en ZIP (%d): %s", len(name_to_uuid), list(name_to_uuid.keys())
        )

        # Buscar por slice_name exacto en el listing — paginar hasta encontrar todos
        # o agotar resultados. Tomamos el ID más alto (= importación más reciente).
        name_to_best: dict[
            str, tuple[int, str]
        ] = {}  # slice_name → (chart_id, uuid_en_superset)
        page = 0
        page_size = 100
        total_fetched = 0
        pending = set(name_to_uuid.keys())  # nombres que aún no encontramos

        while pending:
            resp = await client.get(
                f"{self._base}/api/v1/chart/",
                headers=auth_headers,
                params={"q": f"(page_size:{page_size},page:{page})"},
                timeout=15,
            )
            if resp.status_code != 200:
                logger.warning(
                    "No se pudo listar charts (página %d): %d", page, resp.status_code
                )
                break

            data = resp.json()
            results = data.get("result", [])
            if not results:
                break

            total_fetched += len(results)
            logger.info(
                "Página %d: %d charts (total fetched: %d)",
                page,
                len(results),
                total_fetched,
            )

            for chart in results:
                chart_id = chart.get("id")
                slice_name = chart.get("slice_name", "")
                uuid_in_superset = str(chart.get("uuid") or "")

                if slice_name in pending:
                    prev_id = name_to_best.get(slice_name, (0, ""))[0]
                    if chart_id > prev_id:
                        name_to_best[slice_name] = (chart_id, uuid_in_superset)
                        logger.info(
                            "Chart encontrado: '%s' → id=%s uuid_superset=%s",
                            slice_name,
                            chart_id,
                            uuid_in_superset,
                        )

            # Si encontramos todos los charts, podemos parar
            found = set(name_to_best.keys())
            pending = set(name_to_uuid.keys()) - found

            count = data.get("count", 0)
            if total_fetched >= count:
                break  # No hay más páginas

            page += 1

        # Construir resultado: usar el UUID del ZIP (no el de Superset) como clave
        # porque el dashboard position_json usa los UUIDs del ZIP
        uuid_to_id: dict[str, int] = {}
        for slice_name, (chart_id, _) in name_to_best.items():
            zip_uuid = name_to_uuid[slice_name]
            uuid_to_id[zip_uuid] = chart_id
            logger.info(
                "Chart resuelto: '%s' → zip_uuid=%s id=%s",
                slice_name,
                zip_uuid,
                chart_id,
            )

        if pending:
            logger.warning("Charts no encontrados en Superset: %s", list(pending))

        logger.info("Charts resueltos: %d/%d", len(uuid_to_id), len(name_to_uuid))
        return uuid_to_id

    # ── Import ────────────────────────────────────────────────────────────────

    async def _create_dwh_tables(
        self,
        client: httpx.AsyncClient,
        access_token: str,
        csrf_token: str,
        dwh_sample: dict,
        zip_bytes: bytes,
    ) -> None:
        """
        Crea las tablas del DWH en la BD ETL_DWH de Superset usando SQL Lab API.
        Lee columnas desde los datasets YAML del ZIP (fuente primaria) y usa
        dwh_sample como fallback cuando el ZIP no tiene datos útiles.
        """
        auth_headers = {
            "Authorization": f"Bearer {access_token}",
            "X-CSRFToken": csrf_token,
            "Referer": self._base,
            "Content-Type": "application/json",
        }

        resp = await client.get(
            f"{self._base}/api/v1/database/",
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

        STAGING_PREFIXES = ["stg_", "staging_", "tmp_", "temp_", "ods_", "raw_", "wrk_"]

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
                f"{self._base}/api/v1/sqllab/execute/",
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

    async def import_dashboard(self, zip_bytes: bytes, dwh_sample: dict | None = None) -> str:
        """
        Importa el ZIP a Superset y devuelve la URL directa al dashboard.
        Alinea el database_uuid de los datasets con el UUID real de ETL_DWH.
        """
        async with httpx.AsyncClient() as client:
            access_token, csrf_token = await self._auth(client)

            # Obtener UUID real de ETL_DWH en Superset
            actual_db_uuid = await self._get_or_create_database(
                client, access_token, csrf_token
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
            await self._create_dwh_tables(client, access_token, csrf_token, dwh_sample or {}, clean_zip)

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
                await self._import_step_by_step(client, headers, clean_zip)
            logger.info("Superset import OK")

            # Extraer UUID del dashboard para construir la URL
            dashboard_uuid = _extract_dashboard_uuid(zip_bytes)
            if not dashboard_uuid:
                logger.warning(
                    "No se encontró UUID del dashboard — redirigiendo al listado"
                )
                return f"{self._base}/superset/dashboard/list/"

            resp = await client.get(
                f"{self._base}/api/v1/dashboard/{dashboard_uuid}",
                headers={"Authorization": f"Bearer {access_token}"},
                timeout=10,
            )
            if resp.status_code == 200:
                dash_id = resp.json()["result"]["id"]
                return f"{self._base}/superset/dashboard/{dash_id}/"

            # Fallback: buscar por UUID en el listado
            resp = await client.get(
                f"{self._base}/api/v1/dashboard/",
                headers={"Authorization": f"Bearer {access_token}"},
                params={
                    "q": f'(filters:!((col:uuid,opr:DashboardUUID,val:"{dashboard_uuid}")))'
                },
                timeout=10,
            )
            if resp.status_code == 200:
                results = resp.json().get("result", [])
                if results:
                    return f"{self._base}/superset/dashboard/{results[0]['id']}/"

            return f"{self._base}/superset/dashboard/list/"


# ── ZIP helpers ───────────────────────────────────────────────────────────────

_ALLOWED_SECTIONS = {"datasets", "charts", "dashboards"}


def _strip_and_rewrite_zip(zip_bytes: bytes, actual_db_uuid: str) -> bytes:
    """
    Devuelve un ZIP con solo los archivos que Superset espera:
      - <root>/metadata.yaml
      - <root>/datasets/**/*.yaml
      - <root>/charts/**/*.yaml
      - <root>/dashboards/**/*.yaml
    Excluye databases/, README.md y cualquier archivo no estándar.
    Reescribe database_uuid en los dataset YAMLs.
    """
    input_buf = io.BytesIO(zip_bytes)
    output_buf = io.BytesIO()

    with (
        zipfile.ZipFile(input_buf, "r") as zin,
        zipfile.ZipFile(output_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout,
    ):
        for item in zin.infolist():
            filename = item.filename
            parts = filename.split("/")

            # Entradas de directorio — omitir
            if filename.endswith("/"):
                continue

            # Permitir solo metadata.yaml y secciones estándar
            if len(parts) == 2 and parts[1] == "metadata.yaml":
                zout.writestr(item, zin.read(filename))
                continue

            if (
                len(parts) >= 3
                and parts[1] in _ALLOWED_SECTIONS
                and filename.endswith(".yaml")
            ):
                content = zin.read(filename)
                if parts[1] == "datasets":
                    content = _rewrite_db_uuid_in_yaml(content, actual_db_uuid)
                zout.writestr(item, content)
                continue

            logger.debug("Excluyendo del ZIP: %s", filename)

    return output_buf.getvalue()


def _rewrite_db_uuid_in_yaml(content: bytes, new_uuid: str) -> bytes:
    """Reemplaza el campo database_uuid en un dataset YAML."""
    try:
        data = yaml.safe_load(content.decode("utf-8"))
        if isinstance(data, dict) and "database_uuid" in data:
            old_uuid = data["database_uuid"]
            data["database_uuid"] = new_uuid
            if old_uuid != new_uuid:
                logger.info("Reescribiendo database_uuid: %s → %s", old_uuid, new_uuid)
            return yaml.dump(data, allow_unicode=True, sort_keys=False).encode("utf-8")
    except Exception as exc:
        logger.warning("No se pudo reescribir database_uuid: %s", exc)
    return content


def _log_zip_contents(zip_bytes: bytes) -> None:
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            files = zf.namelist()
            logger.info("ZIP a importar (%d archivos): %s", len(files), files)
            # Volcar contenido de los primeros YAMLs para diagnóstico
            for name in files:
                if name.endswith(".yaml"):
                    content = zf.read(name).decode("utf-8")
                    logger.info("=== %s ===\n%s", name, content[:4000])
    except Exception as exc:
        logger.warning("No se pudo listar el ZIP: %s", exc)


def _rewrite_dashboard_chart_ids(content: bytes, uuid_to_id: dict[str, int]) -> bytes:
    """
    Reescribe chartId en el YAML del dashboard usando los IDs numéricos reales de Superset.
    El frontend genera chartId: 0 — sin el ID real Superset no puede vincular el chart.
    """
    try:
        data = yaml.safe_load(content.decode("utf-8"))
        position = data.get("position", {})
        for key, node in position.items():
            if not isinstance(node, dict):
                continue
            meta = node.get("meta", {})
            if not isinstance(meta, dict):
                continue
            chart_uuid = meta.get("uuid", "")
            if chart_uuid and chart_uuid in uuid_to_id:
                meta["chartId"] = uuid_to_id[chart_uuid]
        return yaml.dump(data, allow_unicode=True, sort_keys=False).encode("utf-8")
    except Exception as exc:
        logger.warning("No se pudo reescribir chartIds del dashboard: %s", exc)
    return content


def _convert_chart_params_to_dict(content: bytes) -> bytes:
    """
    chart/import/ valida params como YAML mapping, no como JSON string.
    Convierte params de string JSON → dict para que yaml.dump lo serialice como mapping.
    """
    try:
        data = yaml.safe_load(content.decode("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("params"), str):
            data["params"] = json.loads(data["params"])
            return yaml.dump(data, allow_unicode=True, sort_keys=False).encode("utf-8")
    except Exception as exc:
        logger.warning("No se pudo convertir params a dict: %s", exc)
    return content


def _make_section_zip(
    zip_bytes: bytes,
    section: str,
    meta_type: str,
    chart_uuid_to_id: dict[str, int] | None = None,
) -> bytes:
    """
    ZIP con metadata.yaml (type reescrito a meta_type) + YAMLs de la sección indicada.
    Cada endpoint individual valida que metadata.yaml.type coincida con su tipo.
    chart_uuid_to_id: si se provee, reescribe chartId en el dashboard YAML.
    """
    input_buf = io.BytesIO(zip_bytes)
    output_buf = io.BytesIO()

    # Detectar root folder del ZIP (ej: "etl_Nueva_Transformacion_export")
    root = ""
    with zipfile.ZipFile(input_buf, "r") as zf:
        for name in zf.namelist():
            parts = name.split("/")
            if len(parts) >= 2:
                root = parts[0]
                break
    input_buf.seek(0)

    # metadata.yaml con type correcto para este endpoint
    # Superset valida que timestamp sea un datetime válido ISO-8601
    from datetime import datetime, timezone as _tz

    ts = datetime.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    meta_content = yaml.dump(
        {"version": "1.0.0", "type": meta_type, "timestamp": ts},
        allow_unicode=True,
    ).encode("utf-8")
    meta_path = f"{root}/metadata.yaml" if root else "metadata.yaml"

    with (
        zipfile.ZipFile(input_buf, "r") as zin,
        zipfile.ZipFile(output_buf, "w", compression=zipfile.ZIP_DEFLATED) as zout,
    ):
        # Escribir metadata con type correcto
        zout.writestr(meta_path, meta_content)
        # Escribir solo los YAMLs de la sección
        for item in zin.infolist():
            filename = item.filename
            if filename.endswith("/"):
                continue
            parts = filename.split("/")
            if filename == meta_path or (
                len(parts) >= 2 and parts[-1] == "metadata.yaml"
            ):
                continue  # ya fue escrito arriba
            if len(parts) >= 3 and parts[1] == section and filename.endswith(".yaml"):
                content = zin.read(filename)
                if section == "charts":
                    content = _convert_chart_params_to_dict(content)
                elif section == "dashboards" and chart_uuid_to_id:
                    content = _rewrite_dashboard_chart_ids(content, chart_uuid_to_id)
                zout.writestr(item, content)
            elif section == "charts" and len(parts) >= 3 and parts[1] == "datasets" and filename.endswith(".yaml"):
                # chart/import/ necesita los datasets en el ZIP para establecer la relación
                zout.writestr(item, zin.read(filename))

    return output_buf.getvalue()


def _extract_dashboard_uuid(zip_bytes: bytes) -> str:
    """Lee el primer archivo dashboards/*.yaml del ZIP y devuelve su UUID."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                parts = name.split("/")
                is_dashboard = (len(parts) == 2 and parts[0] == "dashboards") or (
                    len(parts) == 3 and parts[1] == "dashboards"
                )
                if is_dashboard and name.endswith(".yaml"):
                    data = yaml.safe_load(zf.read(name).decode("utf-8"))
                    uid = data.get("uuid", "")
                    if uid:
                        return uid
    except Exception as exc:
        logger.warning("No se pudo leer UUID del ZIP: %s", exc)
    return ""
