"""
NUEVA-2 (docs/refactor/plan-reparacion-etl.md, sección 3) — tests que generan,
no consumen, el artefacto: arman un `ktr_data` mínimo y parsean el XML real
que produce `build_ktr()`, en vez de comparar contra un `.ktr` capturado sin
JSON de entrada (golden_run_base_01, ver OBJECIONES del plan).

Cubre los ítems 1 (vocabulario por modo de DimensionLookup, D-1) y 2
(ConcatFields anidado) del plan. El ítem 3 completo también agrega casos para
Formula/BigNumber y CHECK de rango (ítem 8) — fuera de esta tanda, no
incluidos acá.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

import pytest

from app.domain.scd import ATTRIBUTE_UPDATE_TYPE_CODES, VALUE_META_TYPE_NAMES
from app.services.ktr_builder import build_ktr
from app.services.ktr_builder.common import KtrBuilderError
from app.services.ktr_builder.dimension_step_policy import enforce_dimension_step_policy
from app.services.ktr_builder.validators import ValidationContext
from app.services.ktr_builder.validators.dimension_lookup_fields import check_dimension_lookup_fields
from app.services.ktr_builder.step_types import STEP_TYPE_ALIASES


class _FakeDimContract:
    def __init__(self, table: str, scd_type: int, *, attributes_scd1: list[str] | None = None):
        self.table = table
        self.scd_type = scd_type
        self.technical_key = "sk_producto"
        self.version_field = "version"
        self.date_from = "fecha_inicio"
        self.date_to = "fecha_fin"
        self.attributes_scd1 = attributes_scd1 or []
        self.attributes_scd2 = []


def _minimal_ktr(steps: list, hops: list) -> dict:
    return {
        "name": "Test_ETL",
        "description": "",
        "connections": [{"name": "conn_dwh", "type": "POSTGRESQL"}],
        "steps": steps,
        "hops": hops,
    }


def _find_step(xml: str, name: str) -> ET.Element:
    root = ET.fromstring(xml)
    for step in root.findall("step"):
        if step.findtext("name") == name:
            return step
    raise AssertionError(f"step '{name}' no encontrado en el XML")


def _mixed_ktr_data() -> dict:
    return _minimal_ktr(
        steps=[
            {
                "name": "Leer Staging Productos", "type": "TableInput",
                "config": {"connection": "conn_dwh", "sql": "SELECT id_producto, nombre, canal FROM stg_productos"},
            },
            {
                "name": "Cargar Dim Producto", "type": "DimensionLookup",
                "config": {
                    "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                    "keys": [{"stream": "id_producto", "lookup": "id_producto"}],
                    "date_from": "fecha_inicio", "date_to": "fecha_fin",
                    "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": "Update"}],
                },
            },
            {
                "name": "Lookup Dim Producto", "type": "DimensionLookup",
                "config": {
                    "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                    "keys": [{"stream": "id_producto", "lookup": "id_producto"}],
                    "update": "N",
                    "date_from": "fecha_inicio", "date_to": "fecha_fin",
                    # Caso legítimo de P3-1 (getFields() 776-803): en modo N,
                    # 'fields' devuelve columnas adicionales del lookup, no un
                    # residuo — vocabulario N-mode, no Insert/Update.
                    "fields": [{"stream_field": "canal", "table_field": "canal", "type": "String"}],
                },
            },
            {
                "name": "Generar BK Producto", "type": "ConcatFields",
                "config": {
                    "separator": "-", "target_field": "bk_producto", "target_field_length": 255,
                    "fields": [{"name": "id_producto"}, {"name": "nombre"}],
                },
            },
        ],
        hops=[
            {"from": "Leer Staging Productos", "to": "Cargar Dim Producto", "enabled": True},
            {"from": "Cargar Dim Producto", "to": "Lookup Dim Producto", "enabled": True},
            {"from": "Lookup Dim Producto", "to": "Generar BK Producto", "enabled": True},
        ],
    )


def test_dimension_lookup_loader_emits_y_mode_vocabulary():
    xml, _, _ = build_ktr(_mixed_ktr_data())
    step = _find_step(xml, "Cargar Dim Producto")
    assert step.findtext("update") == "Y"
    fields = step.findall("fields/field")
    assert len(fields) == 1
    assert fields[0].findtext("update") in ATTRIBUTE_UPDATE_TYPE_CODES
    assert fields[0].find("type") is None


def test_dimension_lookup_fact_lookup_emits_n_mode_vocabulary():
    xml, _, _ = build_ktr(_mixed_ktr_data())
    step = _find_step(xml, "Lookup Dim Producto")
    assert step.findtext("update") == "N"
    fields = step.findall("fields/field")
    assert len(fields) == 1
    assert fields[0].findtext("update") in VALUE_META_TYPE_NAMES
    assert fields[0].findtext("update") not in ATTRIBUTE_UPDATE_TYPE_CODES
    assert fields[0].find("type") is None


def test_concat_fields_emits_nested_concatfields_block():
    xml, _, _ = build_ktr(_mixed_ktr_data())
    step = _find_step(xml, "Generar BK Producto")
    assert step.find("extra_field") is None
    assert step.find("remove_selected_fields") is None
    concat_el = step.find("ConcatFields")
    assert concat_el is not None
    assert concat_el.findtext("targetFieldName") == "bk_producto"
    assert concat_el.findtext("targetFieldLength") == "255"
    assert concat_el.findtext("removeSelectedFields") == "N"


def test_cross_vocabulary_dimension_lookup_raises_and_validator_flags_error():
    """REV3: modo N + type='Insert' (vocabulario Y-mode) — el emisor no debe
    dejarlo pasar (KtrBuilderError), y check_dimension_lookup_fields() debe
    reportarlo por separado (severity='error'), los dos gates cubiertos."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Lookup Dim Producto", "type": "DimensionLookup",
                "config": {
                    "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                    "keys": [{"stream": "id_producto", "lookup": "id_producto"}],
                    "update": "N",
                    "date_from": "fecha_inicio", "date_to": "fecha_fin",
                    "fields": [{"stream_field": "canal", "table_field": "canal", "type": "Insert"}],
                },
            },
        ],
        hops=[],
    )

    with pytest.raises(KtrBuilderError):
        build_ktr(ktr_data)

    ctx = ValidationContext(ktr_data, STEP_TYPE_ALIASES, frozenset())
    findings = check_dimension_lookup_fields(ctx)
    assert any(f.severity == "error" for f in findings)


