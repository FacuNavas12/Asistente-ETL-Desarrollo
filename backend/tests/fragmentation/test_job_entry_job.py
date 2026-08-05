"""
F2.5/H7 — soporte JobEntryJob: una entry de .kjb que llama a OTRO .kjb (no a
un .ktr). Necesario para la jerarquía de 3 niveles (job_master.kjb ->
job_origen_stg.kjb/job_stg_dwh.kjb -> .ktr) cuando F3 fragmente una etapa en
más de un archivo.

Shape XML verificado contra JobEntryJob.getXML() (pentaho-kettle) — ver
kettle-jobentryjob-xml-spec.md. Antes de este fix, build_kjb_xml solo emitía
<type>TRANS</type> sin importar el filename — Kettle instancia JobEntryTrans,
que ni siquiera lee los mismos tags, y falla al abrir/ejecutar en Spoon.
"""
from __future__ import annotations

from xml.etree.ElementTree import fromstring

from app.schemas.job_schemas import JobEntry, JobPlan
from app.services.job_analyzer import build_kjb_xml
from app.services.kjb_xml_validator import KjbXmlValidationError, validate_kjb_xml


def _plan(entries: list[JobEntry]) -> JobPlan:
    return JobPlan(
        job_name="job_master",
        description="Orquesta las etapas",
        execution_order=entries,
        overall_rationale="test",
    )


def test_default_entry_type_still_emits_trans_unchanged():
    """Backward compat: nada que construya JobEntry sin entry_type (todo el
    código anterior a F2.5) sigue emitiendo TRANS exactamente igual."""
    plan = _plan([
        JobEntry(order=1, transformation_name="KTR_1", filename="ktr_1.ktr", rationale="r1"),
        JobEntry(order=2, transformation_name="KTR_2", filename="ktr_2.ktr", rationale="r2"),
    ])
    xml = build_kjb_xml(plan)
    root = fromstring(xml)
    types = [e.findtext("type") for e in root.findall("./entries/entry")]
    assert types.count("TRANS") == 2
    assert "JOB" not in types
    validate_kjb_xml(xml)  # no debe levantar


def test_job_entry_type_emits_job_with_filename_specification():
    plan = _plan([
        JobEntry(order=1, transformation_name="job_origen_stg", filename="job_origen_stg.kjb",
                 rationale="orquesta origen->stg", entry_type="job"),
        JobEntry(order=2, transformation_name="job_stg_dwh", filename="job_stg_dwh.kjb",
                 rationale="orquesta stg->dwh", entry_type="job"),
    ])
    xml = build_kjb_xml(plan)
    root = fromstring(xml)
    entries = root.findall("./entries/entry")
    job_entries = [e for e in entries if e.findtext("type") == "JOB"]
    assert len(job_entries) == 2

    e = job_entries[0]
    assert e.findtext("name") == "job_origen_stg"
    assert e.findtext("specification_method") == "filename"
    assert e.findtext("filename") == "${Internal.Job.Filename.Directory}/job_origen_stg.kjb"
    # Métodos de repositorio, sin usar acá — deben quedar vacíos, no ausentes.
    assert e.find("jobname").text is None
    assert e.find("directory").text is None
    assert e.find("job_object_id").text is None
    assert e.findtext("wait_until_finished") == "Y"

    # No debe levantar aunque no haya ninguna entrada TRANS — un job_master
    # que delega enteramente en jobs hijos es un caso válido (H7).
    validate_kjb_xml(xml)


def test_kjb_with_no_trans_and_no_job_entries_still_rejected():
    """La invariante de fondo (al menos una entrada que orqueste trabajo
    real) se mantiene — el fix de H7 la amplía a TRANS-o-JOB, no la retira.
    build_kjb_xml() ya corre validate_kjb_xml() internamente (última barrera
    antes de devolver el XML), así que el raise ocurre acá mismo."""
    plan = _plan([])
    try:
        build_kjb_xml(plan)
        assert False, "debía levantar KjbXmlValidationError"
    except KjbXmlValidationError as e:
        assert any("TRANS ni JOB" in issue for issue in e.issues)


def test_mixed_trans_and_job_entries_in_same_kjb():
    plan = _plan([
        JobEntry(order=1, transformation_name="KTR_prep", filename="ktr_prep.ktr", rationale="r1"),
        JobEntry(order=2, transformation_name="job_stg_dwh", filename="job_stg_dwh.kjb",
                 rationale="r2", entry_type="job"),
    ])
    xml = build_kjb_xml(plan)
    root = fromstring(xml)
    types = [e.findtext("type") for e in root.findall("./entries/entry")]
    assert "TRANS" in types
    assert "JOB" in types
    validate_kjb_xml(xml)
