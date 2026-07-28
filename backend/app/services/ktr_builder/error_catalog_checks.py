"""Auditoría del catálogo E1-E14 (análisis externo de errores recurrentes en
.ktr generados) contra el XML real -- el que Spoon/Pentaho carga -- ya
serializado. NO confundir con app.services.ktr_xml_validator (validate_ktr_xml
/ KtrXmlValidationError): ese es el gate estructural genérico ya wireado en
build_ktr() (conexión GENERIC sin driver, step sin fields, hop huérfano) y
FALLA duro. Este módulo es más angosto y más lento en volverse obsoleto: cada
V-función corresponde a UN error puntual del catálogo (V4->E1, V5->E2, etc.),
devuelve list[Finding] en vez de lanzar, y no está wireado a build_ktr() --
corre standalone como diagnóstico (ver FASE 1/2/3 del trabajo que lo originó).

Cada V-función es pura: recibe el <transformation> ya parseado con
xml.etree y devuelve list[Finding], sin logging ni mutación.

Cobertura (ver contexto de la tarea para el catálogo completo E1-E14):
  V4  SelectValues sin ninguna entrada select/remove/meta               (E1)
  V5  Columnas técnicas que un DimensionLookup exige (key/date/version/
      return) existen en la tabla real (DDL provisto por el caller)     (E2)
  V6  Mapeos de InsertUpdate/Update referencian columnas reales de la
      tabla, respetando que en <key> el orden es name=campo del stream/
      field=columna, y en <value> se invierte: name=columna/rename=campo (E3)
  V7  Ningún TableOutput (INSERT plano, sin clave) carga una tabla de
      hechos (fact_*/hechos_*/hecho_*)                                  (E8)
  V8  truncate=Y en un TableOutput implica transformación transaccional
      (proxy: <info>/<unique_connections> -- ver nota en la función)    (E10)
  V11 Ningún campo con nombre de pinta monetaria (importe/precio/monto/
      etc.) queda tipado Number en vez de BigNumber, en NINGUNO de los
      steps de ktr_builder que declaran un value-type real de Kettle por
      campo (Calculator, Formula, SelectValues/meta, ScriptValueMod,
      GetVariable, RowGenerator, CsvInput, TextFileInput, ExcelInput,
      JsonInput, TextFileOutput, ExcelOutput, Constant, FieldSplitter,
      Denormaliser, RegexEval, DBLookup, StreamLookup, DataValidator --
      ver FIELD_TYPE_SOURCES; lista cerrada por auditoría de los ~45 steps
      de STEP_BUILDERS, no por catálogo E1-E14 original -- H35/H36,
      docs/refactor/01-hallazgos.md, D36 en 02-decisiones.md)         (E14)
  V13 Todo step de la familia lookup-por-clave (CombinationLookup,
      DimensionLookup, StreamLookup, DBLookup) tiene al menos un <key>
      con ambos lados no vacíos -- una key vacía/incompleta no es un
      step degradado, es un step que Spoon no puede inicializar. Fuera
      del catálogo E1-E14 original (descubierto en diagnóstico sobre
      output fresco, Fase 2) -- sin código E asignado.

Fuera de alcance acá (ver contexto): E5/E6 (fragmentación) y E2
estructural (qué tipo de step usar) -- ese último vive en
dimension_step_policy.py, ya resuelto en otra pasada.
"""
from __future__ import annotations

from dataclasses import dataclass
from xml.etree import ElementTree as ET

MONEY_FIELD_HINTS = (
    "importe", "precio", "monto", "total", "subtotal", "valor", "costo", "price", "amount",
    "impuesto", "iva", "descuento", "saldo", "comision", "recargo", "tipo_cambio", "arancel", "cuota",
)
FACT_TABLE_PREFIXES = ("fact_", "hechos_", "hecho_")


@dataclass(frozen=True)
class Finding:
    rule: str      # V4..V11
    error: str     # E1..E14 (catálogo del análisis que originó estos validadores)
    step: str
    table: str
    message: str


def parse_ktr(xml_text: str) -> ET.Element:
    return ET.fromstring(xml_text)


def _steps(root: ET.Element) -> list[ET.Element]:
    return root.findall("step")


