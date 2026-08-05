"""F3 puntos 1-3 (03-plan.md) — el wiring del corte hacia etl_generator.py y
lineage_builder.py: split_ktr_by_cut(), _build_ktr_stage(), _build_job_plan()
generalizado a N por etapa (jerarquía de 3 niveles, F2.5/H7) y
stitch_lineage_many(). test_fragmentation.py cubre el algoritmo puro
(compute_cut); este archivo cubre el contrato que ese resultado expone hacia
la fase siguiente (D13).

build_ktr() real queda mockeado en los tests de _build_ktr_stage: lo que se
verifica acá es que el split llama build_ktr() una vez por grupo con el
sub-dict correcto, no la validación interna de build_ktr() (ya cubierta en
otro lado — un fixture Kettle-válido completo es ruido para este contrato)."""
from __future__ import annotations

import re
from xml.etree.ElementTree import fromstring

from app.services import etl_generator
from app.services.kjb_xml_validator import validate_kjb_xml
from app.services.ktr_builder.fragmentation import split_ktr_by_cut
from app.services.ktr_builder.naming import kjb_filename, ktr_filename
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES
from app.services.lineage_builder import stitch_lineage, stitch_lineage_many


def _same_except_time(actual: str, expected: str) -> bool:
    """Compara ignorando los segundos del timestamp — llamar ktr_filename()/
    kjb_filename() de nuevo en el test para armar el 'expected' puede cruzar
    un borde de segundo respecto a la llamada real dentro de _build_ktr_stage()
    (dos datetime.now() distintos); la fecha (día) sí debe coincidir siempre."""
    strip_seconds = lambda s: re.sub(r"_\d{6}(?=\.\w+$)", "", s)
    return strip_seconds(actual) == strip_seconds(expected)


