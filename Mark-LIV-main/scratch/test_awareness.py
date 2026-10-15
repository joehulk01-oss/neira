# scratch/test_awareness.py — Tahap 3 Computer Awareness
# Jalankan: python scratch\test_awareness.py
from __future__ import annotations
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PASS, FAIL = 0, 0
def check(name, ok, detail=""):
    global PASS, FAIL
    ok = bool(ok)
    tag = "PASS " if ok else "FAIL "
    print(f"  {tag} {name}" + (f" → {detail}" if detail and not ok else ""))
    PASS += ok; FAIL += (not ok)

print("=== 1. policy rules Tahap 3 dimuat ===")
from core.policy_engine import decide, load_policy
p = load_policy()
for act, want in [("window.list", "allow"), ("window.active", "allow"),
                  ("window.focus", "allow"), ("window.minimize", "allow"),
                  ("window.close", "confirm"), ("awareness.snapshot", "allow")]:
    d = decide(act)
    check(f"{act} → {want}", d.get("decision") == want, str(d))

print("=== 2. core.computer_awareness snapshot ===")
from core.computer_awareness import snapshot, format_snapshot, active_window, window_entries
snap = snapshot()
check("snapshot dict", isinstance(snap, dict) and snap.get("taken_at"))
check("cpu terukur", isinstance(snap.get("cpu_percent"), (int, float)))
check("mem terukur", isinstance(snap.get("mem_percent"), (int, float)))
check("screen ada", snap.get("screen", {}).get("width", 0) > 0, str(snap.get("screen")))
check("active_window ada", "title" in (snap.get("active_window") or {}))
check("windows list", isinstance(snap.get("windows"), list))
check("top_memory list", isinstance(snap.get("top_memory"), list))

txt = format_snapshot(snap)
check("format: judul", "KONDISI PC" in txt)
check("format: AKTIF", "AKTIF" in txt)
check("format: jendela", "JENDELA TERLIHAT" in txt)

print("=== 3. skill computer_awareness (handler + TOOL) ===")
from skills.admin.computer_awareness import computer_awareness, TOOL as TOOL_AW
out = computer_awareness({"cmd": "snapshot"})
check("snapshot via skill", "KONDISI PC" in out, out[:80])
out = computer_awareness({"cmd": "active"})
check("active via skill", "aktif" in out.lower(), out[:80])
out = computer_awareness({"cmd": "windows"})
check("windows via skill", "jendela" in out.lower(), out[:80])
out = computer_awareness({"cmd": "ngasal"})
check("cmd ngasal ditolak rapi", "tidak dikenal" in out.lower(), out[:80])
check("TOOL awareness", TOOL_AW["name"] == "computer_awareness" and callable(TOOL_AW["handler"]))

print("=== 4. window_manager: list + active ===")
from skills.admin.window_manager import window_manager, TOOL as TOOL_WM
out = window_manager({"cmd": "list"})
check("list jendela", "jendela terlihat" in out.lower(), out[:80])
out = window_manager({"cmd": "active"})
check("active window", "aktif" in out.lower(), out[:80])
check("TOOL window_manager", TOOL_WM["name"] == "window_manager" and callable(TOOL_WM["handler"]))

print("=== 5. window_manager: target tidak ada → pesan jelas (anti-bohong) ===")
RUN = time.strftime("%H%M%S")
out = window_manager({"cmd": "focus", "target": f"tidak-ada-{RUN}"})
check("focus gagal jujur", "tidak ditemukan" in out.lower(), out[:80])
out = window_manager({"cmd": "close", "target": f"tidak-ada-{RUN}", "confirm": True})
check("close gagal jujur", "tidak ditemukan" in out.lower(), out[:80])

print("=== 6. window.close butuh konfirmasi (policy confirm) ===")
# target 'tidak ditemukan' TAPI gate harus menahan SEBELUM pencarian:
out = window_manager({"cmd": "close", "target": f"apa-saja-{RUN}"})
check("close tanpa confirm → ditahan", "konfirmasi" in out.lower(), out[:80])
out = window_manager({"cmd": "close", "target": f"apa-saja-{RUN}", "confirm": True})
check("close dgn confirm → jalan (window tak ada → jujur)", "tidak ditemukan" in out.lower(), out[:80])

print("=== 7. emergency stop memblokir window_manager ===")
from skills.admin.emergency_stop import trigger, resume
msg = trigger("tes awareness", by="test")
out = window_manager({"cmd": "list"})
check("stop → aksi ditolak", "emergency stop" in out.lower(), out[:80])
check("resume", "boleh bekerja" in resume(by="test").lower())
out = window_manager({"cmd": "list"})
check("setelah resume → jalan lagi", "jendela" in out.lower(), out[:80])

print("=== 8. audit tercatat ===")
from core.audit_logger import tail
evs = tail(30)
check("ada event window_manager", any("window_manager" in (e.get("skill") or "") for e in evs))
check("ada event awareness", any("awareness" in (e.get("action") or "") for e in evs))

print("=== 9. skill_hub mendeteksi kedua skill baru (2 otak) ===")
from core.skill_hub import SkillHub
hub = SkillHub(); hub.discover(force_reload=True)
check("computer_awareness di hub", hub.has("computer_awareness"))
check("window_manager di hub", hub.has("window_manager"))
cat = hub.get_hermes_catalog()
check("masuk katalog Hermes", "window_manager" in cat and "computer_awareness" in cat)

print("=" * 46)
print(f"HASIL: {PASS} PASS, {FAIL} FAIL dari {PASS + FAIL}")
sys.exit(1 if FAIL else 0)
