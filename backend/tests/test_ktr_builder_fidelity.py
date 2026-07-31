"""
Fidelidad de tipo/config del ktr_builder y cierre de vacíos mecánicos.

Casos reproducidos como test, tal como se documentaron comparando el JSON
ktr.steps[].config del LLM contra el .ktr emitido:

  1. SystemInfo ya no se degrada a Dummy (antes: type no registrado -> Dummy).
  2. SortRows respeta 'ascending': 'N' declarado (antes: string 'N' truthy -> 'Y').
  3. TableOutput respeta ignore_errors/truncate/specify_fields del config (antes:
     ignore_errors hardcodeado a 'N', truncate con default propio).
  4. Un type sin emisor registrado aborta el build con KtrBuilderError en vez de
     emitir Dummy en silencio.
  5. La validación de resolución de campos detecta un campo consumido que
     ningún step aguas arriba produce (el caso stg_fecha_carga de KTR_2).
"""
from xml.etree import ElementTree as ET

import pytest

from app.services.ktr_builder import build_ktr
from app.services.ktr_builder.common import KtrBuilderError


def _minimal_ktr(steps: list, hops: list) -> dict:
    return {
        "name": "Test_ETL",
        "description": "",
        "connections": [{"name": "conn_origen", "type": "POSTGRESQL"}],
        "steps": steps,
        "hops": hops,
    }


def _find_step(xml: str, name: str) -> ET.Element:
    root = ET.fromstring(xml)
    for step in root.findall("step"):
        if step.findtext("name") == name:
            return step
    raise AssertionError(f"step '{name}' no encontrado en el XML")


def test_systeminfo_not_degraded_to_dummy():
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "Obtener Fecha de Carga",
                "type": "SystemInfo",
                "config": {"fields": [{"name": "stg_fecha_carga", "type": "system date (fixed)"}]},
            },
            {
                "name": "Cargar Staging",
                "type": "TableOutput",
                "config": {
                    "table": "stg_tabla",
                    "connection": "conn_origen",
                    "fields": [{"column_name": "stg_fecha_carga", "stream_name": "stg_fecha_carga"}],
                },
            },
        ],
        hops=[{"from": "Obtener Fecha de Carga", "to": "Cargar Staging"}],
    )
    xml, _, _ = build_ktr(ktr)
    step = _find_step(xml, "Obtener Fecha de Carga")
    # XML emite "SystemInfo" (ID real del plugin Kettle), no "GetSystemInfo"
    # (nombre canónico interno/UI) — ver _XML_TYPE_OVERRIDES en build.py.
    assert step.findtext("type") == "SystemInfo"
    field = step.find("fields/field")
    assert field.findtext("name") == "stg_fecha_carga"
    assert field.findtext("type") == "system date (fixed)"


def test_sortrows_respects_ascending_n():
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT fecha_alta FROM stg_clientes"}},
            {
                "name": "Ordenar Clientes",
                "type": "SortRows",
                "config": {"fields": [{"name": "fecha_alta", "ascending": "N"}]},
            },
        ],
        hops=[{"from": "In", "to": "Ordenar Clientes"}],
    )
    xml, _, _ = build_ktr(ktr)
    step = _find_step(xml, "Ordenar Clientes")
    assert step.find("fields/field/ascending").text == "N"


def test_tableoutput_respects_ignore_errors_and_truncate():
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT id FROM stg_ventas"}},
            {
                "name": "Cargar Staging Ventas",
                "type": "TableOutput",
                "config": {
                    "table": "stg_ventas",
                    "connection": "conn_origen",
                    "truncate": "N",
                    "ignore_errors": "Y",
                    "fields": [{"column_name": "id", "stream_name": "id"}],
                },
            },
        ],
        hops=[{"from": "In", "to": "Cargar Staging Ventas"}],
    )
    xml, _, _ = build_ktr(ktr)
    step = _find_step(xml, "Cargar Staging Ventas")
    assert step.findtext("truncate") == "N"
    assert step.findtext("ignore_errors") == "Y"
    assert step.findtext("specify_fields") == "Y"
    # ignore_errors=Y es incompatible con batch en PDI -> use_batch forzado a N
    assert step.findtext("use_batch") == "N"


