# test_tahap14.py — Remote Approval via HP (blueprint §12)
"""
Isolasi: JOBS_PATH + APPROVAL_PATH → scratch/tmp_*_test14.json (restore in
finally). Orchestrator nyata; _decide/_run_skill di-patch agar job bisa
dibawa ke waiting_confirmation dan dieksekusi tanpa skill asli.
"""
import ast
import json
import os
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def section(t: str) -> None:
    print(f"\n── {t} " + "─" * max(4, 62 - len(t)))


JOBS_TMP = BASE / "scratch" / "tmp_jobs_test14.json"
APPR_TMP = BASE / "scratch" / "tmp_approvals_test14.json"
for p in (JOBS_TMP, APPR_TMP):
    if p.exists():
        p.unlink()

import core.job_manager as jm                       # noqa: E402
import core.remote_approval as ra                   # noqa: E402
import core.jarvis_orchestrator as orch             # noqa: E402

ORIG_JOBS = jm.JOBS_PATH
ORIG_APPR = ra.APPROVAL_PATH
ORCH_ORIG = {"decide": orch._decide, "run_skill": orch._run_skill, "run": orch.run}

jm.JOBS_PATH = JOBS_TMP
ra.APPROVAL_PATH = APPR_TMP


def make_waiting(goal: str):
    j, _ = jm.create_job(goal, [{"skill": "fake_skill", "params": {"x": 1}}],
                         risk_level="medium")
    jm.set_status(j["job_id"], jm.WAITING_CONFIRMATION)
    jm.set_waiting_step(j["job_id"], 0)
    return j["job_id"]


