"""
Test manual, con llamada REAL al LLM (consume API, cobra por llamada) -- NO se
corre nunca automaticamente: vive fuera de tests/ (pytest.ini solo colecciona
tests/test_*.py) y ademas queda afuera de `pytest tests/ -v`, el comando
estandar que documenta tests/README.md.

Correr a mano, explicito:
    cd backend
    venv\\Scripts\\activate
    pytest tests_manual_llm/test_h9_h10_live_scenario.py -v -s

Que valida (docs/refactor/01-hallazgos.md H9/H10, docs/refactor/02-decisiones.md D22
fila "E3 (mapeo invertido sk_producto/sk_tiempo), key vacia en CombinationLookup,
E14 (Number vs BigNumber)" + fila "E1/E2 (SelectValues solo-cast no ejercitado,
SCD2 declarado no ejercitado)"):
  - E3  mapeo invertido sk_producto/sk_tiempo en el loader de fact_venta
  - E14 campo monetario (importe) tipado Number en vez de BigNumber
  - key vacia en un step lookup-por-clave (CombinationLookup/DimensionLookup/
        StreamLookup/DBLookup) -- V13, catalogo E1-E14 original no lo cubria
  - E1  SelectValues solo-cast ejercitado (cantidad VARCHAR -> INTEGER)
  - E2  dimension SCD2 declarada Y ejercitada (dim_producto, scd_type=2 sobre
        categoria) -- el corpus original de H9 no tenia ninguna dimension SCD2

Mismo escenario que la corrida original de H9 (ventas/productos, dim_producto/
dim_tiempo/fact_venta), con dim_producto extendido a SCD2 sobre categoria para
forzar E2 -- el corpus original no lo ejercitaba (H10). dim_tiempo y el resto
del escenario quedan igual que el corpus original, para no perder fidelidad de
lo que ya reprodujo E3/E14/key-vacia una vez.
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest


def _load_env(env_path: Path = Path(__file__).parent.parent / ".env") -> None:
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip())


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures del escenario
# ---------------------------------------------------------------------------

STG_DDL = """
CREATE TABLE stg_oltp_productos (
    id_producto INTEGER,
    nombre VARCHAR(100),
    categoria VARCHAR(100),
    stg_fecha_carga TIMESTAMP NOT NULL DEFAULT NOW(),
    stg_origen VARCHAR(100) NOT NULL,
    stg_estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO'
);

CREATE TABLE stg_oltp_ventas (
    id_venta INTEGER,
    fecha_venta DATE,
    id_producto INTEGER,
    cantidad VARCHAR(50),
    precio_unitario NUMERIC(15,2),
    estado VARCHAR(50),
    stg_fecha_carga TIMESTAMP NOT NULL DEFAULT NOW(),
    stg_origen VARCHAR(100) NOT NULL,
    stg_estado VARCHAR(20) NOT NULL DEFAULT 'ACTIVO'
);
""".strip()

# dim_producto extendido a SCD2 sobre categoria (fecha_inicio_vigencia/
# fecha_fin_vigencia/version/vigente) respecto del DDL original de H9, para
# forzar E2 -- el resto (dim_tiempo, fact_venta) queda identico al corpus
# original que reprodujo E3/E14/key-vacia.
DWH_DDL = """
CREATE TABLE dim_producto (
    sk_producto SERIAL,
    id_producto INTEGER NOT NULL,
    nombre VARCHAR(100) NOT NULL,
    categoria VARCHAR(100) NOT NULL,
    fecha_inicio_vigencia DATE NOT NULL,
    fecha_fin_vigencia DATE,
    version INTEGER NOT NULL DEFAULT 1,
    vigente BOOLEAN NOT NULL DEFAULT TRUE,

    CONSTRAINT pk_dim_producto
        PRIMARY KEY (sk_producto)
);

CREATE TABLE dim_tiempo (
    sk_tiempo SERIAL,
    fecha DATE NOT NULL,
    anio INTEGER NOT NULL,
    mes INTEGER NOT NULL,
    dia INTEGER NOT NULL,

    CONSTRAINT pk_dim_tiempo
        PRIMARY KEY (sk_tiempo),

    CONSTRAINT uq_dim_tiempo_fecha
        UNIQUE (fecha)
);