def _text(el: ET.Element | None, tag: str, default: str = "") -> str:
    if el is None:
        return default
    child = el.find(tag)
    if child is None or child.text is None:
        return default
    return child.text


def v4_select_values_sin_entradas(root: ET.Element) -> list[Finding]:
    """Esquema real de Kettle para SelectValues: <fields> contiene <field>
    (select), <remove> y <meta> (cast) como HIJOS directos, además de
    <select_unspecified>. Si no hay ninguno de los tres, el step no
    selecciona/remueve/castea nada -- es un no-op que no debería haberse
    emitido."""
    findings = []
    for step in _steps(root):
        if _text(step, "type") != "SelectValues":
            continue
        fields = step.find("fields")
        entries = 0
        if fields is not None:
            entries = (
                len(fields.findall("field"))
                + len(fields.findall("remove"))
                + len(fields.findall("meta"))
            )
        if entries == 0:
            findings.append(Finding(
                "V4", "E1", _text(step, "name"), "",
                "SelectValues sin ninguna entrada select/remove/meta -- no hace "
                "nada, es un artefacto inválido.",
            ))
    return findings


def v5_dimension_lookup_columnas_tecnicas(
    root: ET.Element, ddl_columns: dict[str, set[str]],
) -> list[Finding]:
    """Un DimensionLookup exige que su tabla tenga las columnas de key,
    date_from/date_to y (si versiona) el campo de version -- son técnicas,
    no de negocio, y si faltan en la tabla real el step falla en runtime,
    no al guardar el .ktr.

    ddl_columns: {tabla: {columnas reales}}, provisto por el caller (DDL
    real o, en su ausencia, otra fuente de verdad confiable -- este
    validador no lee DDL por su cuenta). Tablas ausentes de ddl_columns se
    saltean silenciosamente (no hay con qué comparar)."""
    findings = []
    for step in _steps(root):
        if _text(step, "type") != "DimensionLookup":
            continue
        table = _text(step, "table")
        cols = ddl_columns.get(table)
        if cols is None:
            continue
        name = _text(step, "name")
        fields = step.find("fields")
        if fields is None:
            continue

        date = fields.find("date")
        if date is not None:
            for tag in ("from", "to"):
                col = _text(date, tag)
                if col and col not in cols:
                    findings.append(Finding(
                        "V5", "E2", name, table,
                        f"DimensionLookup exige columna técnica '{col}' (date_{tag}) "
                        f"que no existe en '{table}'.",
                    ))

        ret = fields.find("return")
        if ret is not None:
            version_col = _text(ret, "version")
            if version_col and version_col not in cols:
                findings.append(Finding(
                    "V5", "E2", name, table,
                    f"DimensionLookup exige columna técnica '{version_col}' "
                    f"(version) que no existe en '{table}'.",
                ))
            sk_col = _text(ret, "name")
            if sk_col and sk_col not in cols:
                findings.append(Finding(
                    "V5", "E2", name, table,
                    f"DimensionLookup exige columna técnica '{sk_col}' "
                    f"(surrogate key de return) que no existe en '{table}'.",
                ))

        key = fields.find("key")
        if key is not None:
            lookup_col = _text(key, "lookup")
            if lookup_col and lookup_col not in cols:
                findings.append(Finding(
                    "V5", "E2", name, table,
                    f"DimensionLookup exige columna '{lookup_col}' (key/lookup) "
                    f"que no existe en '{table}'.",
                ))
    return findings