try:
    # ── 1. Policy ────────────────────────────────────────────────────────────
    section("Policy approval.manage")
    pol = json.loads((BASE / "policies" / "default_policy.json").read_text(encoding="utf-8"))
    rule = pol.get("rules", {}).get("approval.manage")
    check("approval.manage terdaftar", isinstance(rule, list) and len(rule) == 2)
    check("approval.manage [low, allow]", rule == ["low", "allow"])

    # ── 2. Register ──────────────────────────────────────────────────────────
    section("Register")
    _e, err = ra.register("")
    check("job_id kosong → error", bool(err))
    _e, err = ra.register("job-tidak-ada-01")
    check("job tak dikenal → 'tidak ditemukan'", "tidak ditemukan" in err)
    jq, _ = jm.create_job("uji bukan waiting 14", [{"skill": "fake_skill", "params": {}}])
    _e, err = ra.register(jq["job_id"])
    check("job bukan waiting → ditolak", "bukan menunggu" in err)

    jid1 = make_waiting("uji approval 14a")
    entry, err = ra.register(jid1, source="test")
    check("register job waiting → sukses", entry is not None and not err)
    check("approval_id == job_id", entry and entry["approval_id"] == jid1)
    check("step_desc memuat skill", entry and "fake_skill" in entry["step_desc"])
    _e, err = ra.register(jid1, source="test")
    check("duplikat pending → error", "sudah ada" in err)

    # ── 3. Notifikasi ────────────────────────────────────────────────────────
    section("Notifikasi ke HP")
    notifs = ra.notifications_new()
    check("notifications_new memuat aid", any(n["approval_id"] == jid1 for n in notifs))
    check("teks notif memuat instruksi", any("setujui" in n["text"] and "tolak" in n["text"]
                                             for n in notifs))
    ra.mark_notified(jid1)
    check("mark_notified → tidak dikirim ulang",
          not any(n["approval_id"] == jid1 for n in ra.notifications_new()))
    check("fmt_pending memuat goal", jid1[:8] in ra.fmt_pending() or
          any(entry["goal"] in ra.fmt_pending() for _ in [0]))
    ra.resolve(jid1, "deny", by="test")            # bersihkan antrian utk seksi 7
    check("antrian dibersihkan", not ra.pending())

    # ── 4. Approve end-to-end ────────────────────────────────────────────────
    section("Approve end-to-end (orchestrator nyata)")
    orch._decide = lambda action, target="", **k: {"decision": "confirm", "risk": "medium"}
    orch._run_skill = lambda skill, params: "ok: langkah fake jalan"
    out = orch.run(goal="uji approval e2e 14", steps=[{"skill": "fake_skill", "params": {"x": 1}}])
    check("orchestrator → butuh konfirmasi", "butuh konfirmasi" in out.lower())
    aid2 = ra.register_from_output(out, source="test")
    check("register_from_output → terdaftar", bool(aid2))
    res = ra.resolve(aid2, "approve", by="test")
    check("resolve approve → lanjut", "Disetujui" in res)
    check("hasil eksekusi nyata di laporan", "ok: langkah fake jalan" in res)
    check("job → succeeded", jm.get_job(aid2).get("status") == jm.SUCCEEDED)

    # ── 5. Deny + double resolve ─────────────────────────────────────────────
    section("Deny + double resolve")
    jid3 = make_waiting("uji approval 14b")
    ra.register(jid3, source="test")
    res = ra.resolve(jid3, "deny", by="hp")
    check("deny → Ditolak", "Ditolak" in res)
    check("job → cancelled", jm.get_job(jid3).get("status") == jm.CANCELLED)
    res = ra.resolve(jid3, "approve")
    check("double resolve → sudah diputuskan", "sudah diputuskan" in res)
    res = ra.resolve("job-202610-deadbeef", "approve")
    check("id tak dikenal → tidak ditemukan", "tidak ditemukan" in res)

    # ── 6. Approve gagal → revert ke pending ─────────────────────────────────
    section("Approve exception → revert")
    jid4 = make_waiting("uji approval 14c")
    ra.register(jid4, source="test")

    def _boom(*a, **k):
        raise RuntimeError("orchestrator down")
    orch.run = _boom
    res = ra.resolve(jid4, "approve", by="test")
    check("eksekusi gagal → jujur error", "gagal" in res.lower() and "orchestrator down" in res)
    check("entry revert ke pending", ra.get(jid4).get("status") == "pending")
    orch.run = ORCH_ORIG["run"]
    ra.resolve(jid4, "deny", by="test")            # bersihkan antrian utk seksi 7
    check("antrian bersih setelah seksi 6", not ra.pending())

    # ── 7. Jalur teks HP ─────────────────────────────────────────────────────
    section("try_handle_text (perintah dari HP)")
    check("teks biasa → None", ra.try_handle_text("halo bro apa kabar") is None)
    check("'approval' → daftar", "persetujuan" in ra.try_handle_text("approval").lower())
    jid5 = make_waiting("uji approval 14d")
    ra.register(jid5, source="test")
    res = ra.try_handle_text("tolak")
    check("'tolak' tanpa id → auto single pending", "Ditolak" in res and jid5 in res)
    check("job5 → cancelled", jm.get_job(jid5).get("status") == jm.CANCELLED)
    res = ra.try_handle_text("setujui")
    check("'setujui' tanpa antrian → info", "tidak ada" in res.lower())
    res = ra.try_handle_text("setujui job-202610-deadbeef")
    check("'setujui <id>' tak dikenal → tidak ditemukan", "tidak ditemukan" in res)

    # ── 8. Expire TTL ────────────────────────────────────────────────────────
    section("Expire TTL")
    jid6 = make_waiting("uji approval 14e")
    ra.register(jid6, source="test")
    rows = ra._load()
    for r in rows:
        if r.get("approval_id") == jid6:
            r["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S",
                                            time.localtime(time.time() - 72 * 3600))
    ra._save(rows)
    n = ra.expire_stale()
    check("expire_stale → 1", n == 1)
    check("status → expired", ra.get(jid6).get("status") == "expired")

    # ── 9. Wrapper skill (3 gerbang) ─────────────────────────────────────────
    section("Wrapper remote_approval_skill")
    from skills.admin.remote_approval_skill import remote_approval_skill as wrap
    from skills.admin.emergency_stop import trigger, resume
    orch._decide = lambda action, target="", **k: {"decision": "confirm", "risk": "medium"}
    orch._run_skill = lambda skill, params: "ok: langkah fake jalan"

    out = wrap({"cmd": "list"})
    check("wrapper list (read-only)", "persetujuan" in out.lower())
    out = wrap({"cmd": "ngasal"})
    check("wrapper bantuan", "Remote Approval Skill" in out)
    trigger("test14")
    out = wrap({"cmd": "approve", "id": "job-202610-deadbeef"})
    check("wrapper estop → ⛔", out.startswith("⛔"))
    resume("test14")

    jid7 = make_waiting("uji approval 14f")
    ra.register(jid7, source="test")
    out = wrap({"cmd": "approve", "id": jid7})
    check("wrapper approve → sukses", "Disetujui" in out)
    check("job7 → succeeded", jm.get_job(jid7).get("status") == jm.SUCCEEDED)

    # ── 10. AST main.py ──────────────────────────────────────────────────────
    section("AST main.py (integrasi)")
    src = (BASE / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "JarvisLive")
    methods = {n.name for n in cls.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    check("class punya _run_approval_push", "_run_approval_push" in methods)
    check("class punya _approval_intercept", "_approval_intercept" in methods)
    check("create_task approval push", "tg.create_task(self._run_approval_push())" in src)
    check("intercept dipanggil di _process_dashboard_commands",
          "self._approval_intercept(text)" in src)
    check("scheduler auto-register approval", "register_from_output" in src)
    check("push pakai notifications_new+mark_notified",
          "notifications_new()" in src and "mark_notified" in src)

    # ── 11. Audit ────────────────────────────────────────────────────────────
    section("Audit")
    audit_txt = ""
    apath = BASE / "audit" / "events.jsonl"
    if apath.exists():
        audit_txt = apath.read_text(encoding="utf-8", errors="ignore")
    check("audit approval.request", '"approval.request"' in audit_txt)
    check("audit approval.decision (approve+deny)",
          '"approval.decision"' in audit_txt and '"decision": "deny"' in audit_txt)
    check("audit wrapper approval.manage", '"approval.manage"' in audit_txt)

    # ── 12. SkillHub ─────────────────────────────────────────────────────────
    section("SkillHub")
    from core.skill_hub import SkillHub
    hub = SkillHub()
    hub.discover(force_reload=True)
    check("remote_approval_skill terdaftar", hub.has("remote_approval_skill"))
    decls = {d.get("name") for d in hub.get_tool_declarations()}
    check("declaration TOOL ada", "remote_approval_skill" in decls)
    rec = hub.get("remote_approval_skill")
    check("handler callable", callable(getattr(rec.handler, "__call__", None)))

finally:
    orch._decide = ORCH_ORIG["decide"]
    orch._run_skill = ORCH_ORIG["run_skill"]
    orch.run = ORCH_ORIG["run"]
    jm.JOBS_PATH = ORIG_JOBS
    ra.APPROVAL_PATH = ORIG_APPR
    for p in (JOBS_TMP, APPR_TMP):
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass

print(f"\n{'=' * 64}\nTOTAL: {PASS} PASS, {FAIL} FAIL dari {PASS + FAIL} cek")
sys.exit(1 if FAIL else 0)