def test_unsupported_step_type_aborts_instead_of_dummy():
    ktr = _minimal_ktr(
        steps=[{"name": "Raro", "type": "TotallyMadeUpStepType", "config": {}}],
        hops=[],
    )
    with pytest.raises(KtrBuilderError, match="Tipo de step no soportado"):
        build_ktr(ktr)


def test_explicit_dummy_still_allowed():
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT id FROM stg_x"}},
            {"name": "Placeholder", "type": "Dummy", "config": {}},
        ],
        hops=[{"from": "In", "to": "Placeholder"}],
    )
    xml, _, _ = build_ktr(ktr)
    assert _find_step(xml, "Placeholder").findtext("type") == "Dummy"


def test_field_resolution_catches_missing_upstream_field():
    # DimensionLookup usa stg_fecha_carga como fecha SCD, pero el TableInput
    # que lo alimenta no la selecciona (mismo hueco visto en KTR_2).
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "Leer Staging Productos",
                "type": "TableInput",
                "config": {"sql": "SELECT id, nombre FROM stg_productos"},
            },
            {
                "name": "Lookup SK Producto",
                "type": "DimensionLookup",
                "config": {
                    "table": "dim_producto",
                    "connection": "conn_origen",
                    "return_field": "sk_producto",
                    "date_field": "stg_fecha_carga",
                    "keys": [{"stream": "id", "lookup": "id"}],
                },
            },
        ],
        hops=[{"from": "Leer Staging Productos", "to": "Lookup SK Producto"}],
    )
    _, _, warnings = build_ktr(ktr)
    assert any("stg_fecha_carga" in w for w in warnings)


def test_field_resolution_passes_when_field_present():
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "Leer Staging Productos",
                "type": "TableInput",
                "config": {"sql": "SELECT id, nombre, stg_fecha_carga FROM stg_productos"},
            },
            {
                "name": "Lookup SK Producto",
                "type": "DimensionLookup",
                "config": {
                    "table": "dim_producto",
                    "connection": "conn_origen",
                    "return_field": "sk_producto",
                    "date_field": "stg_fecha_carga",
                    "keys": [{"stream": "id", "lookup": "id"}],
                },
            },
        ],
        hops=[{"from": "Leer Staging Productos", "to": "Lookup SK Producto"}],
    )
    xml, _, _ = build_ktr(ktr)
    assert _find_step(xml, "Lookup SK Producto").findtext("type") == "DimensionLookup"


def test_numberrange_output_field_not_false_positive():
    # 'categoria_cliente' es agregado por NumberRange (config.output_field), no
    # está en el TableInput de origen — antes se contaba como campo faltante.
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "Leer Staging Clientes",
                "type": "TableInput",
                "config": {"sql": "SELECT id_cliente, monto_total FROM stg_clientes"},
            },
            {
                "name": "Clasificar Cliente",
                "type": "NumberRange",
                "config": {
                    "input_field": "monto_total",
                    "output_field": "categoria_cliente",
                    "ranges": [{"lower": 0, "upper": 1000, "value": "bajo"}],
                },
            },
            {
                "name": "Cargar Staging",
                "type": "TableOutput",
                "config": {
                    "table": "stg_clientes_clasificados",
                    "connection": "conn_origen",
                    "fields": [{"column_name": "categoria_cliente", "stream_name": "categoria_cliente"}],
                },
            },
        ],
        hops=[
            {"from": "Leer Staging Clientes", "to": "Clasificar Cliente"},
            {"from": "Clasificar Cliente", "to": "Cargar Staging"},
        ],
    )
    xml, _, _ = build_ktr(ktr)
    assert _find_step(xml, "Clasificar Cliente").findtext("outputField") == "categoria_cliente"


