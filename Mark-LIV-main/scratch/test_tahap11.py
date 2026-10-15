# test_tahap11.py — Task Scheduler (blueprint §4.10-ish)
# Jalankan: python scratch\test_tahap11.py
from __future__ import annotations

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
print("TAHAP 11 — TASK SCHEDULER (jadwal tugas otomatis + tick)")
print("=" * 64)

from core import scheduler as ts                         # noqa: E402
from core.policy_engine import decide as _decide         # noqa: E402
from core.skill_hub import skill_hub                     # noqa: E402
from skills.admin import task_scheduler_skill as tss     # noqa: E402
from skills.admin.emergency_stop import trigger, resume  # noqa: E402

AUDIT_PATH = Path(__file__).resolve().parent.parent / "audit" / "events.jsonl"

# Isolasi: pakai file jadwal scratch, BUKAN memory/schedules.json asli
TMP_SCHED = Path(__file__).resolve().parent / "tmp_schedules_test.json"
ORIG_SCHED = ts.SCHED_PATH
ts.SCHED_PATH = TMP_SCHED
if TMP_SCHED.exists():
    TMP_SCHED.unlink()

GOOD_STEPS = [{"skill": "workspace_dev", "params": {"cmd": "analyze", "target": ""}}]

try:
    # ── [1] Policy ───────────────────────────────────────────────────────────
    print("\n[1] Policy scheduler.manage")
    d = _decide("scheduler.manage")
    check("scheduler.manage terdecide", d.get("decision") in ("allow", "confirm", "deny"))
    check("scheduler.manage allow", d.get("decision") == "allow")

    # ── [2] Parser HH:MM ─────────────────────────────────────────────────────
    print("\n[2] Parser waktu _parse_hhmm()")
    check("07:30 valid", ts._parse_hhmm("07:30") == (7, 30))
    check("7:5 valid", ts._parse_hhmm("7:5") == (7, 5))
    check("24:00 invalid", ts._parse_hhmm("24:00") is None)
    check("abc invalid", ts._parse_hhmm("pagi") is None)

    # ── [3] compute_next_run ─────────────────────────────────────────────────
    print("\n[3] compute_next_run()")
    now = time.time()
    n1 = ts.compute_next_run({"every_minutes": 30, "last_run": 0}, now)
    check("interval → now+30m", 1799 < n1 - now <= 1801)
    lt = time.localtime(now)
    n2 = ts.compute_next_run({"at": "23:59"}, now)
    check("at hari ini/tomorrow > now", n2 > now)
    n3 = ts.compute_next_run({"every_minutes": 30, "last_run": now - 7200}, now)
    check("interval terlewat → dari sekarang", 0 < n3 - now <= 1801)
    n4 = ts.compute_next_run({"at": "00:00"}, now)
    check("at lewat → besok", n4 > now and n4 - now <= 86400)

    # ── [4] add() validasi ───────────────────────────────────────────────────
    print("\n[4] add() validasi input")
    _, _, e1 = ts.add("", "goal", GOOD_STEPS, every_minutes=10)
    check("nama kosong ditolak", bool(e1))
    _, _, e2 = ts.add("x", "", GOOD_STEPS, every_minutes=10)
    check("goal kosong ditolak", bool(e2))
    _, _, e3 = ts.add("x", "goal", [], every_minutes=10)
    check("steps kosong ditolak", bool(e3))
    _, _, e4 = ts.add("x", "goal", [{"params": {}}], every_minutes=10)
    check("langkah tanpa skill ditolak", bool(e4))
    _, _, e5 = ts.add("x", "goal", GOOD_STEPS)
    check("tanpa spec waktu ditolak", bool(e5))
    _, _, e6 = ts.add("x", "goal", GOOD_STEPS, at="25:99")
    check("format jam salah ditolak", bool(e6))

    # ── [5] add() sukses + persisten + anti duplikat ─────────────────────────
    print("\n[5] add() sukses & persisten")
    s, created, err = ts.add("tes-backup", "backup workspace", GOOD_STEPS,
                             at="07:00", risk_level="low")
    check("jadwal dibuat", created and not err and s.get("schedule_id"))
    check("tersimpan di file", TMP_SCHED.exists()
          and "tes-backup" in TMP_SCHED.read_text(encoding="utf-8"))
    s2, created2, _ = ts.add("tes-backup", "backup workspace", GOOD_STEPS, at="07:00")
    check("duplikat ditolak (anti double)", not created2 and s2.get("schedule_id") == s["schedule_id"])
    check("get() menemukan", ts.get("tes-backup") is not None
          and ts.get(s["schedule_id"]) is not None)

    # ── [6] enable / disable / remove ────────────────────────────────────────
    print("\n[6] enable / disable / remove")
    ts.add("tes-interval", "tes interval", GOOD_STEPS, every_minutes=5)
    dis = ts.set_enabled("tes-interval", False)
    check("disable bekerja", dis is not None and dis["enabled"] is False)
    en = ts.set_enabled("tes-interval", True)
    check("enable → next_run dihitung ulang", en["enabled"] is True and en["next_run"] > time.time())
    check("remove bekerja", ts.remove("tes-interval") and ts.get("tes-interval") is None)

    # ── [7] tick: belum jatuh tempo ──────────────────────────────────────────
    print("\n[7] tick() belum jatuh tempo")
    ts.add("tes-future", "belum waktunya", GOOD_STEPS, every_minutes=60)
    out = ts.tick()
    check("0 jadwal jatuh tempo", "0 jadwal jatuh tempo" in out)
    check("sebut jumlah terdaftar", "terdaftar" in out)

    # ── [8] tick: jatuh tempo → eksekusi via orchestrator ────────────────────
    print("\n[8] tick() jatuh tempo (eksekusi nyata)")
    s_due, _, _ = ts.add("tes-due", "analisa workspace", GOOD_STEPS, every_minutes=30)
    with ts._lock:
        rows = ts._load()
        for r in rows:
            if r["schedule_id"] == s_due["schedule_id"]:
                r["next_run"] = 0.0        # paksa jatuh tempo
        ts._save(rows)
    out = ts.tick()
    check("tick menembak 1 jadwal", "1 jadwal jatuh tempo" in out)
    s_after = ts.get("tes-due")
    check("run_count naik", s_after.get("run_count", 0) == 1)
    check("last_run dimajukan (anti re-trigger)", float(s_after.get("last_run") or 0) > 0)
    check("next_run di masa depan", float(s_after.get("next_run") or 0) > time.time())

    # ── [9] tick: skill tidak ada → klasifikasi gagal jujur ──────────────────
    print("\n[9] Klasifikasi gagal jujur")
    s_bad, _, _ = ts.add("tes-bad", "skill ngawur",
                         [{"skill": "skill_tidak_ada_xyz", "params": {}}],
                         every_minutes=30)
    with ts._lock:
        rows = ts._load()
        for r in rows:
            if r["schedule_id"] == s_bad["schedule_id"]:
                r["next_run"] = 0.0
        ts._save(rows)
    out = ts.tick()
    s_bad_after = ts.get("tes-bad")
    check("fail_count naik", s_bad_after.get("fail_count", 0) == 1)
    check("laporan pakai ❌", "❌" in out)

    # ── [10] Wrapper: read-only + 3 gerbang ──────────────────────────────────
    print("\n[10] Wrapper task_scheduler_skill")
    out = tss.task_scheduler_skill({"cmd": "list"})
    check("wrapper list jalan", "tes-due" in out or "tes-backup" in out or "Tidak ada" in out)
    out = tss.task_scheduler_skill({"cmd": "ngasal"})
    check("cmd asing → bantuan", "Task Scheduler Skill" in out)

    trigger(reason="test tahap11", by="test")
    out = tss.task_scheduler_skill({"cmd": "add", "name": "x-estop", "goal": "g",
                                    "steps": GOOD_STEPS, "every_minutes": 5})
    check("emergency stop memblokir add", out.startswith("⛔"))
    resume(by="test")

    out = tss.task_scheduler_skill({"cmd": "add", "name": "tes-wrapper",
                                    "goal": "dari wrapper", "steps": GOOD_STEPS,
                                    "every_minutes": 15})
    check("wrapper add sukses", out.startswith("✅") and ts.get("tes-wrapper") is not None)
    out = tss.task_scheduler_skill({"cmd": "remove", "name": "tes-wrapper"})
    check("wrapper remove sukses", "dihapus" in out and ts.get("tes-wrapper") is None)

    # ── [11] Audit jejak ─────────────────────────────────────────────────────
    print("\n[11] Audit jejak scheduler")
    found_tick = found_manage = False
    if AUDIT_PATH.exists():
        for line in AUDIT_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("skill") == "task_scheduler" and ev.get("action") == "scheduler.tick":
                found_tick = True
            if (ev.get("skill") == "task_scheduler_skill"
                    and ev.get("action") == "scheduler.manage"
                    and ev.get("result") == "success"):
                found_manage = True
            if found_tick and found_manage:
                break
    check("audit scheduler.tick ada", found_tick)
    check("audit scheduler.manage (wrapper) ada", found_manage)

    # ── [12] SkillHub kedua otak ─────────────────────────────────────────────
    print("\n[12] SkillHub kedua otak")
    check("task_scheduler_skill terdaftar", skill_hub.has("task_scheduler_skill"))
    decls = [x["name"] for x in skill_hub.get_tool_declarations()]
    check("deklarasi tool utk otak", "task_scheduler_skill" in decls)
    cat = skill_hub.get_hermes_catalog()
    check("katalog Hermes sebut task_scheduler_skill", "task_scheduler_skill" in cat)
    out = skill_hub.run("task_scheduler_skill", {"cmd": "list"})
    check("dispatch via hub jalan", "jadwal" in out.lower())

finally:
    ts.SCHED_PATH = ORIG_SCHED
    if TMP_SCHED.exists():
        TMP_SCHED.unlink()

print("\n" + "=" * 64)
print(f"HASIL: {passed} PASS, {failed} FAIL dari {passed + failed} cek")
print("=" * 64)
sys.exit(0 if failed == 0 else 1)
