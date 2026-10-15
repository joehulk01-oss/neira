# test_tahap10.py — Context Engine (blueprint §5.4)
# Jalankan: python scratch\test_tahap10.py
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
print("TAHAP 10 — CONTEXT ENGINE (satu blok konteks + budget)")
print("=" * 64)

from core import context_engine as ce                    # noqa: E402
from core.policy_engine import decide as _decide         # noqa: E402
from core.skill_hub import skill_hub                     # noqa: E402
from skills.admin import context_engine_skill as ces     # noqa: E402
from skills.admin.emergency_stop import trigger, resume  # noqa: E402

AUDIT_PATH = Path(__file__).resolve().parent.parent / "audit" / "events.jsonl"

# ── [1] Policy ───────────────────────────────────────────────────────────────
print("\n[1] Policy context.build")
d = _decide("context.build")
check("context.build terdecide", d.get("decision") in ("allow", "confirm", "deny"))
check("context.build allow", d.get("decision") == "allow")

# ── [2] clip() ───────────────────────────────────────────────────────────────
print("\n[2] Pemotong aman _clip()")
check("teks pendek utuh", ce._clip("halo", 10) == "halo")
long = "\n".join(f"baris {i}" for i in range(100))
clipped = ce._clip(long, 50)
check("teks panjang terpotong", len(clipped) <= 50 + len("\n…(dipotong agar muat budget)"))
check("penanda dipotong ada", "dipotong" in clipped)
check("putus di batas baris", clipped.count("\n") >= 1)

# ── [3] build() — struktur & budget ─────────────────────────────────────────
print("\n[3] build() struktur & budget")
text, rep = ce.build("backup core", max_chars=4000)
check("5 seksi ada", all(k in rep["sections"] for k in
                         ("awareness", "tasks", "memory", "sessions", "metrics")))
check("total ≤ budget 4000", rep["total_chars"] <= 4000)
check("header awareness ada", "=== KONDISI PC ===" in text)
check("header tasks ada", "=== TUGAS TERAKHIR ===" in text)
check("header memory ada", "=== MEMORI RELEVAN ===" in text)
check("header sessions ada", "=== SESI SEBELUMNYA ===" in text)
check("header metrics ada", "=== METRIK SISTEM ===" in text)

text_small, rep_small = ce.build("", max_chars=600)
check("budget kecil tetap dihormati", rep_small["total_chars"] <= 600)
check("budget min 600 dipaksa", ce.build("", max_chars=10)[1]["budget"] == 600)

# ── [4] build() — sumber nyata terisi ────────────────────────────────────────
print("\n[4] Sumber nyata terisi")
_, rep = ce.build("", max_chars=4000)
check("awareness included", rep["sections"]["awareness"]["included"])
check("metrics included", rep["sections"]["metrics"]["included"])
text, _ = ce.build("", max_chars=4000)
check("metrics berisi false success", "false success" in text.lower())

# ── [5] format_report() ──────────────────────────────────────────────────────
print("\n[5] format_report()")
r = ce.format_report(rep)
check("report sebut total", "Konteks" in r)
check("report sebut nama seksi", "awareness" in r and "metrics" in r)

# ── [6] Integrasi anti-bohong: sumber rusak → jujur ─────────────────────────
print("\n[6] Sumber gagal → jujur")
def _boom(q):
    raise RuntimeError("simulasi rusak")
orig = ce._SECTIONS[1][2]
ce._SECTIONS[1] = ("tasks", 0.25, _boom)
try:
    text_bad, rep_bad = ce.build("", max_chars=2000)
    check("seksi gagal → tidak included", not rep_bad["sections"]["tasks"]["included"])
    check("seksi gagal → ditandai jujur", "(tidak tersedia" in text_bad)
finally:
    ce._SECTIONS[1] = ("tasks", 0.25, orig)

# ── [7] Handler TOOL ─────────────────────────────────────────────────────────
print("\n[7] Handler context_engine")
out = ce.context_engine({"cmd": "build", "query": "kondisi laptop"})
check("handler build → konteks", "=== KONDISI PC ===" in out)
check("handler build → report di ekor", "Konteks" in out)
out = ce.context_engine({"cmd": "stats"})
check("handler stats → ringkasan", out.startswith("Konteks"))
out = ce.context_engine({"cmd": "ngasal"})
check("cmd asing → bantuan", "Context Engine" in out)

# ── [8] Wrapper skill: 3 gerbang ─────────────────────────────────────────────
print("\n[8] Wrapper context_engine_skill")
out = ces.context_engine_skill({"cmd": "build", "query": "test"})
check("wrapper build → konteks", "=== KONDISI PC ===" in out)
out = ces.context_engine_skill({"cmd": "stats"})
check("wrapper stats → ringkasan", out.startswith("Konteks"))
out = ces.context_engine_skill({"cmd": "bantuan"})
check("cmd asing → bantuan", "Context Engine Skill" in out)

trigger(reason="test tahap10", by="test")
out = ces.context_engine_skill({"cmd": "build"})
check("emergency stop memblokir", out.startswith("⛔"))
resume(by="test")

# ── [9] Audit jejak ──────────────────────────────────────────────────────────
print("\n[9] Audit jejak context engine")
found = False
if AUDIT_PATH.exists():
    for line in AUDIT_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if (ev.get("skill") == "context_engine_skill"
                and ev.get("action") == "context.build"):
            found = True
            break
check("audit context.build ada", found)

# ── [10] SkillHub kedua otak ────────────────────────────────────────────────
print("\n[10] SkillHub kedua otak")
check("context_engine_skill terdaftar", skill_hub.has("context_engine_skill"))
decls = [x["name"] for x in skill_hub.get_tool_declarations()]
check("deklarasi tool utk otak", "context_engine_skill" in decls)
cat = skill_hub.get_hermes_catalog()
check("katalog Hermes sebut context_engine_skill", "context_engine_skill" in cat)
out = skill_hub.run("context_engine_skill", {"cmd": "stats"})
check("dispatch via hub jalan", out.startswith("Konteks"))

print("\n" + "=" * 64)
print(f"HASIL: {passed} PASS, {failed} FAIL dari {passed + failed} cek")
print("=" * 64)
sys.exit(0 if failed == 0 else 1)