def test_policy_reclassified_fact_lookup_does_not_emit_crossed_vocabulary():
    """D57 — reproducción exacta del crash de la corrida post-C: un step
    'Lookup Dim Producto' llega del LLM como DimensionLookup update='Y' con
    `fields` en vocabulario Y (parece loader). La topología (alimenta un
    InsertUpdate sobre 'fact_venta', tabla distinta de 'dim_producto') lo
    reclasifica fact_lookup vía enforce_dimension_step_policy — antes de
    D57 el update pasaba a 'N' sin limpiar `fields`, dejando vocabulario Y
    cruzado en modo N; build_ktr() debía entonces levantar KtrBuilderError
    en vez de emitir. Con D57, la policy limpia `fields` y build_ktr() no
    debe levantar nada.

    D58: se agrega 'Cargar Dim Producto' (loader dedicado, rama muerta)
    para que haya 2 steps candidatos sobre dim_producto — con 1 solo
    candidato, D58 resuelve 'loader' sin BFS y este test dejaría de
    ejercitar la reclasificación fact_lookup que D57 vino a arreglar (ver
    test_single_step_per_table_reproduction_d58 más abajo para el caso de
    1 solo candidato)."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Cargar Dim Producto", "type": "DimensionLookup",
                "config": {
                    "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                    "keys": [{"stream": "id_producto", "lookup": "id_producto"}],
                    "update": "Y",
                    "date_from": "fecha_inicio", "date_to": "fecha_fin",
                },
            },
            {
                "name": "Lookup Dim Producto", "type": "DimensionLookup",
                "config": {
                    "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                    "keys": [{"stream": "id_producto", "lookup": "id_producto"}],
                    "update": "Y",
                    "date_from": "fecha_inicio", "date_to": "fecha_fin",
                    "fields": [{"stream_field": "nombre", "table_field": "nombre", "type": "Update"}],
                },
            },
            {
                "name": "Cargar Fact Venta", "type": "InsertUpdate",
                "config": {"table": "fact_venta", "connection": "conn_dwh"},
            },
        ],
        hops=[
            {"from": "Lookup Dim Producto", "to": "Cargar Fact Venta", "enabled": True},
        ],
    )
    contracts = [_FakeDimContract("dim_producto", 2)]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    lookup_step = next(s for s in ktr_data["steps"] if s["name"] == "Lookup Dim Producto")
    assert lookup_step["config"]["update"] == "N"
    assert lookup_step["config"]["fields"] == []
    assert any(r.get("repaired") is True for r in results)

    xml, _, _ = build_ktr(ktr_data)  # no debe levantar KtrBuilderError
    step = _find_step(xml, "Lookup Dim Producto")
    assert step.findtext("update") == "N"
    assert step.findall("fields/field") == []


def test_single_step_per_table_reproduction_d58():
    """D58 — reproducción de la corrida real (etl-llm-raw-test-01_sonnet_
    fase4.json, ktr_2): ÚNICO DimensionLookup sobre dim_producto ('Cargar
    dim_producto'), llegado del LLM con update='N' y `fields` en vocabulario
    Y (contradice su propia narración: "update=Y y todos los atributos en
    modo Update"). Alimenta, vía hop, un InsertUpdate sobre 'fact_inventario'
    (tabla distinta) — antes de D58, role_of_dimension_step clasificaba esto
    'fact_lookup' pese a ser el único candidato para dim_producto (sin
    ambigüedad posible: si no es el loader, nadie más carga la dimensión) y
    'already_readonly' lo daba por bueno sin mirar 'fields' — el vocabulario
    cruzado llegaba intacto a build_ktr(), que rechazaba con KtrBuilderError
    (el crash reportado). Con D58: 1 solo candidato ⇒ role='loader' sin BFS,
    cae en el branch H51 (ya existente) — se corrige a update=Y y se
    resintetiza 'fields'; build_ktr() no debe levantar nada."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Cargar dim_producto", "type": "DimensionLookup",
                "config": {
                    "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                    "update": "N",
                    "keys": [{"stream_field": "cod_producto", "table_field": "id_producto_origen"}],
                    "fields": [
                        {"stream_field": "nombre_producto", "table_field": "nombre_producto", "type": "Update"},
                        {"stream_field": "precio_unitario", "table_field": "precio_unitario", "type": "Update"},
                    ],
                    "date_from": "fecha_inicio", "date_to": "fecha_fin", "version_field": "version",
                },
            },
            {
                "name": "Cargar fact_inventario", "type": "InsertUpdate",
                "config": {"table": "fact_inventario", "connection": "conn_dwh"},
            },
        ],
        hops=[
            {"from": "Cargar dim_producto", "to": "Cargar fact_inventario", "enabled": True},
        ],
    )
    contracts = [_FakeDimContract("dim_producto", 1, attributes_scd1=["nombre_producto", "precio_unitario"])]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step_cfg = ktr_data["steps"][0]["config"]
    assert step_cfg["update"] == "Y"
    assert not any(r["tipo"] == "error" for r in results)

    xml, _, _ = build_ktr(ktr_data)  # no debe levantar KtrBuilderError
    step = _find_step(xml, "Cargar dim_producto")
    assert step.findtext("update") == "Y"
    for field in step.findall("fields/field"):
        assert field.findtext("update") in ATTRIBUTE_UPDATE_TYPE_CODES


