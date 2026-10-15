# test_tahap7.py — Workspace & Dev Skills (Blueprint Tahap 7)
# Jalankan: cd Mark-LIV-main && python scratch\test_tahap7.py
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
print("TAHAP 7 — WORKSPACE & DEV SKILLS (analyze/logs/tests/backup)")
print("=" * 64)

# ── 1. Policy rules ──────────────────────────────────────────────────────────
print("\n[1] Policy rules workspace.* / logs.* / devtools.*")
from core.policy_engine import decide as decide

for act in ("workspace.analyze", "workspace.backup", "devtools.run_tests", "logs.scan"):
    d = decide(act, target="core")
    check(f"{act} terdecide", d.get("decision") in ("allow", "confirm"))
d = decide("workspace.analyze", target="../..")
check("policy tetap decide utk target aneh (pembatasan di core)", "decision" in d)

# ── 2. Pembatasan path (traversal keluar workspace ditolak) ──────────────────
print("\n[2] Pembatasan path — hanya di dalam workspace")
from core import workspace_dev as wd

r = wd.analyze_repo("../..")
check("analyze keluar workspace → ditolak", r.get("allowed") is False)
r = wd.analyze_repo("C:\\Windows")
check("analyze C:\\Windows → ditolak", r.get("allowed") is False)
r = wd.scan_logs("..\\..\\secret.log")
check("scan log keluar workspace → ditolak", r.get("allowed") is False)
r = wd.run_tests("..")
check("tests keluar workspace → ditolak", r.get("allowed") is False)
r = wd.backup_workspace("../..")
check("backup keluar workspace → ditolak", r.get("allowed") is False)

# ── 3. Analyze repo (read-only nyata) ────────────────────────────────────────
print("\n[3] Analyze repo")
r = wd.analyze_repo("")
check("analyze root → allowed", r.get("allowed") is True)
check("punya total_files > 0", r.get("total_files", 0) > 0)
check("punya size_mb", isinstance(r.get("size_mb"), (int, float)))
check("languages tidak kosong", len(r.get("languages", {})) > 0)
check("entry_points memuat main.py", "main.py" in r.get("entry_points", []))
check("top_dirs memuat core/skills", {"core", "skills"} <= set(r.get("top_dirs", {})))
check("todos terhitung", isinstance(r.get("todos"), int))
r2 = wd.analyze_repo("core")
check("analyze core → allowed", r2.get("allowed") is True)
check("analyze core lebih kecil dari root", r2.get("total_files", 0) < r.get("total_files", 0))
r3 = wd.analyze_repo("core/policy_engine.py")
check("target file → ditolak (bukan folder)", r3.get("allowed") is False)

# ── 4. Scan log (audit nyata dari tahap-tahap sebelumnya) ────────────────────
print("\n[4] Scan log audit")
r = wd.scan_logs("", pattern="deny")
check("scan deny → allowed", r.get("allowed") is True)
check("audit ada (exists True)", r.get("exists") is True)
check("ada baris deny dari sesi ini", r.get("total", 0) >= 1)
check("errors terhitung", r.get("errors", 0) >= 1)
check("recent terisi", len(r.get("recent", [])) >= 1)
r = wd.scan_logs("", pattern="workflow")
check("scan workflow → ada jejak", r.get("allowed") is True and r.get("total", 0) >= 1)
r = wd.scan_logs("", pattern="xyz_tidak_ada_88")
check("pattern ngasal → total 0 (jujur)", r.get("total") == 0)
r = wd.scan_logs("requirements.txt")
check("scan file .txt diperbolehkan", r.get("allowed") is True)
r = wd.scan_logs("core/policy_engine.py")
check("scan .py → ditolak (bukan log)", r.get("allowed") is False)
r = wd.scan_logs("memory/tidak_ada_999.log")
check("log tidak ada → jujur exists=False", r.get("exists") is False)

# ── 5. Run tests (folder test kecil khusus) ──────────────────────────────────
print("\n[5] Run tests")
tdir = Path(wd.WORKSPACE) / "scratch" / "tmp_t7"
tdir.mkdir(parents=True, exist_ok=True)
(tdir / "test_ok.py").write_text(
    "def test_a():\n    assert 1 + 1 == 2\n\ndef test_b():\n    assert 'x' in 'box'\n",
    encoding="utf-8")
(tdir / "test_bad.py").write_text(
    "def test_z():\n    assert 1 == 2, 'sengaja gagal'\n", encoding="utf-8")
r = wd.run_tests("scratch/tmp_t7", timeout=60)
check("tests → allowed", r.get("allowed") is True)
check("runner terdeteksi", r.get("runner") in ("pytest", "unittest"))
check("test buruk → ok False", r.get("ok") is False)
check("returncode != 0", r.get("returncode") != 0)
check("output memuat nama test", "test_a" in r.get("output", "") or "test_z" in r.get("output", ""))
(tdir / "test_bad.py").unlink()
r = wd.run_tests("scratch/tmp_t7", timeout=60)
check("setelah dibersihkan → ok True", r.get("ok") is True)
(tdir / "test_ok.py").unlink()
try:
    tdir.rmdir()
except OSError:
    pass
r = wd.run_tests("folder_ngawur_404")
check("folder tidak ada → ditolak", r.get("allowed") is False)