CREATE TABLE fact_venta (
    id_venta INTEGER NOT NULL,
    fk_producto INTEGER NOT NULL,
    fk_tiempo INTEGER NOT NULL,
    cantidad INTEGER NOT NULL,
    precio_unitario NUMERIC(15,2) NOT NULL,
    importe NUMERIC(15,2) NOT NULL,
    estado VARCHAR(50) NOT NULL,

    CONSTRAINT pk_fact_venta
        PRIMARY KEY (id_venta),

    CONSTRAINT fk_fact_venta_producto
        FOREIGN KEY (fk_producto)
        REFERENCES dim_producto(sk_producto),

    CONSTRAINT fk_fact_venta_tiempo
        FOREIGN KEY (fk_tiempo)
        REFERENCES dim_tiempo(sk_tiempo)
);
""".strip()

REGLAS_NEGOCIO = """
1. Filtro: excluir estado = 'ANULADA'.
2. Metrica: importe = cantidad * precio_unitario.
3. dim_producto es SCD Tipo 2 sobre categoria: un cambio de categoria de un
   producto debe versionarse (nueva fila con fecha_inicio_vigencia,
   fecha_fin_vigencia y version incrementado), conservando el historial.
   nombre se sobrescribe en el lugar (SCD Tipo 1), sin generar nueva version.
