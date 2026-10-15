# test_tahap13.py — Intent Classifier (blueprint §6-ish)
# Jalankan: python scratch\test_tahap13.py
from __future__ import annotations

import json
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
print("TAHAP 13 — INTENT CLASSIFIER (task vs chat vs question vs stop)")
print("=" * 64)

from core import intent_classifier as ic       # noqa: E402
from core.policy_engine import decide as _decide  # noqa: E402
from core.skill_hub import skill_hub           # noqa: E402
from skills.admin import intent_classifier_skill as ics  # noqa: E402
from skills.admin.emergency_stop import trigger, resume  # noqa: E402

AUDIT_PATH = Path(__file__).resolve().parent.parent / "audit" / "events.jsonl"

# ── [1] Policy ───────────────────────────────────────────────────────────────
print("\n[1] Policy intent.classify")
d = _decide("intent.classify")
check("intent.classify terdecide", d.get("decision") in ("allow", "confirm", "deny"))
check("intent.classify allow", d.get("decision") == "allow")

# ── [2] classify(): task ─────────────────────────────────────────────────────
print("\n[2] classify() → task")
r = ic.classify("rapikan desktop ku", use_llm=False)
check("rapikan desktop → task", r["intent"] == "task" and r["confidence"] >= 0.5)
r = ic.classify("bukain aplikasi spotify", use_llm=False)
check("bukain aplikasi → task", r["intent"] == "task")
r = ic.classify("backup folder core tiap hari jam 07:00", use_llm=False)
check("backup + jadwal → task", r["intent"] == "task")
r = ic.classify("matikan semua window chrome", use_llm=False)
check("matikan window → task", r["intent"] == "task")
r = ic.classify("buat jadwal backup setiap 30 menit", use_llm=False)
check("setiap 30 menit → task", r["intent"] == "task")

# ── [3] classify(): chat ─────────────────────────────────────────────────────
print("\n[3] classify() → chat")
for t in ("halo", "hai", "apa kabar?", "makasih ya", "ok", "kamu bisa apa aja?"):
    r = ic.classify(t, use_llm=False)
    check(f"'{t}' → chat", r["intent"] == "chat")

# ── [4] classify(): question ─────────────────────────────────────────────────
print("\n[4] classify() → question")
r = ic.classify("apa itu python?", use_llm=False)
check("apa itu X? → question", r["intent"] == "question")
r = ic.classify("berapa lama backup kemarin", use_llm=False)
check("berapa lama → question", r["intent"] == "question")
r = ic.classify("kamu bisa buka kamera?", use_llm=False)
check("bisa kamu → question/chat (bukan task)", r["intent"] in ("question", "chat"))
r = ic.classify("siapa presiden indonesia?", use_llm=False)
check("siapa → question", r["intent"] == "question")

# ── [5] Stop phrase prioritas ────────────────────────────────────────────────
print("\n[5] Stop phrase prioritas")
from skills.admin.emergency_stop import STOP_PHRASES  # noqa: E402
if STOP_PHRASES:
    sp = str(sorted(STOP_PHRASES, key=len, reverse=True)[0])
    r = ic.classify(sp, use_llm=False)
    check(f"stop phrase '{sp}' → stop", r["intent"] == "stop" and r["is_stop"])
else:
    check("STOP_PHRASES tersedia utk uji", False)

# ── [6] Ambigu → jujur (LLM tak tersedia) ────────────────────────────────────
print("\n[6] Ambigu → jujur unknown")
r = ic.classify("xyzzy", use_llm=True)
check("teks ngawal → unknown / question aman", r["intent"] in ("unknown", "question"))
check("ada method tercatat", r.get("method") in ("rule", "llm"))
r = ic.classify("", use_llm=False)
check("teks kosong → unknown", r["intent"] == "unknown")

# ── [7] is_task() shortcut ───────────────────────────────────────────────────
print("\n[7] is_task() shortcut")
check("rapikan → task True", ic.is_task("rapikan desktop"))
check("halo → task False", not ic.is_task("halo"))

# ── [8] fmt_result() ─────────────────────────────────────────────────────────
print("\n[8] fmt_result()")
out = ic.fmt_result(ic.classify("backup folder", use_llm=False), "backup folder")
check("fmt sebut intent", "TASK" in out)
out = ic.fmt_result({"intent": "unknown", "confidence": 0.3, "method": "rule",
                     "is_stop": False, "suggest": "tanya ulang"}, "xyzzy")
check("fmt sebut saran", "Saran" in out)

# ── [9] Handler TOOL ─────────────────────────────────────────────────────────
print("\n[9] Handler intent_classifier")
out = ic.intent_classifier({"cmd": "classify", "text": "rapikan desktop"})
check("handler classify", "TASK" in out)
out = ic.intent_classifier({"cmd": "is_task", "text": "halo"})
check("handler is_task", "BUKAN" in out)
out = ic.intent_classifier({"cmd": "ngasal"})
check("cmd asing → bantuan", "Intent Classifier" in out)
out = ic.intent_classifier({"cmd": "classify", "text": ""})
check("teks kosong → petunjuk", "Sebutkan" in out)

# ── [10] Wrapper 3 gerbang ───────────────────────────────────────────────────
print("\n[10] Wrapper intent_classifier_skill")
out = ics.intent_classifier_skill({"cmd": "classify", "text": "rapikan desktop"})
check("wrapper classify", "TASK" in out)
out = ics.intent_classifier_skill({"cmd": "ngasal"})
check("cmd asing → bantuan", "Intent Classifier Skill" in out)
trigger(reason="test tahap13", by="test")
out = ics.intent_classifier_skill({"cmd": "classify", "text": "halo"})
check("emergency stop memblokir", out.startswith("⛔"))
resume(by="test")
out = ics.intent_classifier_skill({"cmd": "classify", "text": "halo"})
check("resume → jalan lagi", "CHAT" in out)

# ── [11] Audit jejak ─────────────────────────────────────────────────────────
print("\n[11] Audit jejak intent.classify")
found = False
if AUDIT_PATH.exists():
    for line in AUDIT_PATH.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            ev = json.loads(line)
        except Exception:
            continue
        if (ev.get("skill") == "intent_classifier_skill"
                and ev.get("action") == "intent.classify"
                and ev.get("result") == "success"):
            found = True
            break
check("audit intent.classify ada", found)

# ── [12] SkillHub kedua otak ─────────────────────────────────────────────────
print("\n[12] SkillHub kedua otak")
check("intent_classifier_skill terdaftar", skill_hub.has("intent_classifier_skill"))
decls = [x["name"] for x in skill_hub.get_tool_declarations()]
check("deklarasi tool utk otak", "intent_classifier_skill" in decls)
cat = skill_hub.get_hermes_catalog()
check("katalog Hermes sebut intent_classifier_skill", "intent_classifier_skill" in cat)
out = skill_hub.run("intent_classifier_skill", {"cmd": "classify", "text": "buka notepad"})
check("dispatch via hub jalan", "TASK" in out)

print("\n" + "=" * 64)
print(f"HASIL: {passed} PASS, {failed} FAIL dari {passed + failed} cek")
print("=" * 64)
sys.exit(0 if failed == 0 else 1)
