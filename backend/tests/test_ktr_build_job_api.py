"""
Tests de integración para el flujo async job_id: generate-async, {job_id}/connections,
{job_id}/status. Cubre la barrera (build_ktr se dispara sin importar el orden de
llegada), el caso de fallo del modelo, y el TTL.
"""
from __future__ import annotations

import asyncio
import json
import pathlib
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from unittest.mock import MagicMock

from app.core.auth import require_auth
from app.core.database import Base, get_db, get_session_factory
from app.core.dependencies import get_main_llm
from app.main import app
from app.models.connection import Connection, DbType
from app.models.ktr_build_job import KtrBuildJob, ModelStatus, KtrBuildStatus
from app.models.llm_base import BaseLLM, LLMResponse

_engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
_Session = sessionmaker(bind=_engine)


@pytest.fixture(autouse=True)
def _clean_db():
    Base.metadata.create_all(bind=_engine)
    yield
    Base.metadata.drop_all(bind=_engine)


def _fake_llm_ok() -> BaseLLM:
    ktr_json = {
        "proceso_etl": {"nombre": "TEST_PROC", "descripcion": "", "steps": []},
        "validaciones": [],
        "documentacion": "",
        "advertencias_buenas_practicas": [],
        "ktr": {
            "name": "TEST_PROC",
            "description": "",
            "connections": [{"name": "conn_dwh", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"}],
            "steps": [
                {"name": "Leer", "type": "TableInput", "config": {"connection": "conn_dwh", "sql": "SELECT 1"}},
                {"name": "Escribir", "type": "TableOutput", "config": {"connection": "conn_dwh", "table": "dim_x"}},
            ],
            "hops": [{"from": "Leer", "to": "Escribir", "enabled": True}],
        },
    }

    async def _complete(user_message, system, schema=None):
        return LLMResponse(content=json.dumps(ktr_json), json_data=ktr_json, model="test", input_tokens=1, output_tokens=1, provider="test")

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    return llm


def _fake_llm_ok_real_sql() -> BaseLLM:
    # Como _fake_llm_ok(), pero con una query real en vez de "SELECT 1" — ese
    # literal es el fallback que _step_TableInput usa cuando el modelo no
    # mandó sql, y build.py lo trata como config crítico incompleto (mismo
    # criterio que un campo ausente), aborta el build con KtrBuilderError.
    # Sin relación con conexiones — hace falta para probar el camino
    # missing_layer_warnings()/build.connection_unresolved sin pisarse con
    # ese chequeo no relacionado.
    ktr_json = {
        "proceso_etl": {"nombre": "TEST_PROC", "descripcion": "", "steps": []},
        "validaciones": [],
        "documentacion": "",
        "advertencias_buenas_practicas": [],
        "ktr": {
            "name": "TEST_PROC",
            "description": "",
            "connections": [{"name": "conn_dwh", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"}],
            "steps": [
                {"name": "Leer", "type": "TableInput", "config": {"connection": "conn_dwh", "sql": "SELECT id FROM origen"}},
                {"name": "Escribir", "type": "TableOutput", "config": {"connection": "conn_dwh", "table": "dim_x"}},
            ],
            "hops": [{"from": "Leer", "to": "Escribir", "enabled": True}],
        },
    }

    async def _complete(user_message, system, schema=None):
        return LLMResponse(content=json.dumps(ktr_json), json_data=ktr_json, model="test", input_tokens=1, output_tokens=1, provider="test")

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    return llm


def _fake_llm_fails() -> BaseLLM:
    async def _complete(user_message, system, schema=None):
        raise RuntimeError("modelo caído")

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    return llm


@pytest.fixture
def client():
    def _override_get_db():
        db = _Session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_session_factory] = lambda: _Session
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(get_db, None)
    app.dependency_overrides.pop(get_session_factory, None)
    app.dependency_overrides.pop(get_main_llm, None)
    app.dependency_overrides.pop(require_auth, None)


def _login_as(sub: str) -> None:
    app.dependency_overrides[require_auth] = lambda: {"sub": sub}


def _make_connection(db_session, owner_id: str | None = None) -> str:
    conn = Connection(
        name="dest_conn", db_type=DbType.postgresql, host="h", port=5432,
        database="d", username="u",
        owner_id=owner_id,
    )
    db_session.add(conn)
    db_session.commit()
    db_session.refresh(conn)
    return str(conn.id)


def _req_body() -> dict:
    return {
        "descripcionObjetivo": "obj",
        "origenTables": [{"tableName": "src", "columns": [{"name": "id", "dataType": "int"}]}],
        "stg_definition": "CREATE TABLE STG_X (id INT);",
        "dwh_model": "CREATE TABLE DIM_X (id INT);",
        "reglasNegocio": "",
    }


async def _drain_pending_tasks():
    # Deja correr el asyncio.create_task del endpoint (generate_etl_async)
    # antes de que el test siga pidiendo /status.
    await asyncio.sleep(0.05)


def test_connections_before_model_then_model_finishes(client):
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_ok()
    db = _Session()
    conn_id = _make_connection(db)
    db.close()

    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    # Caso (a): las conexiones llegan ANTES de que el modelo termine.
    resp = client.post(f"/api/v1/etl/{job_id}/connections", json={"conn_dwh": conn_id})
    assert resp.status_code == 200, resp.text
    assert resp.json()["build_status"] in ("awaiting_model", "built")  # depende del timing del task

    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    body = resp.json()
    assert body["model_status"] == "done"
    assert body["build_status"] == "built"
    etapa_origen_stg = body["result"]["etapas"][0]
    assert etapa_origen_stg["tipo"] == "ktr"
    assert etapa_origen_stg["archivo"]["xml"]
    assert "<server>h</server>" in etapa_origen_stg["archivo"]["xml"]


def test_model_finishes_then_connections_arrive(client):
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_ok()
    db = _Session()
    conn_id = _make_connection(db)
    db.close()

    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    assert resp.json()["build_status"] == "awaiting_connections"

    # Caso (b, orden normal): conexiones llegan DESPUÉS del modelo.
    resp = client.post(f"/api/v1/etl/{job_id}/connections", json={"conn_dwh": conn_id})
    assert resp.status_code == 200
    assert resp.json()["build_status"] == "built"


def test_model_failure_blocks_build_even_with_connections(client):
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_fails()
    db = _Session()
    conn_id = _make_connection(db)
    db.close()

    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    # Usuario ya cargó conexiones mientras el modelo (que va a fallar) corre.
    resp = client.post(f"/api/v1/etl/{job_id}/connections", json={"conn_dwh": conn_id})
    assert resp.status_code == 200

    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    body = resp.json()
    assert body["build_status"] == "failed"
    assert body["model_status"] == "failed"
    assert body["result"] is None
    assert "modelo caído" in body["error"]


def test_missing_connection_id_produces_warning_not_failure(client):
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_ok()
    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    fake_conn_id = str(uuid.uuid4())
    resp = client.post(f"/api/v1/etl/{job_id}/connections", json={"conn_dwh": fake_conn_id})
    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    body = resp.json()
    assert body["build_status"] == "built"  # no falla, usa placeholder
    assert any("conn_dwh" in w for w in body["result"]["advertencias_buenas_practicas"])


def test_absent_connection_layer_produces_warning_and_progress_event_not_failure(client):
    # El bug reportado: conn_origen nunca llega a connections_map (origen por
    # CSV/Excel/DDL/formulario, sin connection_id derivable) — antes tumbaba
    # el build entero. Ahora se completa a mano en Spoon: build "built", con
    # advertencia y un evento de progreso build.connection_unresolved (D15).
    #
    # conn_dwh se manda como InlineConnection (dict) a propósito, no como
    # connection_id string — mandarlo como string pega contra H24
    # (`ConnectionsMapRequest.conn_dwh` no acepta esa forma, 422), bug
    # preexistente y fuera de alcance de este cambio (ver docs/refactor/02-decisiones.md § C.7).
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_ok_real_sql()

    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    # Solo conn_dwh — conn_origen/conn_staging nunca se mandan.
    resp = client.post(f"/api/v1/etl/{job_id}/connections", json={"conn_dwh": {
        "db_type": "postgresql", "host": "dwh.example", "port": 5432,
        "database": "dwh", "username": "etl_user",
    }})
    assert resp.status_code == 200, resp.text
    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    body = resp.json()
    assert body["build_status"] == "built"
    assert body["result"] is not None
    advertencias = body["result"]["advertencias_buenas_practicas"]
    assert any("conn_origen" in w for w in advertencias)
    assert any("conn_staging" in w for w in advertencias)

    unresolved_events = [
        e for e in body["progress"]
        if e["code"] == "build.connection_unresolved" and e["level"] == "warning"
    ]
    assert any("conn_origen" in e["message"] for e in unresolved_events)


def test_conn_origen_accepts_inline_connection_metadata(client):
    # H24-adjacent: conn_origen ahora acepta tanto un connection_id (string,
    # conexión guardada) como InlineConnection (dict, origen sin fila
    # Connection — CSV/Excel/DDL/formulario). Antes ConnectionsMapRequest solo
    # tipaba conn_origen como Optional[str] y esto daba 422.
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_ok()
    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    resp = client.post(
        f"/api/v1/etl/{job_id}/connections",
        json={"conn_origen": {
            "db_type": "postgresql", "host": "origen.example", "port": 5432,
            "database": "ventas", "username": "etl_user",
        }},
    )
    assert resp.status_code == 200, resp.text


# ─── D35 (docs/refactor/02-decisiones.md): build-from-raw acepta connections_map ──
# Bug reportado: "Reutilizar respuesta" (build-from-raw) ignoraba las conexiones
# por completo — el .ktr salía siempre con placeholder aunque el usuario ya
# las hubiera completado en el formulario (verificado contra un ETL real en
# Supabase: form_data.connectionsMap bien guardado, resolve_real_connections
# resolvía bien en replay, pero el resultado no tenía ni un warning de conexión
# porque no pasó por _try_build sino por este endpoint).

def _raw_llm_data_two_ktr() -> dict:
    ktr_1 = {
        "name": "K1", "description": "",
        "connections": [
            {"name": "conn_origen", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"},
            {"name": "conn_staging", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"},
        ],
        "steps": [
            {"name": "Leer", "type": "TableInput", "config": {"connection": "conn_origen", "sql": "SELECT id FROM origen"}},
            {"name": "Escribir", "type": "TableOutput", "config": {"connection": "conn_staging", "table": "stg_x"}},
        ],
        "hops": [{"from": "Leer", "to": "Escribir", "enabled": True}],
    }
    ktr_2 = {
        "name": "K2", "description": "",
        "connections": [
            {"name": "conn_staging", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"},
            {"name": "conn_dwh", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"},
        ],
        "steps": [
            {"name": "Leer2", "type": "TableInput", "config": {"connection": "conn_staging", "sql": "SELECT id FROM stg_x"}},
            {"name": "Escribir2", "type": "TableOutput", "config": {"connection": "conn_dwh", "table": "dim_x"}},
        ],
        "hops": [{"from": "Leer2", "to": "Escribir2", "enabled": True}],
    }
    envelope = {"proceso_etl": {"nombre": "TEST_PROC", "descripcion": "", "steps": []}, "validaciones": [], "documentacion": "", "advertencias_buenas_practicas": []}
    return {"ktr_1": {**envelope, "ktr": ktr_1}, "ktr_2": {**envelope, "ktr": ktr_2}}


def _all_xml(result_body: dict) -> str:
    parts = []
    for et in result_body["etapas"]:
        if et.get("archivo"):
            parts.append(et["archivo"]["xml"])
        for a in et.get("archivos", []):
            parts.append(a["xml"])
    return "\n".join(parts)


def test_build_from_raw_without_connections_map_keeps_historical_placeholder(client):
    # connections_map ausente (default None) — comportamiento histórico intacto.
    resp = client.post("/api/v1/etl/build-from-raw", json={"raw_llm_data": _raw_llm_data_two_ktr()})
    assert resp.status_code == 200, resp.text
    assert "PLACEHOLDER_HOST" in _all_xml(resp.json())


def test_build_from_raw_with_connections_map_resolves_real_metadata_in_both_stages(client):
    resp = client.post("/api/v1/etl/build-from-raw", json={
        "raw_llm_data": _raw_llm_data_two_ktr(),
        "connections_map": {
            "conn_staging": {"db_type": "postgresql", "host": "stg.example", "port": 5432, "database": "stgdb", "username": "stguser"},
            "conn_dwh": {"db_type": "postgresql", "host": "dwh.example", "port": 5432, "database": "dwhdb", "username": "dwhuser"},
        },
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    xml = _all_xml(body)
    assert "<server>stg.example</server>" in xml
    assert "<server>dwh.example</server>" in xml
    assert "<type>POSTGRESQL</type>" in xml
    assert "${STAGING_DB_PASSWORD}" in xml
    assert "${DWH_DB_PASSWORD}" in xml
    # conn_origen no se mandó en el mapa — sigue en placeholder, con warning
    # accionable (missing_layer_warnings), no un build roto.
    assert "PLACEHOLDER_HOST" in xml
    assert any("conn_origen" in w for w in body["advertencias_buenas_practicas"])


def test_build_from_raw_with_unknown_origen_connection_id_warns_not_fails(client):
    # Regresión: un conn_origen con UUID que no existe en `connections` (la
    # segunda causa del bug reportado — fila borrada/de otro owner) no tumba
    # el build, sale como warning "no encontrada" (resolve_real_connections).
    resp = client.post("/api/v1/etl/build-from-raw", json={
        "raw_llm_data": _raw_llm_data_two_ktr(),
        "connections_map": {"conn_origen": str(uuid.uuid4())},
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any("conn_origen" in w and "no encontrada" in w for w in body["advertencias_buenas_practicas"])


def test_unknown_job_id_returns_404(client):
    resp = client.get(f"/api/v1/etl/{uuid.uuid4()}/status")
    assert resp.status_code == 404


def test_malformed_job_id_returns_404(client):
    resp = client.get("/api/v1/etl/not-a-uuid/status")
    assert resp.status_code == 404


def test_expired_job_returns_410(client):
    db = _Session()
    job = KtrBuildJob(expires_at=datetime.now(timezone.utc) - timedelta(minutes=1))
    db.add(job)
    db.commit()
    db.refresh(job)
    job_id = str(job.id)
    db.close()

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    assert resp.status_code == 410

    # La fila vencida se borra al primer acceso (lazy expiry).
    db = _Session()
    assert db.get(KtrBuildJob, job.id) is None
    db.close()


# ─── Ownership (hallazgo B) ───────────────────────────────────────────────────

def test_cross_owner_cannot_read_or_attach_connections_to_foreign_job(client):
    app.dependency_overrides[get_main_llm] = lambda: _fake_llm_ok()
    db = _Session()
    conn_id = _make_connection(db)
    db.close()

    _login_as("user-a")
    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    _login_as("user-b")
    assert client.get(f"/api/v1/etl/{job_id}/status").status_code == 404
    assert client.post(
        f"/api/v1/etl/{job_id}/connections", json={"conn_dwh": conn_id}
    ).status_code == 404

    _login_as("user-a")
    assert client.get(f"/api/v1/etl/{job_id}/status").status_code == 200


def test_attaching_a_foreign_connection_id_to_own_job_falls_back_to_placeholder(client):
    # user-b arma su propio job (dueño legítimo) pero intenta atar el connection_id
    # de user-a. Sin el chequeo de ownership en resolve_real_connections, esto
    # desofuscaba y embebía el password de user-a en el .ktr de user-b.
    # sql real (no "SELECT 1") — ese literal lo trata build.py como placeholder
    # de config faltante, independiente de todo lo de ownership acá probado.
    ktr_json = {
        "proceso_etl": {"nombre": "TEST_PROC", "descripcion": "", "steps": []},
        "validaciones": [], "documentacion": "", "advertencias_buenas_practicas": [],
        "ktr": {
            "name": "TEST_PROC", "description": "",
            "connections": [{"name": "conn_dwh", "type": "GENERIC", "host": "PLACEHOLDER_HOST", "database": "PLACEHOLDER_DATABASE", "port": 0, "username": "PLACEHOLDER_USER"}],
            "steps": [
                {"name": "Leer", "type": "TableInput", "config": {"connection": "conn_dwh", "sql": "SELECT id FROM origen"}},
                {"name": "Escribir", "type": "TableOutput", "config": {"connection": "conn_dwh", "table": "dim_x"}},
            ],
            "hops": [{"from": "Leer", "to": "Escribir", "enabled": True}],
        },
    }

    async def _complete(user_message, system, schema=None):
        return LLMResponse(content=json.dumps(ktr_json), json_data=ktr_json, model="test", input_tokens=1, output_tokens=1, provider="test")

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    app.dependency_overrides[get_main_llm] = lambda: llm
    db = _Session()
    foreign_conn_id = _make_connection(db, owner_id="user-a")
    db.close()

    _login_as("user-b")
    resp = client.post("/api/v1/etl/generate-async", json=_req_body())
    job_id = resp.json()["job_id"]

    resp = client.post(f"/api/v1/etl/{job_id}/connections", json={"conn_dwh": foreign_conn_id})
    assert resp.status_code == 200
    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    body = resp.json()
    # _try_build llama a build_ktr con strict_connections=True (ver etl_generator.py).
    # Una conexión que queda sin resolver ya NO aborta el build (D15,
    # docs/refactor/02-decisiones.md) — se entrega el .ktr con placeholder y se
    # avisa. Lo que SÍ sigue valiendo, chequeo de ownership mediante: el .ktr de
    # user-b nunca lleva host/datos ni password reales de la conexión de user-a.
    assert body["build_status"] == "built"
    assert body["result"] is not None
    assert any("conn_dwh" in w for w in body["result"]["advertencias_buenas_practicas"])
    assert "user-a" not in json.dumps(body)
    etapa = body["result"]["etapas"][0]
    assert "PLACEHOLDER_HOST" in etapa["archivo"]["xml"]  # nunca el host real de user-a


# ─── O1-b, criterios de terminado 3 y 4 (10-estabilizar-emision.md) ───────────
# Corpus real de E-01 (errores.md) a través del camino que el diagnóstico
# original NUNCA ejercitó: /generate-async -> /connections -> /status, no
# build_etl_from_raw() directo (eso es lo que D64 corrió, con llm=None). Este
# test reproduce el 'Cargar dim_producto' con 3 columnas inventadas
# (fk_categoria/precio_lista/stock, vocabulario de fact_inventario, no de la
# dimensión) que motivó el crash original.

_E01_ROOT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "refactor" / "fase4_manual" / "sonnet"


def _e01_raw_llm_data() -> dict:
    corpus = json.loads((_E01_ROOT / "etl-llm-raw-test-01_sonnet_fase4.json").read_text(encoding="utf-8"))
    return corpus["raw_llm_data"]


def _e01_ddl() -> tuple[str, str]:
    # DDL-inferido-test-con-raw.txt: dos líneas `"stg_definition": "..."` /
    # `"dwh_model": "..."`, con \n escapado DOBLE (double-encoded al exportarse
    # una vez de más) — de ahí el replace de "\\\\n" (2 backslashes + n), no
    # "\\n".
    text = (_E01_ROOT / "DDL-inferido-test-con-raw.txt").read_text(encoding="utf-8")

    def _clean(line: str) -> str:
        _, val = line.split(":", 1)
        val = val.strip()
        if val.endswith(","):
            val = val[:-1]
        val = val[1:-1]
        val = val.replace("\\\\n", "\n")
        val = val.replace("\\'", "'")
        return val

    lines = text.split("\n")
    return _clean(lines[0]), _clean(lines[1])


def _e01_dim_contracts() -> list[dict]:
    # Ambas dimensiones son SCD1 según el DDL real (comentarios COMMENT ON
    # TABLE ... 'SCD1: sobreescribe sin versionar').
    return [
        {
            "table": "dim_categoria", "scd_type": 1, "technical_key": "sk_categoria",
            "version_field": "version", "date_from": "fecha_inicio", "date_to": "fecha_fin",
            "natural_keys": ["id_categoria_origen"], "unknown_key_value": 0,
            "attributes_scd1": ["nombre_categoria"], "attributes_scd2": [],
        },
        {
            "table": "dim_producto", "scd_type": 1, "technical_key": "sk_producto",
            "version_field": "version", "date_from": "fecha_inicio", "date_to": "fecha_fin",
            "natural_keys": ["id_producto_origen"], "unknown_key_value": 0,
            "attributes_scd1": ["nombre_producto", "nombre_categoria", "precio_unitario", "bk_producto"],
            "attributes_scd2": [],
        },
    ]


def _e01_llm(stg_ddl: str, dwh_ddl: str, raw: dict):
    """3 llamadas reales del flujo (auditoría DDL, etapa origen_stg, etapa
    stg_dwh) devuelven el corpus tal cual; cualquier llamada de más (los
    repairs — repair_ktr_steps/repair_integrity_gaps/_repair_dimension_
    loader_fields) devuelve json_data=None, que cada call site ya trata como
    intento fallido (no rompe nada — es la misma superficie de 'repair no
    disponible' que build-from-raw con llm=None, E-21)."""
    calls = {"n": 0}

    async def _complete(user_message, system, schema=None):
        calls["n"] += 1
        if calls["n"] == 1:
            data = {"dwh_ddl": dwh_ddl, "sin_cambios": True, "cambios_aplicados": [], "conflictos": []}
        elif calls["n"] == 2:
            data = raw["ktr_1"]
        elif calls["n"] == 3:
            data = raw["ktr_2"]
        else:
            return LLMResponse(content="", json_data=None, model="test", input_tokens=1, output_tokens=1, provider="test")
        return LLMResponse(content=json.dumps(data), json_data=data, model="test", input_tokens=1, output_tokens=1, provider="test")

    llm = MagicMock(spec=BaseLLM)
    llm.complete = _complete
    return llm, calls


def test_e01_corpus_through_real_async_pipeline_reaches_built(client):
    """Reproduce el corpus real de E-01 (cerrado D64, pero D64 llamó a
    build_etl_from_raw() directo con llm=None — nunca ejercitó este camino).
    Criterio de terminado 3: build_status pasa a 'built' a través de
    /generate-async -> /connections -> /status, y el finding de vocabulario
    cruzado (los 3 campos que no existen en dim_producto: fk_categoria,
    precio_lista, stock) llega a result['validaciones']."""
    stg_ddl, dwh_ddl = _e01_ddl()
    raw = _e01_raw_llm_data()
    llm, calls = _e01_llm(stg_ddl, dwh_ddl, raw)
    app.dependency_overrides[get_main_llm] = lambda: llm

    body = {
        "descripcionObjetivo": "Cargar productos y categorias a un DWH de inventario",
        "origenTables": [
            {"tableName": "categorias", "columns": [
                {"name": "cod_categoria", "dataType": "int"},
                {"name": "nombre_categoria", "dataType": "varchar"},
            ]},
            {"tableName": "productos", "columns": [
                {"name": "cod_producto", "dataType": "int"},
                {"name": "nombre_producto", "dataType": "varchar"},
                {"name": "categoria", "dataType": "varchar"},
                {"name": "precio_lista", "dataType": "numeric"},
            ]},
        ],
        "stg_definition": stg_ddl,
        "dwh_model": dwh_ddl,
        "reglasNegocio": "Se descartan precios negativos. valor_inventario = precio_unitario * stock.",
        "dim_contracts": _e01_dim_contracts(),
    }

    resp = client.post("/api/v1/etl/generate-async", json=body)
    assert resp.status_code == 200, resp.text
    job_id = resp.json()["job_id"]

    resp = client.post(f"/api/v1/etl/{job_id}/connections", json={
        "conn_origen": {"db_type": "postgresql", "host": "origen.example", "port": 5432, "database": "origendb", "username": "u"},
        "conn_staging": {"db_type": "postgresql", "host": "stg.example", "port": 5432, "database": "stgdb", "username": "u"},
        "conn_dwh": {"db_type": "postgresql", "host": "dwh.example", "port": 5432, "database": "dwhdb", "username": "u"},
    })
    assert resp.status_code == 200, resp.text
    asyncio.run(_drain_pending_tasks())

    resp = client.get(f"/api/v1/etl/{job_id}/status")
    status = resp.json()
    assert status["model_status"] == "done"
    # Criterio 3: no 'failed' — el crash original de E-01 (KtrBuilderError,
    # cero archivos) ya no puede volver a pasar por este camino.
    assert status["build_status"] == "built", status.get("error")
    result = status["result"]
    assert result is not None
    assert calls["n"] >= 3  # las 3 llamadas reales (DDL + 2 etapas) sí ocurrieron

    # Las dos etapas entregan archivo — el escenario "cero archivos" (motivo
    # original de O1) no ocurrió.
    assert len(result["etapas"]) == 2
    for etapa in result["etapas"]:
        assert etapa.get("archivo") or etapa.get("archivos")

    # El finding de vocabulario cruzado llega al usuario, nombrando los 3
    # campos que no existen en dim_producto (vienen de fact_inventario).
    validaciones_txt = json.dumps(result["validaciones"], ensure_ascii=False)
    assert "Cargar dim_producto" in validaciones_txt
    for campo_inventado in ("fk_categoria", "precio_lista", "stock"):
        assert campo_inventado in validaciones_txt, f"finding no menciona '{campo_inventado}'"

    # Criterio 4: plugin ids reales de Kettle, no solo XML bien formado
    # (ElementTree no distingue esto — E-11 es el precedente exacto: pasaba
    # ElementTree.parse() y Spoon igual marcaba el step "missing"). Sin Spoon
    # en este entorno (verificado — no hay Data Integration instalado):
    # cross-check contra investigacion-tags-validos-por-step.md, que ya
    # verificó clase+línea de pentaho-kettle para los 13 tipos de step de
    # este corpus. Ninguno necesita _XML_TYPE_OVERRIDES salvo GetSystemInfo
    # (-> 'SystemInfo', ya cubierto) — ninguno cae en la trampa de E-11
    # (SplitFieldToRows sin el '3').
    expected_xml_type = {
        "GetSystemInfo": "SystemInfo",
        "TableInput": "TableInput", "Constant": "Constant", "JoinRows": "JoinRows",
        "SelectValues": "SelectValues", "TableOutput": "TableOutput", "WriteToLog": "WriteToLog",
        "DimensionLookup": "DimensionLookup", "FilterRows": "FilterRows", "Dummy": "Dummy",
        "ConcatFields": "ConcatFields", "Calculator": "Calculator", "InsertUpdate": "InsertUpdate",
    }
    all_xml = "\n".join(
        (etapa["archivo"]["xml"] if etapa.get("archivo") else "\n".join(a["xml"] for a in etapa["archivos"]))
        for etapa in result["etapas"]
    )
    for stage_raw in (raw["ktr_1"], raw["ktr_2"]):
        for step in stage_raw["ktr"]["steps"]:
            canonical = step["type"]
            xml_type = expected_xml_type[canonical]
            assert f"<name>{step['name']}</name>\n    <type>{xml_type}</type>" in all_xml, (
                f"step '{step['name']}' no emitió <type>{xml_type}</type> — "
                f"plugin id inválido dejaría el step 'missing' en Spoon (patrón E-11)"
            )