def v6_insert_update_mapeos(
    root: ET.Element, ddl_columns: dict[str, set[str]] | None = None,
) -> list[Finding]:
    """En InsertUpdate/Update, <lookup>/<key> y <lookup>/<value> usan la
    MISMA pareja de tags (name + un segundo tag) con roles invertidos:
      <key>:   <name>   = campo del stream, <field>  = columna de la tabla
      <value>: <name>   = columna de la tabla, <rename> = campo del stream
    Confundir esto (mapeo invertido) hace que Kettle intente escribir en
    una columna que no existe -- silencioso hasta runtime.

    Sin ddl_columns solo valida que la estructura tenga ambos lados
    presentes; con ddl_columns además confirma que las columnas
    declaradas existen en la tabla real."""
    findings = []
    for step in _steps(root):
        step_type = _text(step, "type")
        if step_type not in ("InsertUpdate", "Update"):
            continue
        name = _text(step, "name")
        lookup = step.find("lookup")
        if lookup is None:
            continue
        table = _text(lookup, "table")
        cols = ddl_columns.get(table) if ddl_columns else None

        for key in lookup.findall("key"):
            stream_field = _text(key, "name")
            column = _text(key, "field")
            if not stream_field or not column:
                findings.append(Finding(
                    "V6", "E3", name, table,
                    "<key> incompleto: falta 'name' (campo del stream) o "
                    "'field' (columna de la tabla).",
                ))
            elif cols is not None and column not in cols:
                findings.append(Finding(
                    "V6", "E3", name, table,
                    f"<key> referencia columna '{column}' que no existe en "
                    f"'{table}' (campo de stream: '{stream_field}').",
                ))

        for value in lookup.findall("value"):
            column = _text(value, "name")
            stream_field = _text(value, "rename")
            if not column or not stream_field:
                findings.append(Finding(
                    "V6", "E3", name, table,
                    "<value> incompleto: falta 'name' (columna de la tabla) o "
                    "'rename' (campo del stream).",
                ))
            elif cols is not None and column not in cols:
                findings.append(Finding(
                    "V6", "E3", name, table,
                    f"<value> referencia columna '{column}' que no existe en "
                    f"'{table}' -- posible mapeo invertido: '{column}' parece "
                    f"ser el campo de stream y '{stream_field}' la columna real.",
                ))
    return findings


def v7_fact_table_output_sin_clave(
    root: ET.Element, fact_prefixes: tuple[str, ...] = FACT_TABLE_PREFIXES,
) -> list[Finding]:
    """TableOutput es un INSERT plano sin clave -- reejecutar la transformación
    duplica filas. Ninguna tabla de hechos (fact_*/hechos_*/hecho_*) debería
    cargarse así; necesita Insert/Update contra su clave natural."""
    findings = []
    for step in _steps(root):
        if _text(step, "type") != "TableOutput":
            continue
        table = _text(step, "table")
        if table and table.lower().startswith(fact_prefixes):
            findings.append(Finding(
                "V7", "E8", _text(step, "name"), table,
                f"TableOutput carga '{table}' (tabla de hechos) con INSERT "
                "plano, sin clave -- no idempotente, duplica filas en cada "
                "reejecución. Reemplazar por Insert/Update con la clave "
                "natural del hecho.",
            ))
    return findings


def v8_truncate_sin_transaccional(root: ET.Element) -> list[Finding]:
    """truncate=Y vacía la tabla antes de cargar: si el step falla a mitad de
    carga, la tabla queda vacía y sin repoblar salvo que la transformación
    corra en una única transacción de BD.

    Tag usado: <info>/<unique_connections> -- confirmado contra fuente
    (no es un proxy/aproximación): en TransDialog.java (UI de Spoon), el
    checkbox lee/escribe transMeta.isUsingUniqueConnections() /
    setUsingUniqueConnections(), y el label de ese checkbox en el bundle de
    mensajes (TransDialog.UniqueConnections.Label) es literalmente "Make
    the transformation database transactional". TransMeta.getXML() serializa
    ese campo como <unique_connections>. No hay ningún otro campo llamado
    "transactional" en TransMeta -- USE_POOLING es un atributo de conexión
    aparte (pooling de conexiones físicas), sin relación con esto."""
    findings = []
    unique_conn_text = _text(root.find("info"), "unique_connections")
    transactional = unique_conn_text.strip().upper() == "Y"
    for step in _steps(root):
        if _text(step, "type") != "TableOutput":
            continue
        if _text(step, "truncate").strip().upper() == "Y" and not transactional:
            findings.append(Finding(
                "V8", "E10", _text(step, "name"), _text(step, "table"),
                "truncate=Y sin transformación transaccional (unique_connections "
                "!= Y) -- un fallo a mitad de carga deja la tabla truncada y sin "
                "repoblar.",
            ))
    return findings


