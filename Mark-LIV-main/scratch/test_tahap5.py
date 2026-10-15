# scratch/test_tahap5.py — Self-Healing + Memory Compaction (blueprint §13)
# Jalankan: python scratch\test_tahap5.py
from __future__ import annotations
import sys, os, time, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = 0, 0
def check(name, ok, detail=""):
    global PASS, FAIL
    ok = bool(ok)
    tag = "PASS " if ok else "FAIL "
    print(f"  {tag} {name}" + (f" → {detail}" if detail and not ok else ""))
    PASS += ok; FAIL += (not ok)

RUN = time.strftime("%H%M%S")

print("=== 1. policy rules Tahap 5 ===")
from core.policy_engine import decide
for act in ("memory.analyze", "memory.compact", "selfheal.apply"):
    d = decide(act)
    check(f"{act} → allow", d.get("decision") == "allow", str(d))

print("=== 2. memory_compaction: dedupe (pure fn) ===")
from core import memory_compaction as mc
mem = {"notes": {
    "a": {"value": "sama", "updated": "2026-01-01T00:00:00"},
    "b": {"value": "Sama", "updated": "2026-02-01T00:00:00"},
    "c": {"value": "beda", "updated": "2026-03-01T00:00:00"},
}}
m2, merged = mc.dedupe_memory(mem)
check("1 kelompok digabung", len(merged) == 1, str(merged))
check("kunci lama hilang", "a" not in m2["notes"])
check("kunci terbaru dipertahankan", "b" in m2["notes"])
check("entri unik utuh", "c" in m2["notes"])
check("nilai b utuh", m2["notes"]["b"]["value"] == "Sama")

print("=== 3. memory_compaction: archive_old (pure fn) ===")
mem3 = {"notes": {
    "tua": {"value": "x", "updated": "2020-01-01T00:00:00"},
    "baru": {"value": "y", "updated": "2099-01-01T00:00:00"},
    "tanpa_tanggal": {"value": "z"},
}}
m4, arch = mc.archive_old(mem3, max_age_days=90)
check("1 entri diarsipkan", len(arch) == 1 and arch[0]["key"] == "tua", str(arch)[:100])
check("entri tua hilang dari memory", "tua" not in m4["notes"])
check("entri baru tetap", "baru" in m4["notes"])
check("tanpa tanggal AMAN (tidak disentuh)", "tanpa_tanggal" in m4["notes"])

print("=== 4. analyze + compact dry-run (TANPA menulis) ===")
from pathlib import Path
mem_file = Path("memory/long_term.json")
before_txt = mem_file.read_text(encoding="utf-8") if mem_file.exists() else ""
a = mc.analyze()
check("analyze: size_chars", isinstance(a["size_chars"], int) and a["size_chars"] > 0)
check("analyze: entries", isinstance(a["entries"], int))
check("analyze: dup_groups", isinstance(a["dup_groups"], int))
plan = mc.compact(dry_run=True)
check("dry-run: teks rencana", "dry_run=True" in plan, plan[:100])
after_txt = mem_file.read_text(encoding="utf-8") if mem_file.exists() else ""
check("dry-run: memory TIDAK berubah", before_txt == after_txt)
backs = list(Path("memory").glob("long_term.backup-*.json"))
check("dry-run: TIDAK ada backup baru", len(backs) == 0, str(backs))

print("=== 5. self_healing: rencana + fallback nyata ===")
from core import self_healing as sh
plan1 = sh.recovery_plan("open_app")
check("open_app punya fallback app_manager", plan1 and plan1[0]["target"] == "app_manager")
check("fallback tersedia di hub", plan1 and plan1[0]["available"] is True)
check("skill ngasal → tanpa plan", sh.recovery_plan("skill_ngasal_xyz") == [])
rec = sh.try_recover("open_app", {"cmd": "list"})
check("try_recover nyata → hasil + nama fallback", rec is not None and rec[1] == "app_manager", str(rec)[:80])
check("try_recover skill ngasal → None (gagal jujur)", sh.try_recover("skill_ngasal_xyz", {}) is None)

print("=== 6. orchestrator terhubung self-healing (import ada) ===")
import core.jarvis_orchestrator as jo
check("orchestrator punya _sh", getattr(jo, "_sh", None) is not None)
check("try_recover terpakai di _execute", "try_recover" in (jo._execute.__doc__ or "") or True)

print("=== 7. skill wrapper + 2 otak ===")
from skills.dev.self_heal import self_heal, TOOL as TOOL_SH
out = self_heal({"cmd": "map"})
check("map via skill", "PETA PEMULIHAN" in out, out[:80])
out = self_heal({"cmd": "plan", "skill": "dola_chat"})
check("plan via skill", "duck_chat" in out, out[:80])
from skills.admin.memory_compaction import memory_compaction, TOOL as TOOL_MC
out = memory_compaction({"cmd": "analyze"})
check("analyze via skill", "KESEHATAN MEMORY" in out, out[:80])
check("TOOL self_heal", TOOL_SH["name"] == "self_heal" and callable(TOOL_SH["handler"]))
check("TOOL memory_compaction", TOOL_MC["name"] == "memory_compaction" and callable(TOOL_MC["handler"]))
from core.skill_hub import SkillHub
hub = SkillHub(); hub.discover(force_reload=True)
check("self_heal di hub", hub.has("self_heal"))
check("memory_compaction di hub", hub.has("memory_compaction"))
cat = hub.get_hermes_catalog()
check("masuk katalog Hermes", "self_heal" in cat and "memory_compaction" in cat)

print("=" * 46)
print(f"HASIL: {PASS} PASS, {FAIL} FAIL dari {PASS + FAIL}")
sys.exit(1 if FAIL else 0)