def test_groupby_aggregate_field_not_false_positive():
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "Leer Ventas",
                "type": "TableInput",
                "config": {"sql": "SELECT id_cliente, importe FROM stg_ventas"},
            },
            {
                "name": "Totalizar por Cliente",
                "type": "MemoryGroupBy",
                "config": {
                    "group_fields": ["id_cliente"],
                    "aggregates": [{"name": "total_importe", "field": "importe", "type": "SUM"}],
                },
            },
            {
                "name": "Cargar Staging",
                "type": "TableOutput",
                "config": {
                    "table": "stg_totales",
                    "connection": "conn_origen",
                    "fields": [
                        {"column_name": "id_cliente", "stream_name": "id_cliente"},
                        {"column_name": "total_importe", "stream_name": "total_importe"},
                    ],
                },
            },
        ],
        hops=[
            {"from": "Leer Ventas", "to": "Totalizar por Cliente"},
            {"from": "Totalizar por Cliente", "to": "Cargar Staging"},
        ],
    )
    xml, _, _ = build_ktr(ktr)
    assert _find_step(xml, "Totalizar por Cliente").findtext("type") == "MemoryGroupBy"


def test_groupby_narrows_stream_drops_ungrouped_field():
    # importe no sobrevive a un GroupBy que no lo agrupa ni agrega -> debe fallar.
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "Leer Ventas",
                "type": "TableInput",
                "config": {"sql": "SELECT id_cliente, importe FROM stg_ventas"},
            },
            {
                "name": "Totalizar por Cliente",
                "type": "GroupBy",
                "config": {
                    "group_fields": ["id_cliente"],
                    "aggregates": [{"name": "total_importe", "field": "importe", "type": "SUM"}],
                },
            },
            {
                "name": "Cargar Staging",
                "type": "TableOutput",
                "config": {
                    "table": "stg_totales",
                    "connection": "conn_origen",
                    "fields": [{"column_name": "importe", "stream_name": "importe"}],
                },
            },
        ],
        hops=[
            {"from": "Leer Ventas", "to": "Totalizar por Cliente"},
            {"from": "Totalizar por Cliente", "to": "Cargar Staging"},
        ],
    )
    _, _, warnings = build_ktr(ktr)
    assert any("importe" in w for w in warnings)


def test_calculator_field_not_false_positive():
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT importe FROM stg_ventas"}},
            {
                "name": "Convertir a USD",
                "type": "Calculator",
                "config": {"calculations": [{"field_name": "importe_usd", "calc_type": "DIVIDE", "field_a": "importe", "field_b": "tc"}]},
            },
            {
                "name": "Cargar Staging",
                "type": "TableOutput",
                "config": {
                    "table": "stg_ventas_usd",
                    "connection": "conn_origen",
                    "fields": [{"column_name": "importe_usd", "stream_name": "importe_usd"}],
                },
            },
        ],
        hops=[
            {"from": "In", "to": "Convertir a USD"},
            {"from": "Convertir a USD", "to": "Cargar Staging"},
        ],
    )
    xml, _, _ = build_ktr(ktr)
    assert _find_step(xml, "Convertir a USD").find("calculation/field_name").text == "importe_usd"


def test_calculator_removed_from_result_excludes_field():
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT importe FROM stg_ventas"}},
            {
                "name": "Convertir a USD",
                "type": "Calculator",
                "config": {"calculations": [{"field_name": "importe_usd", "calc_type": "DIVIDE", "field_a": "importe", "field_b": "tc", "removed_from_result": "Y"}]},
            },
            {
                "name": "Cargar Staging",
                "type": "TableOutput",
                "config": {
                    "table": "stg_ventas_usd",
                    "connection": "conn_origen",
                    "fields": [{"column_name": "importe_usd", "stream_name": "importe_usd"}],
                },
            },
        ],
        hops=[
            {"from": "In", "to": "Convertir a USD"},
            {"from": "Convertir a USD", "to": "Cargar Staging"},
        ],
    )
    _, _, warnings = build_ktr(ktr)
    assert any("importe_usd" in w for w in warnings)