def test_orphan_lookup_single_candidate_without_contract_attributes_is_not_forced_to_loader():
    """D58 (segunda vuelta) — el riesgo dejado anotado en la primera versión
    de D58: 1 solo step candidato para una tabla declarada en dim_contracts
    NO prueba por sí solo que sea el loader. Acá el step es un lookup
    huérfano real: solo trae 'return_field'/'keys', sin ningún atributo de
    negocio de la dimensión en 'fields' (el contrato declara nombre_producto/
    precio_unitario, ninguno presente) — señal de que el loader real falta,
    no de que este step deba forzarse a escribir. No debe forzarse
    update=Y; debe reportarse error, y build_ktr() no debe ni intentar
    emitir un loader espurio (el step queda tal cual, update=N original,
    sin 'fields' — build_ktr() no falla porque nunca hay vocabulario
    cruzado en este caso, pero la corrección peligrosa -- convertirlo en
    escritor -- no debe ocurrir)."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Lookup Huerfano Producto", "type": "DimensionLookup",
                "config": {
                    "table": "dim_producto", "connection": "conn_dwh", "return_field": "sk_producto",
                    "update": "N",
                    "keys": [{"stream_field": "cod_producto", "table_field": "id_producto_origen"}],
                    "date_from": "fecha_inicio", "date_to": "fecha_fin", "version_field": "version",
                },
            },
            {
                "name": "Cargar fact_inventario", "type": "InsertUpdate",
                "config": {"table": "fact_inventario", "connection": "conn_dwh"},
            },
        ],
        hops=[
            {"from": "Lookup Huerfano Producto", "to": "Cargar fact_inventario", "enabled": True},
        ],
    )
    contracts = [_FakeDimContract("dim_producto", 1, attributes_scd1=["nombre_producto", "precio_unitario"])]

    results = enforce_dimension_step_policy(ktr_data, contracts, STEP_TYPE_ALIASES, [])

    step_cfg = ktr_data["steps"][0]["config"]
    assert step_cfg["update"] == "N"  # NO forzado a Y — no se demostró que sea el loader
    assert any(
        r["tipo"] == "error" and "loader faltante" in r["mensaje"] and r["campo"] == "dim_producto"
        for r in results
    )

    xml, _, _ = build_ktr(ktr_data)  # no se emite un loader espurio; tampoco crashea
    step = _find_step(xml, "Lookup Huerfano Producto")
    assert step.findtext("update") == "N"


def test_string_operations_emits_literal_kettle_codes_not_numeric_indices():
    """E-04 (docs/refactor/investigacion-tags-validos-por-step.md § A.3) --
    StringOperationsMeta.readData() lee trim_type/lower_upper como los
    literales 'none/left/right/both' y 'none/lower/upper', no como índices
    ('0'..'3'). Con índices el step nunca hacía nada, sin importar el cfg."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Normalizar Nombre", "type": "StringOperations",
                "config": {
                    "fields": [
                        {"name": "nombre", "rename": "nombre", "trim_type": "both", "case": "upper"},
                        {"name": "categoria", "rename": "categoria", "case": "title"},
                    ],
                },
            },
        ],
        hops=[],
    )
    xml, _, _ = build_ktr(ktr_data)
    fields = _find_step(xml, "Normalizar Nombre").findall("fields/field")
    assert fields[0].findtext("trim_type") == "both"
    assert fields[0].findtext("lower_upper") == "upper"
    assert fields[0].findtext("init_cap") == "N"
    # 'title' no es un código real de lower_upper -- se resuelve vía init_cap
    assert fields[1].findtext("lower_upper") == "none"
    assert fields[1].findtext("init_cap") == "Y"