# ── 6. Backup (dry-run default + nyata + daftar) ─────────────────────────────
print("\n[6] Backup workspace")
r = wd.backup_workspace("", dry_run=True)
check("dry-run → allowed", r.get("allowed") is True)
check("dry-run flag True", r.get("dry_run") is True)
check("dry-run hitung file > 0", r.get("files", 0) > 0)
check("dest mengarah backups/", "backups" in str(r.get("dest", "")))
from core.audit_logger import tail as audit_tail
# Real-write check pakai subfolder kecil ("core") — root workspace 1.4 GB
# memang MELEBIHI batas 200 MB, dan penolakan itu adalah perilaku benar.
r_root = wd.backup_workspace("", dry_run=False)
check("backup root 1.4GB → ditolak batas (perilaku benar)",
      r_root.get("ok") is False and "refused" in r_root)
before_rows = len(audit_tail(50))
r = wd.backup_workspace("core", dry_run=False)
check("backup nyata (core) → ok", r.get("ok") is True)
check("zip tersimpan", Path(r.get("dest", "")).exists())
check("size_mb > 0", r.get("size_mb", 0) > 0)
rows = wd.list_backups()
check("list_backups ≥ 1", len(rows) >= 1)
check("list memuat zip barusan", any("-backup-" in x["name"] for x in rows))
check("list punya size & tanggal", all("size_mb" in x and "modified" in x for x in rows))

# ── 7. Skill wrapper: 3 gerbang ──────────────────────────────────────────────
print("\n[7] Skill wrapper workspace_dev: stop → policy → audit")
from skills.dev import workspace_dev as sk

out = sk.workspace_dev({"cmd": "analyze"})
check("wrapper analyze → REPO", "REPO" in out)
out = sk.workspace_dev({"cmd": "analyze", "target": "core"})
check("wrapper analyze core", "core" in out.lower() or "REPO" in out)
out = sk.workspace_dev({"cmd": "logs", "pattern": "deny"})
check("wrapper logs → LOG", "LOG" in out)
out = sk.workspace_dev({"cmd": "backups"})
check("wrapper backups → daftar", "BACKUP" in out)
out = sk.workspace_dev({"cmd": "ngaco"})
check("cmd asing → bantuan", "tidak dikenal" in out)
out = sk.workspace_dev({"cmd": "analyze", "target": "../.."})
check("wrapper menolak traversal", "DITOLAK" in out or "di luar workspace" in out)

from skills.admin import emergency_stop as es
es.trigger("test tahap7")
out = sk.workspace_dev({"cmd": "analyze"})
check("emergency stop memblokir", "EMERGENCY STOP" in out)
es.resume()
check("resume → bebas", not es.is_stopped())

out = sk.workspace_dev({"cmd": "backup", "confirm": False})
check("backup tanpa confirm → dry-run", "dry-run" in out)
out = sk.workspace_dev({"cmd": "backup", "target": "core", "confirm": True})
check("backup confirm (core) → tersimpan", "tersimpan" in out)
out = sk.workspace_dev({"cmd": "backup", "confirm": True})
check("backup confirm root 1.4GB → ditolak batas", "DITOLAK" in out)

# ── 8. Audit jejak workspace_dev ─────────────────────────────────────────────
print("\n[8] Audit jejak")
rows = audit_tail(20)
wd_rows = [x for x in rows if x.get("skill") == "workspace_dev"]
check("ada audit workspace_dev", len(wd_rows) >= 3)
check("audit memuat workspace.analyze", any(x.get("action") == "workspace.analyze" for x in wd_rows))
check("audit memuat workspace.backup", any(x.get("action") == "workspace.backup" for x in wd_rows))

# ── 9. SkillHub kedua otak ───────────────────────────────────────────────────
print("\n[9] SkillHub kedua otak")
from core.skill_hub import skill_hub as hub
check("workspace_dev terdaftar", hub.has("workspace_dev"))
decls = {t["name"] for t in hub.get_tool_declarations()}
check("deklarasi tool utk otak", "workspace_dev" in decls)
check("katalog Hermes sebut workspace_dev", "workspace_dev" in hub.get_hermes_catalog())
out = hub.run("workspace_dev", {"cmd": "analyze", "target": "core"})
check("dispatch via hub jalan", "REPO" in out)

# ── 10. Workflow repo_health_check end-to-end ────────────────────────────────
print("\n[10] Workflow repo_health_check via workflow_manager")
from core import workflow_engine as we
wf = we.load("repo_health_check")
check("workflow ketiga ter-load", isinstance(wf, dict))
check("punya 4 langkah", len(wf.get("steps", [])) == 4)
items = we.list_workflows()
check("list sekarang 3 workflow", len(items) >= 3)
from skills.admin import workflow_manager as wmgr
out = wmgr.workflow_manager({"cmd": "run", "name": "repo_health_check"})
check("run repo_health_check sukses", "🏁" in out and "[workflow:repo_health_check]" in out)
check("tanpa unverified", "unverified" not in out)

# ── RINGKASAN ────────────────────────────────────────────────────────────────
print("\n" + "=" * 64)
print(f"HASIL: {PASS} PASS, {FAIL} FAIL dari {PASS + FAIL} cek")
print("=" * 64)
sys.exit(0 if FAIL == 0 else 1)