# Todo step de ktr_builder que asigna un value-type REAL de Kettle
# (String/Number/Integer/BigNumber/Date/...) a un campo con nombre propio.
# Relevado por grep de "value_type"/'"type", f.get(' en steps/*.py -- no por
# los dos casos que ya habíamos visto (Calculator/SelectValues), para no
# repetir el mismo punto ciego que dejó pasar Formula.
#
# (step_type, contenedor_directo_del_step | None, tag_repetido, tag_nombre, tag_tipo)
#   contenedor=None: el tag repetido cuelga directo de <step> (Calculator,
#   Formula). Los demás cuelgan de <step>/<fields>/<tag_repetido>.
#
# Deliberadamente AFUERA pese a tener una key de cfg llamada "value_type":
#   FilterRows (steps/transform.py _step_FilterRows) -- <value><type> ahí es
#   el tipo de la CONSTANTE de comparación de un <condition>, no el tipo de
#   un campo que sigue viajando por el stream. No es candidato a "campo
#   monetario mal tipado" en el mismo sentido que el resto de esta lista.
# Deliberadamente AFUERA pese a tener un tag <field><type>:
#   DimensionLookup punch-through fields (steps/lookups.py) -- vocabulario
#   Insert/Update/"Punch through" (modo de escritura), no un value-type de
#   Kettle. GroupBy aggregates -- vocabulario SUM/AVG/COUNT (tipo de
#   agregación), tampoco un value-type. AnalyticQuery fields -- mismo caso,
#   vocabulario LEAD/LAG (función analítica). GetSystemInfo fields --
#   vocabulario "system date (fixed/variable)" (qué dato de sistema capturar),
#   tampoco un value-type. Ninguno de los cuatro puede matchear "Number" de
#   todas formas, así que ni hace falta excluirlos por nombre de step -- el
#   filtro de valor ya los descarta.
# Consideradas y AFUERA por bajo riesgo real (value-type genuino, pero no es
# el campo que persiste con semántica monetaria en el resto del stream):
#   ConcatFields fields (steps/transform.py) -- describe metadata de los
#   campos ENTRADA a la concatenación (para formatear el string armado); el
#   campo de SALIDA (`extra_field`) siempre es String, no hay BigNumber
#   posible aguas abajo de este step. IfNull fields (steps/transform.py) --
#   `type` ahí es un selector de qué columnas recibe el reemplazo de null,
#   no una redeclaración de tipo del campo (IfNullMeta no castea).
# H35/H36 (docs/refactor/01-hallazgos.md) auditaron los ~45 steps de
# STEP_BUILDERS (step_emitters.py) contra este mismo criterio -- no solo
# Calculator/SelectValues/Formula del catálogo E1-E14 original -- y agregaron
# las 7 entradas de abajo desde Constant en adelante. Ver D36
# (02-decisiones.md) para el detalle por step.
FIELD_TYPE_SOURCES: tuple[tuple[str, str | None, str, str, str], ...] = (
    ("Calculator",      None,     "calculation",    "field_name",  "value_type"),
    ("Formula",         None,     "formula",         "field_name",  "value_type"),
    ("SelectValues",    "fields", "meta",            "name",        "type"),
    ("ScriptValueMod",  "fields", "field",           "name",        "type"),
    ("GetVariable",     "fields", "field",           "name",        "type"),
    ("RowGenerator",    "fields", "field",           "name",        "type"),
    ("CsvInput",        "fields", "field",           "name",        "type"),
    ("TextFileInput",   "fields", "field",           "name",        "type"),
    ("ExcelInput",      "fields", "field",           "name",        "type"),
    ("JsonInput",       "fields", "field",           "name",        "type"),
    ("TextFileOutput",  "fields", "field",           "name",        "type"),
    ("ExcelOutput",     "fields", "field",           "name",        "type"),
    ("Constant",        "fields", "field",           "name",        "type"),
    ("FieldSplitter",   "fields", "field",           "name",        "type"),
    ("Denormaliser",    "fields", "field",           "target_name", "target_type"),
    ("RegexEval",       "fields", "field",           "name",        "type"),
    ("DBLookup",        "lookup", "value",           "name",        "type"),
    ("StreamLookup",    "lookup", "value",           "name",        "type"),
    ("DataValidator",   None,     "validator_field", "name",        "data_type"),
)