def test_unique_emits_case_insensitive_tag_with_correct_polarity():
    """E-05 (investigacion-tags-validos-por-step.md § A.5) --
    UniqueRowsMeta.readData() lee 'case_insensitive' (ausente = siempre true).
    El emisor escribía 'case_sensitive', tag inexistente, con la polaridad
    invertida: deduplicaba filas que solo difieren en mayúsculas siempre."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Filas Unicas", "type": "Unique",
                "config": {"fields": [{"name": "codigo", "case_sensitive": True}, "nombre"]},
            },
        ],
        hops=[],
    )
    xml, _, _ = build_ktr(ktr_data)
    step = _find_step(xml, "Filas Unicas")
    assert step.find("fields/field/case_sensitive") is None
    fields = step.findall("fields/field")
    assert fields[0].findtext("case_insensitive") == "N"
    assert fields[1].findtext("case_insensitive") == "N"


def test_excel_input_emits_spreadsheet_type_by_extension():
    """E-06 (investigacion-tags-validos-por-step.md § A.6) --
    ExcelInputMeta.readData() cae a SpreadSheetType.JXL (motor legado, no lee
    .xlsx) cuando 'spreadsheet_type' está ausente o no matchea el enum real
    (JXL/POI/SAX_POI/ODS). El emisor nunca lo escribía."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Leer Ventas Xlsx", "type": "ExcelInput",
                "config": {"filename": "ventas.xlsx", "fields": [{"name": "id"}]},
            },
            {
                "name": "Leer Ventas Xls", "type": "ExcelInput",
                "config": {"filename": "ventas.xls", "fields": [{"name": "id"}]},
            },
        ],
        hops=[],
    )
    xml, _, _ = build_ktr(ktr_data)
    assert _find_step(xml, "Leer Ventas Xlsx").findtext("spreadsheet_type") == "POI"
    assert _find_step(xml, "Leer Ventas Xls").findtext("spreadsheet_type") == "JXL"