def test_dblookup_return_field_not_false_positive():
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT cod_cliente FROM stg_ventas"}},
            {
                "name": "Lookup SK Cliente",
                "type": "DBLookup",
                "config": {
                    "connection": "conn_dwh",
                    "table": "dim_cliente",
                    "keys": [{"stream_field": "cod_cliente", "lookup_field": "cod_cliente"}],
                    "return_fields": [{"name": "sk_cliente"}],
                },
            },
            {
                "name": "Cargar Fact",
                "type": "TableOutput",
                "config": {
                    "table": "fact_ventas",
                    "connection": "conn_dwh",
                    "fields": [{"column_name": "sk_cliente", "stream_name": "sk_cliente"}],
                },
            },
        ],
        hops=[
            {"from": "In", "to": "Lookup SK Cliente"},
            {"from": "Lookup SK Cliente", "to": "Cargar Fact"},
        ],
    )
    xml, _, _ = build_ktr(ktr)
    assert _find_step(xml, "Lookup SK Cliente").find("lookup/value/name").text == "sk_cliente"


def test_dblookup_empty_config_reports_incomplete_producer():
    # Mismo hueco visto en KTR_2: el DBLookup no declara return_fields, así que
    # el mensaje debe apuntar al productor incompleto ('Lookup SK Cliente'), no
    # solo al consumidor lejano que finalmente no encuentra el campo.
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT cod_cliente FROM stg_ventas"}},
            {
                "name": "Lookup SK Cliente",
                "type": "DBLookup",
                "config": {"connection": "conn_dwh", "table": "dim_cliente"},
            },
            {
                "name": "Cargar Fact",
                "type": "TableOutput",
                "config": {
                    "table": "fact_ventas",
                    "connection": "conn_dwh",
                    "fields": [{"column_name": "sk_cliente", "stream_name": "sk_cliente"}],
                },
            },
        ],
        hops=[
            {"from": "In", "to": "Lookup SK Cliente"},
            {"from": "Lookup SK Cliente", "to": "Cargar Fact"},
        ],
    )
    with pytest.raises(KtrBuilderError, match=r"'Lookup SK Cliente'.*no declara campos de retorno"):
        build_ktr(ktr)


def test_calculator_empty_calculations_aborts():
    # Caso real documentado: "Convertir a USD"/"Generar Atributos de Tiempo"
    # llegaban con config = {"calculations": []} — sin campos.formulas/fields, un
    # Calculator vacío no aporta nada al stream y todo lo que dependa de él rompe.
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT monto FROM stg_ventas"}},
            {"name": "Convertir a USD", "type": "Calculator", "config": {"calculations": []}},
        ],
        hops=[{"from": "In", "to": "Convertir a USD"}],
    )
    with pytest.raises(KtrBuilderError, match=r"'Convertir a USD'.*no declara calculations"):
        build_ktr(ktr)


def test_formula_empty_formulas_aborts():
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT monto FROM stg_ventas"}},
            {"name": "Calcular Importe Neto", "type": "Formula", "config": {"formulas": []}},
        ],
        hops=[{"from": "In", "to": "Calcular Importe Neto"}],
    )
    with pytest.raises(KtrBuilderError, match=r"'Calcular Importe Neto'.*no declara formulas"):
        build_ktr(ktr)


def test_streamlookup_empty_values_aborts():
    # keys presente (condición de cruce) pero values vacío: el lookup no trae
    # ningún campo nuevo al stream — mismo hueco visto en "Unir Clasificacion
    # Cliente" (categoria_cliente nunca llega a los consumidores aguas abajo).
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT cliente_id FROM stg_ventas"}},
            {
                "name": "Unir Clasificacion Cliente",
                "type": "StreamLookup",
                "config": {"step": "Clasificar Cliente", "keys": [{"stream": "cliente_id", "lookup": "cliente_id"}], "values": []},
            },
        ],
        hops=[{"from": "In", "to": "Unir Clasificacion Cliente"}],
    )
    with pytest.raises(KtrBuilderError, match=r"'Unir Clasificacion Cliente'.*no declara values"):
        build_ktr(ktr)


