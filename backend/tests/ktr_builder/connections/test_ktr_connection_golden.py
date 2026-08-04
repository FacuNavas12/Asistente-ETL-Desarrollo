"""
Golden-file test: fixture .ktr fiel a un export de Spoon 9.x (tests/fixtures/
connections_sample.ktr) con dos conexiones (postgres + sqlserver). Documenta
la estructura/campos que _build_connection() en ktr_builder.py debe reproducir
para que el .ktr abra sin reconfiguración. El fixture trae passwords ofuscados
reales (formato Spoon) pero esta suite no los valida — el backend nunca lee ni
escribe ese campo con contenido real (ver decisión de no-custodia de
credenciales), así que no hay comportamiento propio que verificar ahí.
"""
from pathlib import Path
from xml.etree import ElementTree as ET

FIXTURE = Path(__file__).parent.parent.parent / "fixtures" / "connections_sample.ktr"


def _load_connections() -> dict[str, ET.Element]:
    root = ET.parse(FIXTURE).getroot()
    return {c.findtext("name"): c for c in root.findall("connection")}


def test_fixture_has_both_connections():
    conns = _load_connections()
    assert set(conns) == {"pg_test", "mssql_test"}


def test_pg_connection_fields():
    c = _load_connections()["pg_test"]
    assert c.findtext("type") == "POSTGRESQL"
    assert c.findtext("access") == "Native"
    assert c.findtext("server") == "localhost"
    assert c.findtext("port") == "5432"
    assert c.findtext("database") == "testdb"
    assert c.findtext("username") == "pg_test_user"


def test_mssql_connection_fields():
    c = _load_connections()["mssql_test"]
    assert c.findtext("type") == "MSSQLNATIVE"
    assert c.findtext("access") == "Native"
    assert c.findtext("server") == "localhost"
    assert c.findtext("port") == "1433"
    assert c.findtext("database") == "testdb"
    assert c.findtext("username") == "mssql_test_user"


def test_steps_reference_declared_connections():
    root = ET.parse(FIXTURE).getroot()
    conn_names = {c.findtext("name") for c in root.findall("connection")}
    for step in root.findall("step"):
        conn_ref = step.findtext("connection")
        if conn_ref:
            assert conn_ref in conn_names, f"step '{step.findtext('name')}' referencia conexión huérfana '{conn_ref}'"
