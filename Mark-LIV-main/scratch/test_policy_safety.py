# test_policy_safety.py — Smoke test Tahap 1: Fondasi Keamanan
# Cakupan: policy_engine (decide/protected/mtime-reload), audit_logger (JSONL),
#          emergency_stop (trigger/status/resume), app_manager × policy gate.
# Jalankan:  set PYTHONIOENCODING=utf-8 && python scratch\test_policy_safety.py
import json
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

PASS = FAIL = 0
def ok(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name} {extra}")

print("=== 1. policy_engine: decide() ===")
from core.policy_engine import decide, load_policy, protected_processes, describe

ok("csrss → deny critical", decide("app.kill", target="csrss")["decision"] == "deny")
ok("csrss risk=critical", decide("app.kill", target="csrss.exe")["risk"] == "critical")
ok("svchost → deny (protected)", decide("app.kill", target="svchost")["decision"] == "deny")
ok("app.kill chrome → confirm", decide("app.kill", target="chrome")["decision"] == "confirm")
ok("app.close chrome → allow", decide("app.close", target="chrome")["decision"] == "allow")
ok("app.list → allow low", decide("app.list")["decision"] == "allow")
ok("aksi tak dikenal → default", decide("unknown.thing")["decision"] == "allow")
ok("wildcard prefix app.* bekerja",
   (load_policy()["rules"].get("app.close") is not None))

print("=== 2. policy file mtime reload ===")
tmp = tempfile.mkdtemp()
pol_file = BASE / "policies" / "default_policy.json"
backup = pol_file.read_text(encoding="utf-8")
try:
    edited = json.loads(backup)
    edited["rules"]["app.close"] = ["medium", "confirm"]       # naikkan ke confirm
    pol_file.write_text(json.dumps(edited, indent=2), encoding="utf-8")
    d = decide("app.close", target="chrome")                    # mtime berubah
    ok("edit policy tanpa restart → confirm", d["decision"] == "confirm", f"got {d}")
finally:
    pol_file.write_text(backup, encoding="utf-8")               # restore
d = decide("app.close", target="chrome")
ok("restore → allow lagi", d["decision"] == "allow", f"got {d}")
shutil.rmtree(tmp, ignore_errors=True)

print("=== 3. audit_logger: JSONL append ===")
from core.audit_logger import log_event, log_command, tail, new_correlation_id
corr = new_correlation_id()
ok("correlation_id format", corr.startswith("corr-") and len(corr) == 15, corr)
ok("log_command True", log_command(skill="test_skill", target="demo",
                                   decision="allow", risk_level="low",
                                   result="ok", correlation_id=corr))
events = tail(5)
ok("event tersimpan", any(e.get("skill") == "test_skill" for e in events))
ok("correlation_id tercatat", any(e.get("correlation_id") == corr for e in events))
ok("timestamp ada", bool(events[-1].get("timestamp")))

print("=== 4. emergency_stop ===")
from skills.admin.emergency_stop import (
    emergency_stop, is_stopped, trigger, resume, matches_stop_phrase,
)
ok("status awal → tidak stop", not is_stopped())
ok("matches_stop_phrase 'berhenti'", matches_stop_phrase("berhenti"))
ok("matches_stop_phrase 'jangan lanjut'", matches_stop_phrase("jangan lanjut"))
ok("trigger → is_stopped True", trigger("tes otomatis", by="test") and is_stopped())
ok("skill handler stop", emergency_stop({"cmd": "stop", "reason": "tes2"}).startswith("⛔"))
ok("status handler menyebut aktif", "AKTIF" in emergency_stop({"cmd": "status"}))
ok("resume → is_stopped False", resume() and not is_stopped())
ok("status handler normal", "Tidak ada" in emergency_stop({"cmd": "status"}))
stop_events = [e for e in tail(20) if e.get("skill") == "emergency_stop"]
ok("audit mencatat stop+resume", len(stop_events) >= 2, str(len(stop_events)))

print("=== 5. app_manager × policy gate ===")
from skills.admin.app_manager import app_manager, TOOL
ok("TOOL dict ada", TOOL["name"] == "app_manager" and callable(TOOL["handler"]))
ok("list tetap jalan", app_manager({"cmd": "list"}).startswith("Aplikasi aktif"))
out = app_manager({"cmd": "kill", "target": "csrss"})
ok("csrss ditolak policy", "Ditolak oleh policy" in out, out[:80])
import subprocess as _sp, psutil as _ps
proc = _sp.Popen(["ping", "-n", "30", "127.0.0.1"], creationflags=0x08000000)
pid = proc.pid
out = app_manager({"cmd": "kill", "target": str(pid)})
ok("kill PID spawn → minta konfirmasi", "⚠️" in out and "confirm=true" in out, out[:100])
out = app_manager({"cmd": "kill", "target": str(pid), "confirm": True})
ok("confirm=true → proses mati sungguhan", not _ps.pid_exists(pid), out[:100])
deny_events = [e for e in tail(30) if e.get("decision") == "deny"]
ok("audit mencatat deny csrss", any("csrss" in (e.get("target") or "")
                                    for e in deny_events))
conf_events = [e for e in tail(30) if e.get("result") == "awaiting_confirmation"]
ok("audit mencatat awaiting_confirmation", len(conf_events) >= 1)

print("=== 6. policy + emergency_stop terdeteksi skill_hub (2 otak) ===")
from core.skill_hub import skill_hub
skill_hub.discover(force_reload=True)
ok("emergency_stop di skill_hub", skill_hub.has("emergency_stop"))
ok("app_manager masih di skill_hub", skill_hub.has("app_manager"))
cat = skill_hub.get_hermes_catalog()
ok("emergency_stop masuk katalog Hermes", "emergency_stop" in cat)

print(f"\n{'='*46}\nHASIL: {PASS} PASS, {FAIL} FAIL dari {PASS+FAIL}")
sys.exit(1 if FAIL else 0)