def test_tableinput_duplicate_select_column_warns():
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "Leer Staging Clientes",
                "type": "TableInput",
                "config": {"sql": "SELECT id, fecha_alta, fecha_alta FROM stg_clientes"},
            },
            {
                "name": "Cargar Staging",
                "type": "TableOutput",
                "config": {
                    "table": "stg_clientes2",
                    "connection": "conn_origen",
                    "fields": [{"column_name": "id", "stream_name": "id"}],
                },
            },
        ],
        hops=[{"from": "Leer Staging Clientes", "to": "Cargar Staging"}],
    )
    _, _, warnings = build_ktr(ktr)
    assert any("fecha_alta" in w and "repetida" in w for w in warnings)


def test_unmapped_config_key_warns():
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "In",
                "type": "TableInput",
                "config": {"sql": "SELECT id FROM stg_x"},
            },
            {
                "name": "Cargar Staging",
                "type": "TableOutput",
                "config": {
                    "table": "stg_x",
                    "connection": "conn_origen",
                    "fields": [{"column_name": "id", "stream_name": "id"}],
                    "no_existe_esta_clave": "algo",
                },
            },
        ],
        hops=[{"from": "In", "to": "Cargar Staging"}],
    )
    _, _, warnings = build_ktr(ktr)
    assert any("no_existe_esta_clave" in w for w in warnings)


# ─── StepContract registry: normalize_config() + required_keys ────────────

def test_numberrange_camelcase_alias_normalized():
    # El LLM puede devolver camelCase (inputField/outputField) en vez del
    # snake_case documentado en el prompt. normalize_config() debe resolverlo
    # ANTES de emitir y de validar — ni el emisor ni el validador deben ver
    # 'inputField' crudo, ni dar falso positivo de campo faltante.
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "Leer Staging Clientes",
                "type": "TableInput",
                "config": {"sql": "SELECT id_cliente, monto_total FROM stg_clientes"},
            },
            {
                "name": "Clasificar Cliente",
                "type": "NumberRange",
                "config": {
                    "inputField": "monto_total",
                    "outputField": "categoria_cliente",
                    "ranges": [{"lower": 0, "upper": 1000, "value": "bajo"}],
                },
            },
            {
                "name": "Cargar Staging",
                "type": "TableOutput",
                "config": {
                    "table": "stg_clientes_clasificados",
                    "connection": "conn_origen",
                    "fields": [{"column_name": "categoria_cliente", "stream_name": "categoria_cliente"}],
                },
            },
        ],
        hops=[
            {"from": "Leer Staging Clientes", "to": "Clasificar Cliente"},
            {"from": "Clasificar Cliente", "to": "Cargar Staging"},
        ],
    )
    xml, _, _ = build_ktr(ktr)
    step = _find_step(xml, "Clasificar Cliente")
    assert step.findtext("inputField") == "monto_total"
    assert step.findtext("outputField") == "categoria_cliente"


@pytest.mark.parametrize(
    "step_type,config,expected_key",
    [
        ("DBLookup", {"connection": "conn_dwh", "table": "dim_cliente"}, "return_fields"),
        ("Calculator", {}, "calculations"),
        ("StreamLookup", {"step": "In", "keys": [{"stream": "id", "lookup": "id"}]}, "values"),
    ],
)
def test_required_keys_blocks_with_step_name_in_message(step_type, config, expected_key):
    # required_keys del contrato bloquea ACÁ, en el step que quedó a medio
    # llenar — no dos capas después, como un campo faltante en un consumidor
    # lejano cuyo mensaje culpa al step equivocado.
    ktr = _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT id FROM stg_x"}},
            {"name": "Step Incompleto", "type": step_type, "config": config},
        ],
        hops=[{"from": "In", "to": "Step Incompleto"}],
    )
    with pytest.raises(KtrBuilderError, match=r"Config incompleto en 'Step Incompleto'"):
        build_ktr(ktr)


def test_no_duplicate_key_alias_tables_outside_contracts():
    # Guard contra que vuelva el drift: los alias de clave viven SOLO en
    # contracts.py. fields_validate.py no debe definir su propia tabla de
    # alias/semántica por tipo — debe leerla de STEP_CONTRACTS.
    import inspect

    from app.services.ktr_builder import fields_validate

    source = inspect.getsource(fields_validate)
    assert "STEP_CONTRACTS" in source
    assert 'canonical_type == "' not in source