def v11_monetario_sin_bignumber(
    root: ET.Element, hints: tuple[str, ...] = MONEY_FIELD_HINTS,
) -> list[Finding]:
    """Number en Kettle es double de precisión limitada -- suficiente para
    conteos, no para dinero (errores de redondeo acumulados). Todo campo cuyo
    nombre sugiere un monto debe tipar BigNumber (BigDecimal), sin importar
    QUÉ step lo produce -- ver FIELD_TYPE_SOURCES para la lista completa de
    steps auditados y por qué. Generalizado a partir de "qué step declara un
    value-type de Kettle por campo", no de los steps puntuales donde ya se
    había visto el error (ver nota en FIELD_TYPE_SOURCES: Formula quedaba
    afuera antes y fue exactamente donde se escapó en el output real)."""
    findings = []
    by_step_type = {src[0]: src for src in FIELD_TYPE_SOURCES}
    for step in _steps(root):
        step_type = _text(step, "type")
        src = by_step_type.get(step_type)
        if src is None:
            continue
        _, container_tag, repeated_tag, name_tag, type_tag = src
        name = _text(step, "name")

        container = step if container_tag is None else step.find(container_tag)
        if container is None:
            continue

        for entry in container.findall(repeated_tag):
            field_name = _text(entry, name_tag)
            field_type = _text(entry, type_tag)
            if field_name and field_type == "Number" and any(
                h in field_name.lower() for h in hints
            ):
                findings.append(Finding(
                    "V11", "E14", name, "",
                    f"{step_type} produce/declara '{field_name}' (nombre de "
                    f"campo monetario) con {type_tag}=Number -- debe ser "
                    "BigNumber.",
                ))
    return findings


# (step_type, contenedor_directo_del_step, tag_nombre_en_key, tag_columna_en_key)
# CombinationLookup/DimensionLookup: <fields><key><name>/<lookup></key></fields>
# StreamLookup/DBLookup:             <lookup><key><name>/<field></key></lookup>
# InsertUpdate/Update NO están acá a propósito: su <key> ya lo audita V6
# (mismo defecto -- incompleto/vacío -- bajo E3, no duplicar el hallazgo).
LOOKUP_KEY_SOURCES: tuple[tuple[str, str, str, str], ...] = (
    ("CombinationLookup", "fields", "name", "lookup"),
    ("DimensionLookup",   "fields", "name", "lookup"),
    ("StreamLookup",      "lookup", "name", "field"),
    ("DBLookup",          "lookup", "name", "field"),
)


def v13_lookup_key_incompleta(root: ET.Element) -> list[Finding]:
    """Todo step de la familia lookup-por-clave necesita, para poder
    inicializar en Spoon, al menos una entrada de <key> con AMBOS lados
    (campo del stream + columna/campo de la tabla) no vacíos -- ver
    LOOKUP_KEY_SOURCES para qué tags usa cada step type.

    Construido "por tipo de step" (qué steps tienen un bloque <key> del que
    dependen para inicializar), no a partir de un caso puntual ya visto --
    aunque el disparador fue justamente un CombinationLookup real con
    <key><name/><lookup/></key> vacío que ni el gate estructural ni V4-V11
    detectaban (nadie chequeaba completitud de key ahí)."""
    findings = []
    by_step_type = {src[0]: src for src in LOOKUP_KEY_SOURCES}
    for step in _steps(root):
        step_type = _text(step, "type")
        src = by_step_type.get(step_type)
        if src is None:
            continue
        _, container_tag, name_tag, col_tag = src
        name = _text(step, "name")
        table = _text(step, "table")
        if not table:
            lookup_el = step.find("lookup")
            if lookup_el is not None:
                table = _text(lookup_el, "table")

        container = step.find(container_tag)
        keys = container.findall("key") if container is not None else []
        if not keys:
            findings.append(Finding(
                "V13", "-", name, table,
                f"{step_type} sin ningún <key> -- el step no tiene con qué "
                "matchear, no puede inicializar en Spoon.",
            ))
            continue
        for key in keys:
            stream_val = _text(key, name_tag)
            col_val = _text(key, col_tag)
            if not stream_val or not col_val:
                falta = []
                if not stream_val:
                    falta.append(f"'{name_tag}' (campo del stream)")
                if not col_val:
                    falta.append(f"'{col_tag}' (columna/campo de la tabla)")
                findings.append(Finding(
                    "V13", "-", name, table,
                    f"{step_type}: <key> incompleta -- falta " + " y ".join(falta) +
                    " -- el step no inicializa en Spoon con esta key vacía.",
                ))
    return findings
