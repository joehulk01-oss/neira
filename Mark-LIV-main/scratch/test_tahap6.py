# test_tahap6.py — Workflow Engine (Blueprint Tahap 6)
# Jalankan: cd Mark-LIV-main && python scratch\test_tahap6.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

PASS = 0
FAIL = 0


def check(label: str, ok) -> None:
    global PASS, FAIL
    ok = bool(ok)
    if ok:
        PASS += 1
        print(f"  PASS  {label}")
    else:
        FAIL += 1
        print(f"  FAIL  {label}")


print("=" * 64)
print("TAHAP 6 — WORKFLOW ENGINE (blueprint: workflow multi-langkah YAML)")
print("=" * 64)

# ── 1. Policy rule workflow.run ──────────────────────────────────────────────
print("\n[1] Policy rule workflow.run")
from core.policy_engine import decide as decide

d = decide("workflow.run", target="morning_briefing")
check("workflow.run ada di policy", d.get("decision") in ("allow", "confirm"))
check("workflow.run risk terdaftar", d.get("risk") in ("low", "medium", "high", "critical"))
d_unknown = decide("workflow.run", target="")
check("target kosong tetap terdecide (bukan error)", "decision" in d_unknown)

# ── 2. Loader: load / list / validasi ────────────────────────────────────────
print("\n[2] Loader workflow YAML")
from core import workflow_engine as we

wf = we.load("morning_briefing")
check("load morning_briefing → dict", isinstance(wf, dict))
check("wf punya name", wf.get("name") == "morning_briefing")
check("wf punya steps non-kosong", isinstance(wf.get("steps"), list) and len(wf["steps"]) >= 2)
check("wf punya risk_level", wf.get("risk_level") == "low")
wf2 = we.load("shutdown_routine")
check("load shutdown_routine → dict", isinstance(wf2, dict))
check("shutdown_routine risk high", wf2.get("risk_level") == "high")
check("load .yaml extension dinormalisasi", we.load("morning_briefing.yaml") is not None)
check("load tidak ada → None", we.load("tidak_ada_9999") is None)
check("path traversal diblokir → None", we.load("../secrets/config") is None)
check("path traversal backslash diblokir → None", we.load("..\\secrets") is None)
items = we.list_workflows()
names = {w["name"] for w in items}
check("list_workflows ≥ 2", len(items) >= 2)
check("list memuat morning_briefing", "morning_briefing" in names)
check("list memuat shutdown_routine", "shutdown_routine" in names)
check("list item punya jumlah steps", all(w.get("steps", 0) >= 1 for w in items))

# ── 3. Format list & show ────────────────────────────────────────────────────
print("\n[3] Format list & show")
txt = we.fmt_list(items)
check("fmt_list sebut morning_briefing", "morning_briefing" in txt)
check("fmt_list sebut jumlah langkah", "langkah" in txt)
show = we.fmt_show(wf)
check("fmt_show sebut skill pertama", "computer_awareness" in show)
check("fmt_show tampilkan expect", "expect" in show)
show2 = we.fmt_show(wf2)
check("fmt_show shutdown sebut app_manager", "app_manager" in show2)

# ── 4. Handler read-only workflow_engine ─────────────────────────────────────
print("\n[4] Handler core.workflow_engine (list|show)")
out = we.workflow_engine({"cmd": "list"})
check("cmd=list tampilkan workflow", "morning_briefing" in out)
out = we.workflow_engine({"cmd": "show", "name": "morning_briefing"})
check("cmd=show tampilkan detail", "risk_level" in out and "computer_awareness" in out)
out = we.workflow_engine({"cmd": "show", "name": "ngawur_404"})
check("show tidak ada → pesan sopan + daftar", "tidak ditemukan" in out and "morning_briefing" in out)
out = we.workflow_engine({"cmd": "ngaco"})
check("cmd asing → pesan bantuan", "tidak dikenal" in out)

