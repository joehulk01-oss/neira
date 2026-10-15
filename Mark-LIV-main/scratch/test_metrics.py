# scratch/test_metrics.py — Tahap 4 Metrik Anti-Bohong
# Jalankan: python scratch\test_metrics.py
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

RUN = time.strftime("%H%M%S")

print("=== 1. record_claim + record_verification (dasar) ===")
from core import metrics as m
aid1 = m.record_claim("app_manager", "app.kill", "111", True, "✅ kill oke")
check("attempt_id dibuat", aid1.startswith("att-"))
att = m.record_verification(aid1, True, "psutil.pid_exists")
check("verifikasi tersimpan", att.get("verified") is True and att.get("verify_method") == "psutil.pid_exists")
check("verifikasi attempt asing → {}", m.record_verification("att-tidakada", True) == {})

print("=== 2. false_success_rate matematika benar ===")
s0 = m.stats()
base_bad = s0["false_success"]; base_ver = s0["verified"]
aid2 = m.record_claim("app_manager", "app.close", "222", True, "✅ close oke")
m.record_verification(aid2, False, "psutil: proses masih hidup")  # BOHONG
s1 = m.stats()
check("false_success naik 1", s1["false_success"] == base_bad + 1)
check("verified naik 1", s1["verified"] == base_ver + 1)
exp_rate = round((base_bad + 1) / (base_ver + 1), 4)
check("rate = bad/verified", s1["false_success_rate"] == exp_rate, f"{s1['false_success_rate']} vs {exp_rate}")

print("=== 3. pending = klaim belum diverifikasi ===")
aid3 = m.record_claim("window_manager", "window.focus", "notepad", True, "✅ fokus")
pend = m.pending(limit=50)
check("aid3 masuk pending", any(a["attempt_id"] == aid3 for a in pend))

print("=== 4. format_stats tampil ===")
txt = m.format_stats()
check("judul metrik", "METRIK ANTI-BOHONG" in txt)
check("rate tampil", "FALSE SUCCESS RATE" in txt)
check("target blueprint", "5%" in txt)

print("=== 5. orchestrator: langkah expect COCOK → succeeded + verified True ===")
from core.jarvis_orchestrator import run as orch_run, status as orch_status
from core import job_manager as jm
out = orch_run(f"tes metrik cocok {RUN}", [
    {"skill": "computer_awareness", "params": {"cmd": "active"},
     "expect": "aktif"},
])
check("job selesai", "🏁" in out or "succeeded" in out.lower(), out[:120])
st = orch_status()
check("status sukses", "succeeded" in st.lower(), st[:120])
s2 = m.stats()
check("attempt verif tercatat", s2["verified"] >= base_ver + 2)
rec = [a for a in m.recent(5) if a["skill"] == "computer_awareness"]
check("langkah cocok → verified True", rec and rec[-1].get("verified") is True, str(rec[-1:])[:120])

print("=== 6. orchestrator: expect TIDAK cocok → reconciliation + BOHONG tercatat ===")
before = m.stats()["false_success"]
out2 = orch_run(f"tes metrik bohong {RUN}", [
    {"skill": "computer_awareness", "params": {"cmd": "active"},
     "expect": "SUBSTRING-INI-PASTI-TIDAK-ADA"},
])
check("job tidak klaim sukses", "🏁" not in out2, out2[:150])
check("ada tanda reconciliation", "reconciliation" in out2.lower() or "❓" in out2 or "gagal verifikasi" in out2.lower(), out2[:200])
after = m.stats()["false_success"]
check("false_success naik", after == before + 1, f"{before} → {after}")

print("=== 7. skill wrapper metrics + TOOL + 2 otak ===")
from skills.dev.metrics import metrics as metrics_skill, TOOL as TOOL_M
out3 = metrics_skill({"cmd": "stats"})
check("stats via skill", "FALSE SUCCESS RATE" in out3, out3[:100])
out4 = metrics_skill({"cmd": "reset"})  # tanpa confirm
check("reset tanpa confirm ditahan", "confirm=true" in out4.lower(), out4[:100])
check("TOOL metrics", TOOL_M["name"] == "metrics" and callable(TOOL_M["handler"]))
from core.skill_hub import SkillHub
hub = SkillHub(); hub.discover(force_reload=True)
check("metrics di skill_hub", hub.has("metrics"))
check("masuk katalog Hermes", "metrics" in hub.get_hermes_catalog())

print("=" * 46)
print(f"HASIL: {PASS} PASS, {FAIL} FAIL dari {PASS + FAIL}")
sys.exit(1 if FAIL else 0)