@pytest.mark.parametrize("step_type", ["InsertUpdate", "Update"])
def test_insert_update_value_name_is_table_column_not_stream_field(step_type):
    # Bug real (H9/E3, docs/refactor/01-hallazgos.md): InsertUpdateMeta.getXML()/
    # readData() (pentaho-kettle, InsertUpdateMeta.java) define, dentro de
    # <lookup><value>, <name> = columna de la TABLA (updateLookup) y
    # <rename> = campo del STREAM (updateStream) -- invertido respecto de
    # <key>, donde <name> sí es el stream. Antes de este fix, output.py
    # emitía <name>=stream_field/<rename>=table_field para TODO InsertUpdate
    # y Update generado -- Kettle intentaba escribir en una "columna" con
    # nombre de campo de stream, inexistente en la tabla real.
    ktr = _minimal_ktr(
        steps=[
            {
                "name": "In", "type": "TableInput",
                "config": {"sql": "SELECT sk_producto, id_venta FROM stg_x"},
            },
            {
                "name": "Cargar Fact Venta", "type": step_type,
                "config": {
                    "table": "fact_venta", "connection": "conn_origen",
                    "keys": [{"stream_field": "id_venta", "table_field": "id_venta"}],
                    "fields": [{"stream_field": "sk_producto", "table_field": "fk_producto", "update": True}],
                },
            },
        ],
        hops=[{"from": "In", "to": "Cargar Fact Venta"}],
    )
    xml, _, _ = build_ktr(ktr)
    step = _find_step(xml, "Cargar Fact Venta")
    value = step.find("lookup").find("value")
    assert value.findtext("name") == "fk_producto", "name debe ser la columna de tabla (updateLookup)"
    assert value.findtext("rename") == "sk_producto", "rename debe ser el campo de stream (updateStream)"


def _insert_update_ktr(fields: list) -> dict:
    return _minimal_ktr(
        steps=[
            {"name": "In", "type": "TableInput", "config": {"sql": "SELECT id_venta FROM stg_x"}},
            {
                "name": "Cargar Fact Venta", "type": "InsertUpdate",
                "config": {
                    "table": "fact_venta", "connection": "conn_origen",
                    "keys": [{"stream_field": "id_venta", "table_field": "id_venta"}],
                    "fields": fields,
                },
            },
        ],
        hops=[{"from": "In", "to": "Cargar Fact Venta"}],
    )


def test_insert_update_bypassed_tag_present_and_n_with_updatable_value():
    # R-K7 (docs/refactor/03c-investigacion-vocabulario-dimension-kettle.md,
    # D51): el tag <update_bypassed> no se emitía NUNCA antes de este fix —
    # InsertUpdateMeta.readData() interpreta esa ausencia como "N".
    ktr = _insert_update_ktr([{"stream_field": "monto", "table_field": "monto", "update": True}])
    xml, _, _ = build_ktr(ktr)
    step = _find_step(xml, "Cargar Fact Venta")
    assert step.findtext("update_bypassed") == "N"


def test_insert_update_bypassed_defaults_to_y_when_no_updatable_value():
    # Sin ningún <value> en update=Y, dejar update_bypassed=N (default de
    # Kettle si el tag falta) arma un "UPDATE ... SET" vacío que revienta en
    # la primera fila (InsertUpdateMeta.prepareUpdate()) -- el emisor
    # bypassea automáticamente en este caso, sin que el LLM lo declare.
    ktr = _insert_update_ktr([{"stream_field": "monto", "table_field": "monto", "update": False}])
    xml, _, _ = build_ktr(ktr)
    step = _find_step(xml, "Cargar Fact Venta")
    assert step.findtext("update_bypassed") == "Y"


def test_insert_update_bypassed_respects_explicit_config():
    ktr = _insert_update_ktr([{"stream_field": "monto", "table_field": "monto", "update": True}])
    ktr["steps"][1]["config"]["update_bypassed"] = "Y"
    xml, _, _ = build_ktr(ktr)
    step = _find_step(xml, "Cargar Fact Venta")
    assert step.findtext("update_bypassed") == "Y"
