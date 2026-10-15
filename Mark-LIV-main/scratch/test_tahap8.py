# test_tahap8.py — Task Planner (niat → langkah → eksekusi terkontrol)
# Jalankan: python scratch\test_tahap8.py
from __future__ import annotations

import json
import sys
from pathlib import Path

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
print("TAHAP 8 — TASK PLANNER (plan / validate / execute)")
print("=" * 64)

from core import task_planner as tp                      # noqa: E402
from core.policy_engine import decide as _decide         # noqa: E402
from core.audit_logger import log_event as _audit        # noqa: E402
from core.skill_hub import skill_hub                     # noqa: E402
from skills.admin import task_planner_agent as tpa       # noqa: E402
from skills.admin.emergency_stop import trigger, resume  # noqa: E402

AUDIT_PATH = Path(__file__).resolve().parent.parent / "audit" / "events.jsonl"

# ── [1] Policy rules planner.* ───────────────────────────────────────────────
print("\n[1] Policy planner.plan / planner.execute")
d1 = _decide("planner.plan")
d2 = _decide("planner.execute")
check("planner.plan terdecide", d1.get("decision") in ("allow", "confirm", "deny"))
check("planner.plan allow", d1.get("decision") == "allow")
check("planner.execute allow", d2.get("decision") == "allow")
check("planner.execute risk medium", d2.get("risk") == "medium")
check("aksi asing tetap default", _decide("planner.ngasal").get("decision") == "allow")

# ── [2] parse_plan_json ──────────────────────────────────────────────────────
print("\n[2] Parser JSON plan")
check("parse polos", (tp.parse_plan_json('{"steps":[{"skill":"echo"}]}') or []) ==
      [{"skill": "echo"}])
check("parse dikelilingi teks", tp.parse_plan_json('Ini plannya:\n{"steps":[]}') == [])
check("parse bukan json → None", tp.parse_plan_json("saya tidak paham") is None)
check("parse tanpa steps → None", tp.parse_plan_json('{"halo":1}') is None)
check("parse rusak → None", tp.parse_plan_json('{"steps":[broken') is None)
check("parse steps bukan list → None", tp.parse_plan_json('{"steps":"dua"}') is None)

# ── [3] validate_steps ───────────────────────────────────────────────────────
print("\n[3] Validasi langkah")
good = [{"skill": "workspace_dev", "params": {"cmd": "analyze"}},
        {"skill": "memory_compaction", "params": {"cmd": "analyze"}}]
clean, errors = tp.validate_steps(good)
check("plan bagus → tanpa error", not errors)
check("plan bagus → 2 langkah", len(clean) == 2)
check("params dipertahankan", clean[0]["params"] == {"cmd": "analyze"})

check("plan kosong → ditolak", tp.validate_steps([])[1] != [])
check("plan bukan list → ditolak", tp.validate_steps("halo")[1] != [])
check("plan 11 langkah → ditolak", tp.validate_steps(
    [{"skill": "echo"}] * 11)[1] != [])

bad_skill, errs = tp.validate_steps([{"skill": "skill_tidak_ada_xyz", "params": {}}])
check("skill ngasal → error", any("tidak terdaftar" in e for e in errs))
check("skill ngasal → tidak ada langkah bersih", bad_skill == [])

noshape, errs = tp.validate_steps(["bukan-dict", {"params": {}}, {}])
check("bentuk salah → error per langkah", len(errs) == 3)

badact, errs = tp.validate_steps(
    [{"skill": "workspace_dev", "params": {}, "policy_action": "aksi.ngasal.aja"}])
check("policy_action ngasal → ditolak", any("tidak dikenal" in e for e in errs))

okact, errs = tp.validate_steps(
    [{"skill": "workspace_dev", "params": {"cmd": "backup", "target": "core"},
      "policy_action": "workspace.backup"}])
check("policy_action dikenal → lolos", not errs and len(okact) == 1)

alias, errs = tp.validate_steps(
    [{"skill": "workspace_dev", "parameters": {"cmd": "analyze"}}])
check("alias 'parameters' diterima", not errs and alias[0]["params"] == {"cmd": "analyze"})

# ── [4] fmt_plan ─────────────────────────────────────────────────────────────
print("\n[4] Format plan")
txt = tp.fmt_plan(good)
check("fmt_plan tampil", "PLAN" in txt and "workspace_dev" in txt)
check("fmt_plan kosong jujur", tp.fmt_plan([]) == "(plan kosong)")

# ── [5] Katalog skill dari skill_hub ────────────────────────────────────────
print("\n[5] Katalog skill")
cat = tp.skill_catalog()
check("katalog tidak kosong", len(cat) > 100)
check("katalog sebut workspace_dev", "workspace_dev" in cat)
check("katalog sebut orchestrator", "orchestrator" in cat.lower())

