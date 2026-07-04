"""
Migra datos de localStorage (etl_list / job_list) al backend.
Uso:
  1. En browser console: copy(JSON.stringify({etls: JSON.parse(localStorage.getItem("etl_list") ?? "null"), jobs: JSON.parse(localStorage.getItem("job_list") ?? "null")}))
  2. Pegar clipboard → localStorage_export.json (en raíz del proyecto)
  3. cd backend && venv\Scripts\activate && python ../migrate_localstorage.py
"""
import json
import sys
from pathlib import Path
import requests

BACKEND = "http://localhost:8000"
EXPORT_FILE = Path(__file__).parent / "localStorage_export.json"

VALID_STATUSES = {"draft", "pending", "en_proceso", "done", "error"}


def get_items(entry):
    if not entry:
        return []
    if isinstance(entry, list):
        return entry
    return entry.get("data", [])


def migrate_etls(items):
    ok = 0
    for etl in items:
        status = etl.get("status", "done")
        if status not in VALID_STATUSES:
            status = "done"
        payload = {
            "name": etl.get("name") or "ETL migrado",
            "status": status,
            "formData": etl.get("formData"),
            "result": etl.get("result"),
        }
        r = requests.post(f"{BACKEND}/api/etls/", json=payload, timeout=15)
        label = etl.get("name", "?")
        if r.ok:
            ok += 1
            print(f"  ✓ ETL '{label}' → {r.json().get('id')}")
        else:
            print(f"  ✗ ETL '{label}' → {r.status_code}: {r.text[:120]}")
    return ok


def migrate_jobs(items):
    ok = 0
    for job in items:
        status = job.get("status", "done")
        if status not in VALID_STATUSES:
            status = "done"
        payload = {
            "name": job.get("name") or "Job migrado",
            "status": status,
            "formData": job.get("formData"),
            "result": job.get("result"),
        }
        r = requests.post(f"{BACKEND}/api/jobs/", json=payload, timeout=15)
        label = job.get("name", "?")
        if r.ok:
            ok += 1
            print(f"  ✓ Job '{label}' → {r.json().get('id')}")
        else:
            print(f"  ✗ Job '{label}' → {r.status_code}: {r.text[:120]}")
    return ok


if not EXPORT_FILE.exists():
    print(f"ERROR: no se encontró {EXPORT_FILE}")
    print("Exportá desde browser console y guardá como localStorage_export.json en raíz del proyecto.")
    sys.exit(1)

data = json.loads(EXPORT_FILE.read_text(encoding="utf-8"))
etl_items = get_items(data.get("etls"))
job_items = get_items(data.get("jobs"))

print(f"Encontrados: {len(etl_items)} ETLs, {len(job_items)} Jobs")

etl_ok = migrate_etls(etl_items)
job_ok = migrate_jobs(job_items)

print(f"\nListo: {etl_ok}/{len(etl_items)} ETLs, {job_ok}/{len(job_items)} Jobs migrados a Supabase.")