""".strip()

DESCRIPCION_OBJETIVO = (
    "Cargar un datamart de ventas: la dimension de producto (SCD Tipo 2 sobre "
    "categoria) y una tabla de hechos con cantidad e importe por venta. "
    "Descartar las ventas anuladas."
)


def _origen_tables():
    from app.schemas.etl_schemas import ColumnaOrigen, TablaOrigen

    return [
        TablaOrigen(
            tableName="oltp_productos",
            columns=[
                ColumnaOrigen(name="id_producto", dataType="int"),
                ColumnaOrigen(name="nombre", dataType="string"),
                ColumnaOrigen(name="categoria", dataType="string"),
            ],
        ),
        TablaOrigen(
            tableName="oltp_ventas",
            columns=[
                ColumnaOrigen(name="id_venta", dataType="int"),
                ColumnaOrigen(name="fecha_venta", dataType="date"),
                ColumnaOrigen(name="id_producto", dataType="int"),
                ColumnaOrigen(name="cantidad", dataType="int"),
                ColumnaOrigen(name="precio_unitario", dataType="float"),
                ColumnaOrigen(name="estado", dataType="string"),
            ],
        ),
    ]


def _dim_contracts():
    from app.schemas.etl_schemas import DimContract

    return [
        DimContract(
            table="dim_producto", scd_type=2, technical_key="sk_producto",
            version_field="version", date_from="fecha_inicio_vigencia", date_to="fecha_fin_vigencia",
            natural_keys=["id_producto"], unknown_key_value=0,
            attributes_scd1=["nombre"], attributes_scd2=["categoria"],
        ),
        DimContract(
            table="dim_tiempo", scd_type=1, technical_key="sk_tiempo",
            version_field="", date_from="", date_to="",
            natural_keys=["fecha"], unknown_key_value=0,
        ),
    ]


def _make_llm():
    _load_env()
    from app.core.config import Settings
    from app.models.llm_factory import build_llm
    return build_llm(Settings(), role="main")


@pytest.mark.integration
def test_h9_h10_live_generation_no_e3_e14_keyvacia():
    from app.schemas.etl_schemas import ETLFromInferenceRequest
    from app.services.etl_generator import generate_etl_from_inference
    from app.services.ktr_builder.error_catalog_checks import (
        v11_monetario_sin_bignumber,
        v13_lookup_key_incompleta,
    )

    req = ETLFromInferenceRequest(
        descripcionObjetivo=DESCRIPCION_OBJETIVO,
        origenTables=_origen_tables(),
        stg_definition=STG_DDL,
        dwh_model=DWH_DDL,
        reglasNegocio=REGLAS_NEGOCIO,
        dim_contracts=_dim_contracts(),
    )

    llm = _make_llm()
    resp = _run(generate_etl_from_inference(req, llm))

    assert resp.etapas, "el modelo no devolvio ninguna etapa"

    # Aplana TODO .ktr fisico generado (ambas etapas, incluida fragmentacion F3
    # si compute_cut() partio alguna en N archivos) -- v11/v13 corren sobre el
    # XML YA serializado, no sobre el JSON crudo del modelo.
    ktr_files: list[tuple[str, str]] = []
    for etapa in resp.etapas:
        if etapa.tipo == "ktr":
            ktr_files.append((etapa.archivo.filename, etapa.archivo.xml))
        else:
            ktr_files.extend((a.filename, a.xml) for a in etapa.archivos)

    assert ktr_files, "no se genero ningun archivo .ktr"

    all_findings: list[str] = []
    # column_name (tabla fact_venta) -> (stream_field, step_name)
    fact_venta_value_maps: dict[str, tuple[str, str]] = {}

    for filename, xml in ktr_files:
        root = ET.fromstring(xml)
        findings = [
            *v11_monetario_sin_bignumber(root),
            *v13_lookup_key_incompleta(root),
        ]
        all_findings.extend(
            f"[{filename}] {f.rule}/{f.error} step={f.step!r} table={f.table!r}: {f.message}"
            for f in findings
        )

        for step in root.findall("step"):
            step_type = step.findtext("type", "")
            step_name = step.findtext("name", "")
            lookup = step.find("lookup")
            table = step.findtext("table", "")
            if not table and lookup is not None:
                table = lookup.findtext("table", "")
            if table != "fact_venta":
                continue

            if step_type in ("InsertUpdate", "Update") and lookup is not None:
                for value in lookup.findall("value"):
                    fact_venta_value_maps[value.findtext("name", "")] = (
                        value.findtext("rename", ""), step_name,
                    )
            elif step_type == "TableOutput":
                for field in step.findall("./fields/field"):
                    fact_venta_value_maps[field.findtext("column_name", "")] = (
                        field.findtext("stream_name", ""), step_name,
                    )

    # Junta TODOS los problemas antes de fallar (no cortar en el primer assert) --
    # una corrida real cuesta API, mejor un solo reporte completo que N corridas.
    problems: list[str] = []
    if all_findings:
        problems.append(
            "V11 (E14 monetario sin BigNumber) / V13 (key vacia en lookup):\n  "
            + "\n  ".join(all_findings)
        )

    # E3: sk_producto -> fk_producto y sk_tiempo -> fk_tiempo, sin invertir.
    if "fk_producto" not in fact_venta_value_maps:
        problems.append(f"fk_producto no aparece en ningun loader de fact_venta -- steps vistos: {fact_venta_value_maps}")
    if "fk_tiempo" not in fact_venta_value_maps:
        problems.append(f"fk_tiempo no aparece en ningun loader de fact_venta -- steps vistos: {fact_venta_value_maps}")
    if "fk_producto" in fact_venta_value_maps and "fk_tiempo" in fact_venta_value_maps:
        stream_for_producto, step_p = fact_venta_value_maps["fk_producto"]
        stream_for_tiempo, step_t = fact_venta_value_maps["fk_tiempo"]
        if "tiempo" in stream_for_producto.lower():
            problems.append(f"E3 mapeo invertido: fk_producto <- '{stream_for_producto}' en step {step_p!r}")
        if "producto" in stream_for_tiempo.lower():
            problems.append(f"E3 mapeo invertido: fk_tiempo <- '{stream_for_tiempo}' en step {step_t!r}")

    # E1: SelectValues con SOLO cast (cantidad VARCHAR -> INTEGER), sin select/remove.
    # SelectValuesMeta.getXML() (ver transform.py::_step_SelectValues): dentro de
    # <fields>, select va como <field>, remove como <remove>, cast como <meta>.
    e1_found = False
    for _, xml in ktr_files:
        root = ET.fromstring(xml)
        for step in root.findall("step"):
            if step.findtext("type", "") != "SelectValues":
                continue
            fields = step.find("fields")
            if fields is None:
                continue
            metas = fields.findall("meta")
            has_only_cast = bool(metas) and not fields.findall("field") and not fields.findall("remove")
            if has_only_cast and any((m.findtext("name") or "").lower() == "cantidad" for m in metas):
                e1_found = True

    print(f"\n[E1] SelectValues solo-cast sobre 'cantidad' ejercitado: {e1_found}")

    # E2: dim_producto SCD2 ejercitada -- DimensionLookup (no degradado a
    # CombinationLookup) con technical_key/date_from/date_to configurados.
    e2_found = False
    for _, xml in ktr_files:
        root = ET.fromstring(xml)
        for step in root.findall("step"):
            if step.findtext("type", "") != "DimensionLookup":
                continue
            if step.findtext("table", "") == "dim_producto":
                e2_found = True

    print(f"[E2] dim_producto SCD2 ejercitada via DimensionLookup: {e2_found}")

    print(f"\n[resumen] archivos generados: {[f for f, _ in ktr_files]}")
    for filename, xml in ktr_files:
        root = ET.fromstring(xml)
        steps_desc = [(s.findtext('name'), s.findtext('type')) for s in root.findall('step')]
        print(f"[resumen] {filename} steps: {steps_desc}")
    print(f"[resumen] validaciones del backend: {[(v.tipo, v.campo, v.mensaje) for v in resp.validaciones]}")
    print(f"[resumen] advertencias_buenas_practicas: {resp.advertencias_buenas_practicas}")

    assert not problems, "Problemas encontrados:\n\n" + "\n\n".join(problems)