def _err1_like_ktr():
    """Misma forma que test_fragmentation.py — reproducida acá para no
    acoplar este archivo a los internals de ese módulo de test."""
    return {
        "steps": [
            {"name": "Leer Staging Productos", "type": "TableInput",
             "config": {"connection": "c", "sql": "SELECT * FROM stg_producto"}},
            {"name": "Cargar Dim Producto", "type": "DimensionLookup",
             "config": {"table": "dim_producto", "connection": "conn_dwh", "returnfield": "sk_producto",
                        "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}]}},
            {"name": "Leer Staging Ventas", "type": "TableInput",
             "config": {"connection": "c", "sql": "SELECT * FROM stg_venta"}},
            {"name": "Lookup Dim Producto", "type": "DimensionLookup",
             "config": {"table": "dim_producto", "connection": "conn_dwh", "returnfield": "sk_producto",
                        "update": "N",
                        "keys": [{"stream_field": "id_producto", "table_field": "id_producto"}]}},
            {"name": "Cargar Fact Venta", "type": "InsertUpdate",
             "config": {"table": "fact_venta", "connection": "conn_dwh"}},
        ],
        "hops": [
            {"from": "Leer Staging Productos", "to": "Cargar Dim Producto", "enabled": True},
            {"from": "Leer Staging Ventas", "to": "Lookup Dim Producto", "enabled": True},
            {"from": "Lookup Dim Producto", "to": "Cargar Fact Venta", "enabled": True},
        ],
    }


# ─── split_ktr_by_cut (punto 1) ────────────────────────────────────────────

def test_split_ktr_by_cut_partitions_steps_and_hops():
    sub_dicts, notifications = split_ktr_by_cut(_err1_like_ktr(), STEP_TYPE_ALIASES)
    assert notifications == []
    assert len(sub_dicts) == 2

    names_0 = {s["name"] for s in sub_dicts[0]["steps"]}
    names_1 = {s["name"] for s in sub_dicts[1]["steps"]}
    assert names_0 == {"Leer Staging Productos", "Cargar Dim Producto"}
    assert names_1 == {"Leer Staging Ventas", "Lookup Dim Producto", "Cargar Fact Venta"}

    # Hops solo internos a cada grupo — ninguno cruza a un step del otro grupo.
    assert all(h["from"] in names_0 and h["to"] in names_0 for h in sub_dicts[0]["hops"])
    assert all(h["from"] in names_1 and h["to"] in names_1 for h in sub_dicts[1]["hops"])
    assert len(sub_dicts[0]["hops"]) + len(sub_dicts[1]["hops"]) == len(_err1_like_ktr()["hops"])


def test_split_ktr_by_cut_single_group_returns_same_object():
    ktr = {"steps": [{"name": "A", "type": "TableInput", "config": {}}], "hops": []}
    sub_dicts, notifications = split_ktr_by_cut(ktr, STEP_TYPE_ALIASES)
    assert sub_dicts == [ktr]
    assert sub_dicts[0] is ktr
    assert notifications == []


# ─── _build_ktr_stage (punto 1) ────────────────────────────────────────────

def test_build_ktr_stage_calls_build_ktr_once_per_group(monkeypatch):
    calls: list[tuple[str, list[str]]] = []

    def _fake_build_ktr(ktr_data, name, **kwargs):
        calls.append((name, [s["name"] for s in ktr_data["steps"]]))
        return f"<xml name='{name}'/>", f"{name}.ktr", []

    monkeypatch.setattr(etl_generator, "build_ktr", _fake_build_ktr)
    built, warnings = etl_generator._build_ktr_stage(_err1_like_ktr(), "stg_dwh", etapa_label="stg_dwh")

    assert len(built) == 2
    # D45 punto 1: 'stg_producto'/'stg_venta' ahora se resuelven por SQL real
    # (antes invisibles) — V2 (severity="warning", tabla leída sin writer en
    # ESTA etapa, legítimo: se escribe en origen->stg) es esperado acá, no un
    # error de este contrato de wiring.
    assert warnings == [
        "Tabla 'stg_producto (conexión 'c')': leída por 'Leer Staging Productos' pero ningún step "
        "de esta etapa la escribe (V2) — verificar que se cargue en otra etapa/archivo antes de "
        "ejecutar en Spoon.",
        "Tabla 'stg_venta (conexión 'c')': leída por 'Leer Staging Ventas' pero ningún step de esta "
        "etapa la escribe (V2) — verificar que se cargue en otra etapa/archivo antes de ejecutar en Spoon.",
    ]
    assert [c[0] for c in calls] == ["stg_dwh_1", "stg_dwh_2"]
    assert calls[0][1] == ["Leer Staging Productos", "Cargar Dim Producto"]
    assert calls[1][1] == ["Leer Staging Ventas", "Lookup Dim Producto", "Cargar Fact Venta"]
    # (ktr_data_del_grupo, xml, filename) en el mismo orden que las llamadas —
    # filename ya no es el que devuelve el fake build_ktr, lo recalcula
    # _build_ktr_stage() vía naming.ktr_filename(process_name, etapa_label, index).
    assert _same_except_time(built[0][2], ktr_filename("stg_dwh", "stg_dwh", index=1))
    assert _same_except_time(built[1][2], ktr_filename("stg_dwh", "stg_dwh", index=2))


def test_build_ktr_stage_single_group_keeps_base_name(monkeypatch):
    calls: list[str] = []

    def _fake_build_ktr(ktr_data, name, **kwargs):
        calls.append(name)
        return "<xml/>", f"{name}.ktr", []

    monkeypatch.setattr(etl_generator, "build_ktr", _fake_build_ktr)
    ktr = {"steps": [{"name": "A", "type": "TableInput", "config": {}}], "hops": []}
    built, _ = etl_generator._build_ktr_stage(ktr, "origen_stg", etapa_label="origen_stg")

    assert calls == ["origen_stg"]  # sin sufijo _1 cuando hay 1 solo grupo
    assert len(built) == 1


def test_build_ktr_stage_forwards_kwargs_to_build_ktr(monkeypatch):
    received = {}

    def _fake_build_ktr(ktr_data, name, **kwargs):
        received.update(kwargs)
        return "<xml/>", f"{name}.ktr", []

    monkeypatch.setattr(etl_generator, "build_ktr", _fake_build_ktr)
    ktr = {"steps": [{"name": "A", "type": "TableInput", "config": {}}], "hops": []}
    etl_generator._build_ktr_stage(ktr, "origen_stg", etapa_label="origen_stg", pass_source_connection="conn_origen")

    assert received["pass_source_connection"] == "conn_origen"


# ─── _build_job_plan (punto 2 — jerarquía de 3 niveles, F2.5/H7) ──────────

def test_build_job_plan_single_file_per_stage_no_sub_kjb():
    stages = [
        ("origen_stg", [({}, "<x/>", "ktr1.ktr")]),
        ("stg_dwh", [({}, "<x/>", "ktr2.ktr")]),
    ]
    job_plan, sub_kjbs = etl_generator._build_job_plan(stages, "Proceso")

    assert sub_kjbs == []
    entries = job_plan.execution_order
    assert [e.filename for e in entries] == ["ktr1.ktr", "ktr2.ktr"]
    assert [e.entry_type for e in entries] == ["trans", "trans"]
    assert [e.order for e in entries] == [1, 2]

    from app.services.job_analyzer import build_kjb_xml
    validate_kjb_xml(build_kjb_xml(job_plan))  # no debe levantar


def test_build_job_plan_multi_file_stage_builds_inner_kjb_and_job_entry():
    stages = [
        ("origen_stg", [({}, "<x/>", "ktr1.ktr")]),
        ("stg_dwh", [
            ({}, "<x/>", "ktr2_1.ktr"),
            ({}, "<x/>", "ktr2_2.ktr"),
        ]),
    ]
    job_plan, sub_kjbs = etl_generator._build_job_plan(stages, "Proceso")

    assert len(sub_kjbs) == 1
    inner_xml, inner_filename = sub_kjbs[0]
    assert _same_except_time(inner_filename, kjb_filename("Proceso", "stg_dwh"))
    validate_kjb_xml(inner_xml)  # el .kjb intermedio también es válido standalone
    root = fromstring(inner_xml)
    inner_files = {e.findtext("filename") for e in root.findall("./entries/entry") if e.findtext("type") == "TRANS"}
    assert any(f and f.endswith("ktr2_1.ktr") for f in inner_files)
    assert any(f and f.endswith("ktr2_2.ktr") for f in inner_files)

    entries = job_plan.execution_order
    assert len(entries) == 2  # 1 trans (origen_stg) + 1 job (stg_dwh), no 3
    assert entries[0].entry_type == "trans"
    assert entries[0].filename == "ktr1.ktr"
    assert entries[1].entry_type == "job"
    # Co-ubicado con sus N .ktr en la carpeta de la etapa (fix del bug de
    # ruta encontrado en esta sesión) — el maestro está en la raíz del ZIP,
    # necesita el prefijo "stg_dwh/" para encontrar el .kjb orquestador.
    assert entries[1].filename == f"stg_dwh/{inner_filename}"

    from app.services.job_analyzer import build_kjb_xml
    validate_kjb_xml(build_kjb_xml(job_plan))  # el job maestro también es válido


def test_build_job_plan_skips_empty_stage():
    stages = [
        ("origen_stg", []),
        ("stg_dwh", [({}, "<x/>", "ktr2.ktr")]),
    ]
    job_plan, sub_kjbs = etl_generator._build_job_plan(stages, "Proceso")
    assert sub_kjbs == []
    assert len(job_plan.execution_order) == 1
    assert job_plan.execution_order[0].filename == "ktr2.ktr"
    assert job_plan.execution_order[0].order == 1


# ─── stitch_lineage_many (punto 3) ─────────────────────────────────────────

def _table_input(name: str, table: str) -> dict:
    return {"name": name, "type": "TableInput", "config": {"sql": f"SELECT * FROM {table}", "connection": "c"}}


def _table_output(name: str, table: str) -> dict:
    return {"name": name, "type": "TableOutput", "config": {"table": table, "connection": "c"}}


def test_stitch_lineage_many_connects_non_adjacent_files():
    """3 archivos: F0 escribe stg_productos, F1 (intermedio, sin relación de
    tabla con F0) es puro passthrough, F2 lee stg_productos — la costura debe
    conectar F0 -> F2 directamente, saltando F1, matcheado por nombre de
    tabla (no por adyacencia posicional)."""
    file_0 = {"steps": [_table_output("Escribir Productos", "stg_productos")], "hops": []}
    file_1 = {
        "steps": [
            {"name": "Leer Otro", "type": "TableInput", "config": {"sql": "SELECT * FROM otra_tabla", "connection": "c"}},
            _table_output("Escribir Otro", "otra_tabla"),
        ],
        "hops": [{"from": "Leer Otro", "to": "Escribir Otro", "enabled": True}],
    }
    file_2 = {"steps": [_table_input("Leer Productos", "stg_productos")], "hops": []}

    lineage = stitch_lineage_many([file_0, file_1, file_2])
    names = {n.step_name for n in lineage.nodes}
    assert names == {
        "Escribir Productos",
        "F1::Leer Otro", "F1::Escribir Otro",
        "F2::Leer Productos",
    }
    synthetic = [e for e in lineage.edges if e.from_step == "Escribir Productos" and e.to_step == "F2::Leer Productos"]
    assert len(synthetic) == 1


def test_stitch_lineage_many_does_not_self_match_within_same_file():
    """Un TableInput y un TableOutput de la MISMA tabla dentro del MISMO
    archivo (self-lookup, no conectados por hop real) no deben coserse entre
    sí — solo cuentan como sink/source archivos DISTINTOS."""
    file_0 = {
        "steps": [_table_input("Leer X", "stg_x"), _table_output("Escribir X", "stg_x")],
        "hops": [],  # sin hop real entre ellos a propósito
    }
    lineage = stitch_lineage_many([file_0])
    assert lineage.edges == []


def test_stitch_lineage_two_files_matches_many_with_two():
    a = {"steps": [_table_output("Out", "stg_x")], "hops": []}
    b = {"steps": [_table_input("In", "stg_x")], "hops": []}
    assert stitch_lineage(a, b) == stitch_lineage_many([a, b])


def test_stitch_lineage_many_single_file_identity():
    a = {"steps": [_table_output("Out", "stg_x")], "hops": []}
    from app.services.lineage_builder import build_lineage
    assert stitch_lineage_many([a]) == build_lineage(a)


def test_stitch_lineage_many_empty_list():
    from app.services.lineage_builder import build_lineage
    assert stitch_lineage_many([]) == build_lineage({})
