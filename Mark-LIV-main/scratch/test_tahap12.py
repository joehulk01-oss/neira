# test_tahap12.py — Proactive Execution: scheduler jalan otomatis dari main loop
# Jalankan: python scratch\test_tahap12.py
from __future__ import annotations

import ast
import json
import time
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

passed = 0
failed = 0


def check(name: str, cond: bool) -> None:
    global passed, failed
    if cond:
        passed += 1
        print(f"  PASS  {name}")
    else:
        failed += 1
        print(f"  FAIL  {name}")


print("=" * 64)
print("TAHAP 12 — PROACTIVE EXECUTION (scheduler otomatis + laporan)")
print("=" * 64)

from core import scheduler as ts                         # noqa: E402
from core.policy_engine import decide as _decide         # noqa: E402
from core.skill_hub import skill_hub                     # noqa: E402
from skills.admin import task_scheduler_skill as tss     # noqa: E402

AUDIT_PATH = Path(__file__).resolve().parent.parent / "audit" / "events.jsonl"
MAIN_PATH = Path(__file__).resolve().parent.parent / "main.py"

# ── [1] due_report() ─────────────────────────────────────────────────────────
print("\n[1] due_report() — filter laporan yang layak ganggu user")
check("tick kosong → None", ts.due_report("") is None)
check("estop ⛔ → None", ts.due_report("⛔ EMERGENCY STOP aktif") is None)
check("tidak ada due → None", ts.due_report("⏱ Scheduler tick: 0 jadwal jatuh tempo (2 terdaftar).") is None)
check("ada due → laporan", ts.due_report("⏱ Scheduler tick: 1 jadwal jatuh tempo.\n  ✅ x: ok") is not None)

# ── [2] Integrasi main.py: loop terpasang ────────────────────────────────────
print("\n[2] Integrasi main.py")
src = MAIN_PATH.read_text(encoding="utf-8", errors="ignore")
tree = ast.parse(src)
main_cls = next(n for n in ast.walk(tree)
                if isinstance(n, ast.ClassDef) and n.name == "JarvisLive")
methods = {n.name for n in main_cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
check("_run_task_scheduler ada di JarvisLive", "_run_task_scheduler" in methods)
check("create_task dipanggil", "tg.create_task(self._run_task_scheduler())" in src)
meth = next(n for n in main_cls.body
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "_run_task_scheduler")
m_src = ast.get_source_segment(src, meth)
check("pakai to_thread tick", "_ts.tick" in m_src and "to_thread" in m_src)
check("laporan via send_client_content", "send_client_content" in m_src)
check("due_report dipakai utk filter", "due_report" in m_src)
check("jangan ganggu saat bicara", "_speaking_lock" in m_src)

# ── [3] Tick end-to-end dengan jadwal nyata (isolasi file) ───────────────────
print("\n[3] tick() end-to-end + due_report nyata")
TMP_SCHED = Path(__file__).resolve().parent / "tmp_schedules_test12.json"
ORIG_SCHED = ts.SCHED_PATH
ts.SCHED_PATH = TMP_SCHED
if TMP_SCHED.exists():
    TMP_SCHED.unlink()

GOOD_STEPS = [{"skill": "workspace_dev", "params": {"cmd": "analyze", "target": ""}}]
try:
    s, created, err = ts.add("tes-proactive", "analisa workspace", GOOD_STEPS,
                             every_minutes=30)
    check("jadwal uji dibuat", created and not err)
    with ts._lock:
        rows = ts._load()
        for r in rows:
            if r["schedule_id"] == s["schedule_id"]:
                r["next_run"] = 0.0
        ts._save(rows)
    out = ts.tick()
    check("tick menembak", "1 jadwal jatuh tempo" in out)
    rep = ts.due_report(out)
    check("due_report menghasilkan laporan", rep is not None and "✅" in rep)
    s_after = ts.get("tes-proactive")
    check("run_count = 1", s_after.get("run_count", 0) == 1)
    check("next_run maju", float(s_after.get("next_run") or 0) > time.time())
    # tick kedua: tidak boleh nembak ulang (anti re-trigger)
    out2 = ts.tick()
    check("tick kedua 0 due (anti re-trigger)", "0 jadwal jatuh tempo" in out2)
    check("due_report kedua None (tidak ganggu user)", ts.due_report(out2) is None)
finally:
    ts.SCHED_PATH = ORIG_SCHED
    if TMP_SCHED.exists():
        TMP_SCHED.unlink()

# ── [4] Audit jejak scheduler.tick dari eksekusi nyata ───────────────────────
print("\n[4] Audit jejak")
found = False
if AUDIT_PATH.exists():
    for line in AUDIT_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if ev.get("skill") == "task_scheduler" and ev.get("action") == "scheduler.tick":
            found = True
            break
check("audit scheduler.tick tercatat", found)

# ── [5] Regresi mini: wrapper & hub tetap jalan ──────────────────────────────
print("\n[5] Regresi mini wrapper + hub")
d = _decide("scheduler.manage")
check("policy scheduler.manage masih allow", d.get("decision") == "allow")
out = tss.task_scheduler_skill({"cmd": "list"})
check("wrapper list jalan", isinstance(out, str) and ("jadwal" in out.lower() or "Tidak ada" in out))
check("hub masih daftar skill", skill_hub.has("task_scheduler_skill"))
decls = [x["name"] for x in skill_hub.get_tool_declarations()]
check("deklarasi tool tetap ada", "task_scheduler_skill" in decls)

print("\n" + "=" * 64)
print(f"HASIL: {passed} PASS, {failed} FAIL dari {passed + failed} cek")
print("=" * 64)
sys.exit(0 if failed == 0 else 1)
