# test_orchestrator.py — Smoke test Tahap 2: Orchestrator (job_manager + policy + audit)
# Jalankan:  set PYTHONIOENCODING=utf-8 && python scratch\test_orchestrator.py
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

RUN = time.strftime("%H%M%S")          # goal unik per run — jobs.json persisten
PASS = FAIL = 0
def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")

from core import job_manager as jm
from core.jarvis_orchestrator import run, status, cancel, orchestrator, TOOL

print("=== 1. job_manager: create + anti double-run ===")
job, created = jm.create_job(f"tes orkestra A {RUN}", [
    {"skill": "app_manager", "params": {"cmd": "list"}, "policy_action": "app.list", "name": "cek aplikasi"},
], risk_level="low")
ok("job dibuat", created and job["job_id"].startswith("job-"))
ok("status awal queued", job["status"] == jm.QUEUED)
job2, created2 = jm.create_job(f"Tes Orkestra A {RUN}", [
    {"skill": "app_manager", "params": {"cmd": "list"}},
])
ok("double-run dicegah (job lama dikembalikan)", not created2 and job2["job_id"] == job["job_id"])

print("=== 2. run(): langkah sukses → succeeded + langkah done ===")
jobX, _ = jm.create_job(f"tes orkestra B {RUN}", [
    {"skill": "app_manager", "params": {"cmd": "list"}, "policy_action": "app.list", "name": "monitor"},
], risk_level="low")
jm.set_status(jobX["job_id"], jm.RUNNING)
out = run("", [], job_id=jobX["job_id"])
ok("langkah sukses dieksekusi", "✅ 1." in out, out[:120])
ok("job sukses", jobX["job_id"] in out and "succeeded" in out, out[-200:])
step0 = jm.get_job(jobX["job_id"])["steps"][0]
ok("hasil langkah tersimpan", step0["status"] == "done" and step0["result"], step0["result"][:60])

print("=== 3. policy: deny (csrss) menggagalkan job; confirm menahan job ===")
jobD, _ = jm.create_job(f"tes deny {RUN}", [
    {"skill": "app_manager", "params": {"cmd": "kill", "target": "csrss", "confirm": True},
     "policy_action": "app.kill", "name": "kill csrss"},
], risk_level="high")
jm.set_status(jobD["job_id"], jm.RUNNING)
out = run("", [], job_id=jobD["job_id"])
ok("deny → job failed", "DITOLAK policy" in out and "failed" in out, out[:150])

jobC, _ = jm.create_job(f"tes confirm {RUN}", [
    {"skill": "app_manager", "params": {"cmd": "kill", "target": "notepad"},
     "policy_action": "app.kill", "name": "kill notepad"},
], risk_level="high")
jm.set_status(jobC["job_id"], jm.RUNNING)
out = run("", [], job_id=jobC["job_id"])
ok("confirm → job waiting + instruksi resume",
   "butuh konfirmasi" in out and "confirm\": true" in out, out[:200])
st = jm.get_job(jobC["job_id"])
ok("status waiting_confirmation di langkah 0",
   st["status"] == jm.WAITING_CONFIRMATION and st["current_step"] == 0)

print("=== 4. resume setelah konfirmasi (kill proses spawn sungguhan) ===")
import subprocess as _sp, psutil as _ps
proc = _sp.Popen(["ping", "-n", "30", "127.0.0.1"], creationflags=0x08000000)
pid = proc.pid
jobR, _ = jm.create_job(f"tes resume {RUN}", [
    {"skill": "app_manager", "params": {"cmd": "kill", "target": str(pid)},
     "policy_action": "app.kill", "name": "kill spawn"},
], risk_level="high")
jm.set_status(jobR["job_id"], jm.RUNNING)
out = run("", [], job_id=jobR["job_id"])                    # tanpa confirm → tahan
ok("menahan dulu", "butuh konfirmasi" in out)
out = run("", [], job_id=jobR["job_id"], confirm=True)      # resume dari langkah 0
ok("resume → proses mati", not _ps.pid_exists(pid), out[:150])
ok("job succeeded setelah resume", "succeeded" in out, out[-150:])

print("=== 5. skill gagal → 1 retry → job failed ===")
jobF, _ = jm.create_job(f"tes gagal {RUN}", [
    {"skill": "skill_yang_tidak_ada_9999", "params": {}, "name": "langkah hantu"},
], risk_level="low")
jm.set_status(jobF["job_id"], jm.RUNNING)
out = run("", [], job_id=jobF["job_id"])
ok("gagal → job failed + pesan jelas", "gagal" in out and "failed" in out, out[:150])
ok("retry tercatat", jm.get_job(jobF["job_id"]).get("retry_count", 0) == 1)

print("=== 6. status & cancel & handler & TOOL ===")
ok("status job terbaru", "tes" in status() or "Belum ada" in status())
ok("status by id", jobX["job_id"] in status(jobX["job_id"]))
ok("cancel job", jobD["job_id"] in cancel(jobD["job_id"]) and
   jm.get_job(jobD["job_id"])["status"] == jm.CANCELLED)
ok("handler run via TOOL", callable(TOOL["handler"]) and
   ("Sebutkan goal" in orchestrator({"cmd": "run"}) or "steps" in orchestrator({"cmd": "run"})))
ok("handler cmd tak dikenal", "tidak dikenal" in orchestrator({"cmd": "ngawur"}))

from core.skill_hub import skill_hub
skill_hub.discover(force_reload=True)
ok("orchestrator di skill_hub (2 otak)", skill_hub.has("orchestrator"))
ok("masuk katalog Hermes", "orchestrator" in skill_hub.get_hermes_catalog())

print(f"\n{'='*46}\nHASIL: {PASS} PASS, {FAIL} FAIL dari {PASS+FAIL}")
sys.exit(1 if FAIL else 0)