# ── [6] Wrapper: validate read-only ─────────────────────────────────────────
print("\n[6] Wrapper validate (read-only)")
out = tpa.task_planner_agent({"cmd": "validate", "steps": good})
check("validate bagus → ✅", out.startswith("✅"))
out = tpa.task_planner_agent({"cmd": "validate", "steps": [{"skill": "ngasal_x"}]})
check("validate jelek → ❌", out.startswith("❌"))
out = tpa.task_planner_agent({"cmd": "bantuan"})
check("cmd asing → bantuan", "Task Planner Agent" in out)
out = tpa.task_planner_agent({"cmd": "plan", "goal": "uji audit plan tahap 8"})
check("plan via wrapper → jujur (✅/❌)", out.startswith(("✅", "❌")))

# ── [7] Wrapper execute: 3 gerbang ──────────────────────────────────────────
print("\n[7] Wrapper execute — stop → policy → audit")
out = tpa.task_planner_agent({"cmd": "execute", "goal": "uji", "steps": good})
check("tanpa confirm → tampilkan plan", out.startswith("⚠️") and "PLAN" in out)

trigger(reason="test tahap8", by="test")
out = tpa.task_planner_agent({"cmd": "execute", "goal": "uji", "steps": good,
                              "confirm": True})
check("emergency stop memblokir", out.startswith("⛔") and "EMERGENCY STOP" in out)
resume(by="test")

plan_rusak = [{"skill": "ngasal_tidak_ada", "params": {}}]
out = tpa.task_planner_agent({"cmd": "execute", "goal": "uji",
                              "steps": plan_rusak, "confirm": True})
check("plan invalid ditolak sebelum gerbang", out.startswith("❌"))

before = AUDIT_PATH.stat().st_size if AUDIT_PATH.exists() else 0
steps_sukses = [{"skill": "memory_compaction", "params": {"cmd": "analyze"}}]
out = tpa.task_planner_agent({"cmd": "execute", "goal": "uji planner tahap 8",
                              "steps": steps_sukses, "confirm": True})
check("execute valid → job sukses", "succeeded" in out.lower())
after = AUDIT_PATH.stat().st_size if AUDIT_PATH.exists() else 0
check("audit tumbuh setelah execute", after > before)

# ── [8] Audit jejak planner ─────────────────────────────────────────────────
print("\n[8] Audit jejak planner")
found = {"plan": False, "execute": False, "blocked": False}
if AUDIT_PATH.exists():
    for line in AUDIT_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        sk = ev.get("skill", "")
        if sk == "task_planner_agent":
            act = ev.get("action", "")
            if act == "planner.plan":
                found["plan"] = True
            if act == "planner.execute" and ev.get("result") == "success":
                found["execute"] = True
            if act == "planner.execute" and ev.get("result") == "blocked_emergency_stop":
                found["blocked"] = True
check("audit planner.plan ada", found["plan"])
check("audit planner.execute ada", found["execute"])
check("audit emergency-stop tercatat", found["blocked"])

# ── [9] plan() — LLM lokal (jujur kalau tidak ada LLM) ──────────────────────
print("\n[9] plan() via LLM lokal (atau jujur gagal)")
steps, msg = tp.plan("cek kesehatan repo lalu analisis memory")
llm_ok = steps != [] and "plan valid" in msg
llm_absent = steps == [] and any(
    k in msg for k in ("LLM gagal", "LLM client", "bukan JSON", "ditolak validasi"))
check("plan: sukses ATAU jujur gagal", llm_ok or llm_absent)
check("plan: steps divalidasi (skill nyata) jika sukses",
      (not llm_ok) or all(skill_hub.has(s["skill"]) for s in steps))
check("plan: goal kosong ditolak", tp.plan("  ")[1] == "goal kosong")
check("plan: steps ≤ MAX_STEPS jika sukses", (not llm_ok) or len(steps) <= tp.MAX_STEPS)

# ── [10] SkillHub kedua otak ────────────────────────────────────────────────
print("\n[10] SkillHub kedua otak")
check("task_planner_agent terdaftar", skill_hub.has("task_planner_agent"))
decls = [d["name"] for d in skill_hub.get_tool_declarations()]
check("deklarasi tool utk otak", "task_planner_agent" in decls)
cat = skill_hub.get_hermes_catalog()
check("katalog Hermes sebut task_planner_agent", "task_planner_agent" in cat)
out = skill_hub.run("task_planner_agent", {"cmd": "validate", "steps": good})
check("dispatch via hub jalan", out.startswith("✅"))

print("\n" + "=" * 64)
print(f"HASIL: {passed} PASS, {failed} FAIL dari {passed + failed} cek")
print("=" * 64)
sys.exit(0 if failed == 0 else 1)
