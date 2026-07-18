"""Helpers de bajo nivel para manipular el ZIP de export de Superset (formato
assets/import/): filtrar secciones, reescribir UUIDs/chartIds, armar sub-ZIPs por tipo."""

from __future__ import annotations

import io
import json
import logging
import zipfile

import yaml

logger = logging.getLogger(__name__)

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