# ── 5. RUN via orchestrator: morning_briefing end-to-end ─────────────────────
print("\n[5] Run workflow via orchestrator (jalur keamanan SAMA)")
from core import job_manager as jm

before = len(jm._load())
rep = we.run("morning_briefing")
check("run → laporan berisi goal workflow", "[workflow:morning_briefing]" in rep)
check("run → sukses marker", "🏁" in rep)
jobs = jm._load()
check("job workflow tercatat di job_manager", len(jobs) == before + 1)
job = jobs[-1] if jobs else {}
check("job status succeeded", job.get("status") == "succeeded")
check("semua langkah done", all(s.get("status") == "done" for s in job.get("steps", [])))
check("expect terbawa ke langkah", any("expect" in s for s in job.get("steps", [])))
check("laporan sebut verifikasi lolos", "unverified" not in rep)

# ── 6. Run workflow tidak ada → jujur ────────────────────────────────────────
print("\n[6] Run workflow fiktif → jujur gagal")
rep = we.run("workflow_fiktif_404")
check("laporkan tidak ditemukan", "tidak ditemukan" in rep)
check("tawarkan daftar yang ada", "morning_briefing" in rep)

# ── 7. workflow_manager: 3 gerbang ───────────────────────────────────────────
print("\n[7] workflow_manager: stop → policy → audit")
from skills.admin import workflow_manager as wm

out = wm.workflow_manager({"cmd": "list"})
check("wm list delegasi", "morning_briefing" in out)
out = wm.workflow_manager({"cmd": "show", "name": "shutdown_routine"})
check("wm show delegasi", "app_manager" in out)
out = wm.workflow_manager({"cmd": "ngaco"})
check("wm cmd asing → bantuan", "tidak dikenal" in out)

# emergency stop blokir run
from skills.admin import emergency_stop as es

es.trigger("test tahap6")
out = wm.workflow_manager({"cmd": "run", "name": "morning_briefing"})
check("emergency stop memblokir run", "EMERGENCY STOP" in out)
es.resume()
check("resume → bebas lagi", not es.is_stopped())

# run nyata via wm
out = wm.workflow_manager({"cmd": "run", "name": "morning_briefing"})
check("wm run nyata sukses", "🏁" in out and "[workflow:morning_briefing]" in out)

# ── 8. Audit jejak workflow ──────────────────────────────────────────────────
print("\n[8] Audit jejak workflow.run")
from core.audit_logger import tail as audit_tail

rows = audit_tail(12)
wf_rows = [r for r in rows if r.get("skill") == "workflow_manager"]
# Hanya run yang BENAR-BENAR dieksekusi yang diaudit; run yang diblokir
# emergency stop berhenti SEBELUM gerbang audit (by design).
check("ada audit workflow_manager", len(wf_rows) >= 1)
check("audit memuat action workflow.run", any(r.get("action") == "workflow.run" for r in wf_rows))

# ── 9. SkillHub: 2 otak melihat 3 tool baru ──────────────────────────────────
print("\n[9] SkillHub kedua otak (core/workflow_engine dijangkau via wrapper)")
from core.skill_hub import skill_hub as hub

check("workflow_manager terdaftar", hub.has("workflow_manager"))
check("workflow_engine TIDAK di skills/ (core punya handler sendiri)",
      not hub.has("workflow_engine"))
decls = {t["name"] for t in hub.get_tool_declarations()}
check("deklarasi tool utk otak", "workflow_manager" in decls)
catalog = hub.get_hermes_catalog()
check("katalog Hermes sebut workflow_manager", "workflow_manager" in catalog)
out = hub.run("workflow_manager", {"cmd": "list"})
check("dispatch via hub jalan", "morning_briefing" in out)
out = hub.run("workflow_manager", {"cmd": "show", "name": "morning_briefing"})
check("dispatch show via hub jalan", "risk_level" in out)

# ── RINGKASAN ────────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print(f"HASIL: {PASS} PASS, {FAIL} FAIL dari {PASS + FAIL} cek")
print("=" * 64)
sys.exit(0 if FAIL == 0 else 1)