def test_json_input_emits_include_nulls_explicit():
    """E-07 (investigacion-tags-validos-por-step.md § A.7) --
    JsonInputMeta.getincludeNulls() cae al kettle.properties del entorno
    (KETTLE_JSON_INPUT_INCLUDE_NULLS) cuando el tag está ausente -- el mismo
    .ktr se comportaba distinto según la máquina que lo ejecutara."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Leer Pedidos Json", "type": "JsonInput",
                "config": {"filename": "pedidos.json", "fields": [{"name": "id", "path": "$.id"}]},
            },
            {
                "name": "Leer Pedidos Json Con Nulls", "type": "JsonInput",
                "config": {
                    "filename": "pedidos.json", "include_nulls": True,
                    "fields": [{"name": "id", "path": "$.id"}],
                },
            },
        ],
        hops=[],
    )
    xml, _, _ = build_ktr(ktr_data)
    assert _find_step(xml, "Leer Pedidos Json").findtext("includeNulls") == "N"
    assert _find_step(xml, "Leer Pedidos Json Con Nulls").findtext("includeNulls") == "Y"


def test_text_file_output_emits_create_parent_folder_at_step_level():
    """E-08 (investigacion-tags-validos-por-step.md § A.8) --
    TextFileOutputMeta.readData() lee 'create_parent_folder' como hijo
    directo de <step>, no anidado en <file>. El emisor lo anidaba -- inocuo
    hoy solo porque el default ante ausencia ('Y') coincide con lo emitido."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Escribir Log", "type": "TextFileOutput",
                "config": {"filename": "log.txt", "fields": [{"name": "mensaje"}]},
            },
        ],
        hops=[],
    )
    xml, _, _ = build_ktr(ktr_data)
    step = _find_step(xml, "Escribir Log")
    assert step.findtext("create_parent_folder") == "Y"
    file_el = step.find("file")
    assert file_el.find("create_parent_folder") is None


def test_combination_lookup_emits_return_block_with_named_surrogate_key():
    """E-09 (investigacion-tags-validos-por-step.md § A.1) --
    CombinationLookupMeta.readData() 404-450 solo conoce la surrogate key vía
    <fields><return><name>; el emisor anterior escribía 'returnfield' plano
    (sin lector) y nunca el bloque <return> -- technicalKeyField quedaba null
    y useAutoinc se forzaba a true sin importar el cfg."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Cargar Dim Canal", "type": "CombinationLookup",
                "config": {
                    "schema": "public", "table": "dim_canal", "connection": "conn_dwh",
                    "return_field": "sk_canal",
                    "keys": [{"stream": "canal", "lookup": "canal"}],
                },
            },
        ],
        hops=[],
    )
    xml, _, _ = build_ktr(ktr_data)
    step = _find_step(xml, "Cargar Dim Canal")
    assert step.find("useautoinc") is None
    assert step.find("returnfield") is None
    ret = step.find("fields/return")
    assert ret is not None
    assert ret.findtext("name") == "sk_canal"
    assert ret.findtext("creation_method") == "autoinc"
    assert ret.findtext("use_autoinc") == "Y"
    key = step.find("fields/key")
    assert key.findtext("name") == "canal"
    assert step.findtext("commit") == "100"


def test_data_validator_emits_real_field_as_name_and_label_as_validation_name():
    """E-10 (investigacion-tags-validos-por-step.md § A.2) --
    ValidatorMeta/Validation(Node) lee 'name' como el CAMPO REAL del stream a
    validar y 'validation_name' como la etiqueta de la regla (fallback a
    'name' si ausente). El emisor anterior invertía esto -- la validación
    quedaba rota para toda regla donde etiqueta != campo, el caso esperado."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Validar Precio", "type": "DataValidator",
                "config": {
                    "validations": [
                        {"name": "precio_no_negativo", "field": "precio", "min_value": 0},
                    ],
                },
            },
        ],
        hops=[],
    )
    xml, _, _ = build_ktr(ktr_data)
    val = _find_step(xml, "Validar Precio").find("validator_field")
    assert val.findtext("name") == "precio"
    assert val.findtext("validation_name") == "precio_no_negativo"
    assert val.find("fieldname") is None


def test_split_field_to_rows_emits_registered_plugin_id():
    """E-11 (investigacion-tags-validos-por-step.md § A.4) --
    kettle-steps.xml solo registra id="SplitFieldToRows3"; "SplitFieldToRows"
    (sin el 3, al que resuelve el alias 'Split fields' de step_types.py) no es
    un plugin id real -- Spoon marca el step "missing" y la transformación no
    corre."""
    ktr_data = _minimal_ktr(
        steps=[
            {
                "name": "Separar Tags", "type": "SplitFieldToRows",
                "config": {"split_field": "tags", "delimiter": ",", "new_field": "tag"},
            },
        ],
        hops=[],
    )
    xml, _, _ = build_ktr(ktr_data)
    step = _find_step(xml, "Separar Tags")
    assert step.findtext("type") == "SplitFieldToRows3"
