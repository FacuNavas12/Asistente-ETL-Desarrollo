"""Constantes y listas de keywords compartidas por el paquete superset_export —
version del formato de export, identidad de ETL_DWH, y listas de clasificacion
semantica de columnas/tablas (port 1:1 de frontend/src/utils/supersetExport.js)."""

from __future__ import annotations

VERSION = "1.0.0"
DB_NAME = "ETL_DWH"
DB_SCHEMA = "public"

# UUID fijo de la conexion ETL_DWH — igual a DB_UUID_FRONTEND en
# superset_client/constants.py. Todos los exports comparten esta entrada.
DB_UUID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# Prefijos de tablas intermedias/staging — excluidas de datasets/charts.
# Lista larga (11 items): antes vivia solo en el frontend; ahora unica fuente
# de verdad. superset_client/constants.STAGING_PREFIXES (7 items, mas corta)
# se usa para el write-gate contra la conexion real — no la unificamos aca
# para no tocar ese modulo fuera de alcance.
STAGING_PREFIXES = [
    "stg_", "staging_", "tmp_", "temp_", "ods_", "raw_", "wrk_", "work_",
    "landing_", "src_", "source_", "ext_",
]

# Columnas de auditoria ETL — no aportan valor analitico en charts.
AUDIT_KEYWORDS = [
    "CARGA_DW", "LOAD_DT", "INSERT_DT", "UPDATE_DT", "CREATED_AT", "UPDATED_AT",
    "MODIFIED_AT", "ETL_DATE", "PROCESS_DATE", "FECHA_CARGA", "FECHA_INSERT",
    "FECHA_UPDATE", "FECHA_ETL", "FECHA_PROCESO", "DW_TIMESTAMP", "AUDIT",
]

# Keywords de deteccion de fecha (nombre de columna).
DATE_KW = [
    "FECHA", "DATE", "DT", "ANIO", "MES", "TRIMESTRE", "DIA", "YEAR", "MONTH",
    "DAY", "PERIODO", "QUARTER",
]

# Prefijos/nombres que indican categoria aunque contengan una keyword de metrica
# (ej. TIPO_VENTA debe ser categoria, no metrica, aunque VENTA sea keyword de metrica).
CAT_PREFIXES = [
    "TIPO", "CATEGORIA", "ESTADO", "CLASE", "GRUPO", "NOMBRE", "DESC",
    "DESCRIPCION", "CODIGO", "CODE", "FLAG", "IND", "INDICADOR", "GENERO",
    "PAIS", "REGION", "CIUDAD", "ZONA", "SEGMENTO",
]

# Keywords de deteccion de metrica — vocabulario comun de DWH.
METRIC_KW = [
    "MONTO", "IMPORTE", "TOTAL", "PRECIO", "CANTIDAD", "QTY", "AMOUNT",
    "INGRESO", "EGRESO", "COSTO", "VENTA", "COMPRA", "REVENUE", "DESCUENTO",
    "IMPUESTO", "NETO", "BRUTO", "SALDO", "COUNT", "VALOR", "STOCK", "PESO",
    "VOLUMEN", "TASA", "PORCENTAJE", "RATIO", "SCORE", "RATING", "HORAS",
    "DIAS", "UNIDADES", "GANANCIA", "MARGEN", "UTILIDAD", "FACTURACION",
    "PAGOS", "CUOTA", "DEUDA", "CREDITO", "DEBITO", "BALANCE", "INVENTARIO",
    "VENTAS", "COMPRAS", "PROMEDIO", "AVG", "SUM", "MAX", "MIN",
]

# Keywords que marcan una columna como "descriptiva" — preferida como
# pick_column (columna de detalle mostrada en charts de tipo tabla).
DESCRIPTIVE_KEYWORDS = [
    "NOMBRE", "NAME", "DESCRIPCION", "DESCRIPTION", "DETALLE", "DETAIL",
    "TIPO", "TYPE", "CATEGORIA", "CATEGORY", "CLASE", "CLASS",
    "ESTADO", "STATUS", "ETIQUETA", "LABEL", "TITULO", "TITLE",
    "RAZON_SOCIAL", "RAZON", "SOCIAL", "DENOMINACION", "FANTASIA",
    "APELLIDO", "SURNAME",
    "OBSERVACION", "COMENTARIO", "NOTA",
    "SUBCATEGORIA", "SUBCATEGORY",
    "LOCALIDAD", "BARRIO", "COLONIA",
    "SUCURSAL", "BRANCH", "OFICINA", "SEDE",
    "LINEA", "LINE", "FAMILIA", "FAMILY", "MARCA", "BRAND",
    "SERVICIO", "SERVICE", "MODALIDAD", "TURNO", "SHIFT",
    "DEPARTAMENTO", "CIUDAD", "PAIS", "REGION", "PROVINCIA",
    "MUNICIPIO", "ZONA", "TERRITORIO", "COUNTRY", "CITY",
    "PROYECTO", "PROJECT", "FASE", "ETAPA", "STAGE",
    "PRODUCTO", "PRODUCT", "ARTICULO", "ITEM", "SKU",
    "CLIENTE", "CUSTOMER", "PROVEEDOR", "SUPPLIER", "VENDEDOR",
    "COMPRA", "VENTA", "SALE", "CANAL", "CHANNEL",
    "ONTOLOGY", "TERM", "DEFINITION", "QUALIFIER", "EVIDENCE",
    "GENE", "PROTEIN", "RNA", "ANNOTATION",
    "EMPLEADO", "EMPLOYEE", "CARGO", "ROLE",
    "AREA", "DIVISION", "EQUIPO", "TEAM",
    "ASIGNATURA", "CURSO", "MATERIA", "CARRERA", "FACULTAD",
    "ALUMNO", "STUDENT", "DOCENTE", "TEACHER",
]

# Categorias tecnicas excluidas del breakdown por categoria en tablas FACT
# (ej. MONEDA/ESTADO no son dimensiones de negocio interesantes para un bar chart).
TECHNICAL_CAT_KEYWORDS = ["MONEDA", "CURRENCY", "ESTADO", "STATUS", "FLAG", "TIPO_CAMBIO", "ACTIVO"]
