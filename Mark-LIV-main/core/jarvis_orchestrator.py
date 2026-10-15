# jarvis_orchestrator.py
"""
jarvis_orchestrator.py — Eksekusi task multi-langkah Neira (Blueprint Tahap 2).

Rangkaian: job_manager (lifecycle) + policy_engine (gate per langkah) +
audit_logger (jejak) + skill_hub (eksekusi skill asli) + emergency_stop
(cek di setiap langkah).

Pemakaian dari Hermes/model:
    {"action": "orchestrator", "cmd": "run", "goal": "rapikan desktop",
     "steps": [{"skill": "desktop_control", "params": {"mode": "by_type"}}]}
    {"action": "orchestrator", "cmd": "status", "job_id": "job-202610-xxxx"}
    {"action": "orchestrator", "cmd": "cancel", "job_id": "job-202610-xxxx"}

Alur run():
  buat job → per langkah: emergency_stop? → policy decide() →
    deny      → langkah denied, job failed (jika wajib) / lewati
    confirm   → job waiting_confirmation DI langkah itu; panggil ulang dengan
                job_id + confirm=true setelah user setuju → lanjut dari sini
    allow     → skill_hub.run() → catat hasil + audit → langkah berikut
One repair: langkah gagal boleh diulang SEKALI (retry_count) sebelum job failed.
"""
from __future__ import annotations

import time

def _get_hub():
    """skill_hub lazily — aman dari circular import (skill_hub scan bisa
    re-enter modul ini saat scan meng-import skill wrapper orchestrator)."""
    global _hub
    if _hub is None:
        try:
            from core.skill_hub import skill_hub as _h
            _hub = _h
        except Exception:
            return None
    return _hub


try:
    _hub = None          # diisi lazy oleh _get_hub()
except Exception:
    _hub = None
try:
    from core.policy_engine import decide as _decide, deny_message as _deny_msg, \
        confirm_message as _confirm_msg
except Exception:
    _decide = None
try:
    from core.audit_logger import log_event as _audit, new_correlation_id as _corr
except Exception:
    _audit = None
    _corr = (lambda: "")
try:
    from core import job_manager as jm
except Exception:
    jm = None
try:
    from skills.admin.emergency_stop import is_stopped
except Exception:
    def is_stopped() -> bool:            # type: ignore[misc]
        return False
try:
    from core import metrics as _metrics   # Tahap 4 anti-bohong
except Exception:
    _metrics = None
try:
    from core import self_healing as _sh   # Tahap 5 self-healing
except Exception:
    _sh = None


def _run_skill(skill: str, params: dict) -> str:
    """Eksekusi satu skill via skill_hub (universal dispatch kedua otak)."""
    hub = _get_hub()
    if hub is None:
        return "failed: skill_hub tidak tersedia"
    if not hub.has(skill):
        return f"failed: skill '{skill}' tidak ditemukan"
    try:
        out = hub.run(skill, params or {})
        return str(out)[:2000] if out is not None else "ok"
    except Exception as e:
        return f"failed: {e}"


def run(goal: str, steps: list[dict], job_id: str = "", confirm: bool = False,
        risk_level: str = "medium") -> str:
    """Jalankan/melanjutkan job multi-langkah. Ini SATU-satunya pintu eksekusi."""
    if jm is None:
        return "orchestrator failed: job_manager tidak tersedia"

    # ── Lanjutkan job lama (setelah konfirmasi / resume) ─────────────────────
    if job_id:
        job = jm.get_job(job_id)
        if job is None:
            return f"Job '{job_id}' tidak ditemukan."
        if confirm and job.get("status") == jm.WAITING_CONFIRMATION:
            jm.set_status(job_id, jm.RUNNING)
        # confirm=True dilempar ke _execute: langkah yang di-waiting DIJAMIN
        # sudah disetujui user — jangan ditahan policy lagi.
        return _execute(job, confirm=confirm)

    # ── Job baru ─────────────────────────────────────────────────────────────
    if not goal or not steps:
        return ("Sebutkan goal + steps. Contoh: {\"cmd\": \"run\", "
                "\"goal\": \"rapikan desktop\", \"steps\": [{\"skill\": \"desktop_control\", "
                "\"params\": {\"mode\": \"by_type\"}}]}")
    job, created = jm.create_job(goal, steps, risk_level=risk_level,
                                 correlation_id=_corr())
    if not created:
        return ("⚠️ Tugas yang sama masih berjalan — TIDAK dibuat ganda "
                "(anti double-run):\n" + jm.fmt_job(job))
    jm.set_status(job["job_id"], jm.RUNNING)
    return _execute(job)


def _execute(job: dict, confirm: bool = False) -> str:
    """Loop langkah dari current_step. Return laporan siap-tampilkan."""
    jid = job["job_id"]
    steps = job.get("steps", [])
    start = job.get("current_step", 0)
    lines = [f"🎯 {job['goal']}"]

    for i in range(start, len(steps)):
        # 1) Emergency stop — dicek di SETIAP langkah (blueprint §15)
        if is_stopped():
            jm.set_status(jid, jm.PAUSED, "dihentikan emergency stop")
            return ("\n".join(lines) +
                    f"\n⛔ Dihentikan emergency stop di langkah {i+1}. "
                    f"Job {jid} dijeda — ucapkan 'lanjutkan' untuk resume.")

        s = steps[i]
        skill = s.get("skill", "")
        params = dict(s.get("params") or {})
        action = s.get("policy_action") or ""
        # Langkah yang di-resume setelah konfirmasi user SUDAH disetujui —
        # injeksi confirm=true agar policy gate DI DALAM skill tidak menahan
        # ulang (hanya untuk langkah yang di-waiting itu, bukan semua langkah).
        if confirm and i == start:
            params["confirm"] = True

        # 2) Policy gate per langkah
        if _decide is not None:
            d = _decide(action or f"skill.{skill}", target=params.get("target", ""))
            if d.get("decision") == "deny":
                jm.update_step(jid, i, "denied", d.get("reason", ""))
                _audit({"skill": "orchestrator", "action": action or skill,
                        "target": str(params)[:120], "decision": "deny",
                        "risk_level": d.get("risk", ""), "result": "denied"})
                jm.set_status(jid, jm.FAILED, f"langkah {i+1} ditolak policy")
                return ("\n".join(lines) + f"\n⛔ Langkah {i+1} ({skill}) DITOLAK "
                        f"policy: {d.get('reason', '')}\n" + jm.fmt_job(jm.get_job(jid)))
            if d.get("decision") == "confirm" and not confirm:
                jm.update_step(jid, i, "waiting")
                jm.set_waiting_step(jid, i)
                _audit({"skill": "orchestrator", "action": action or skill,
                        "target": str(params)[:120], "decision": "confirm",
                        "risk_level": d.get("risk", ""),
                        "result": "awaiting_confirmation"})
                return ("\n".join(lines) +
                        f"\n⚠️ Langkah {i+1} ({skill}) butuh konfirmasi: "
                        f"{_confirm_msg(d, skill, params.get('target', ''))}\n"
                        f"Panggil ulang: {{\"action\": \"orchestrator\", "
                        f"\"cmd\": \"run\", \"job_id\": \"{jid}\", \"confirm\": true}}")

        # 3) Eksekusi skill + 1 ronde retry
        jm.update_step(jid, i, "running")
        out = _run_skill(skill, params)
        if out.startswith("failed"):
            jm.update_step(jid, i, "failed", out)
            job_now = jm.get_job(jid) or job
            if job_now.get("retry_count", 0) < 1:
                _mutate_retry(jid)
                # Self-healing (Tahap 5): coba fallback aman dulu — fallback
                # WAJIB terdaftar di skill_hub, output bohong tetap ditolak.
                rec = None
                if _sh is not None:
                    rec = _sh.try_recover(skill, params, out)
                if rec is not None:
                    out2, fb = rec
                    verdict = _verify_step(skill, action, params, out2, s)
                    if not verdict.startswith("unverified"):
                        jm.update_step(jid, i, "done", f"[fallback:{fb}] {out2}")
                        lines.append(f"✅ {i+1}. {skill} gagal → pulih via "
                                     f"fallback {fb}: {out2[:120]}")
                        _audit_ok(action or skill, params, out2)
                        continue
                out2 = _run_skill(skill, params)          # satu repair (blueprint)
                if not out2.startswith("failed"):
                    jm.update_step(jid, i, "done", out2)
                    lines.append(f"✅ {i+1}. {skill} (setelah 1 retry): {out2[:150]}")
                    _audit_ok(action or skill, params, out2)
                    continue
            jm.set_status(jid, jm.FAILED, f"langkah {i+1} gagal: {out[:150]}")
            _audit({"skill": "orchestrator", "action": action or skill,
                    "target": str(params)[:120], "decision": "allow",
                    "result": "failed", "note": out[:200]})
            return ("\n".join(lines) + f"\n❌ Langkah {i+1} ({skill}) gagal: "
                    f"{out[:200]}\n" + jm.fmt_job(jm.get_job(jid)))

        jm.update_step(jid, i, "done", out)
        lines.append(f"✅ {i+1}. {skill}: {out[:150]}")

        # 4) Verifikasi anti-bohong (Tahap 4, blueprint §17): langkah dengan
        #    "expect" dicek ke realita — substring expect HARUS ada di output
        #    asli skill. Gagal verifikasi → job reconciliation_required.
        verdict = _verify_step(skill, action, params, out, s)
        if verdict.startswith("unverified"):
            jm.update_step(jid, i, "unverified", verdict)
            jm.set_status(jid, jm.RECONCILIATION,
                          f"langkah {i+1} gagal verifikasi fakta")
            return ("\n".join(lines) +
                    f"\n❓ Langkah {i+1} ({skill}) mengklaim sukses tapi TIDAK "
                    f"lolos verifikasi — expect '{s.get('expect')}' tidak ada di "
                    f"hasil nyata.\nJob {jid} → reconciliation_required. "
                    "Cek manual dulu; jangan berasumsi sukses.\n"
                    + jm.fmt_job(jm.get_job(jid)))
        _audit_ok(action or skill, params, out)

    jm.set_status(jid, jm.SUCCEEDED, f"{len(steps)} langkah selesai")
    return ("\n".join(lines) + f"\n🏁 Selesai — {len(steps)} langkah.\n"
            + jm.fmt_job(jm.get_job(jid)))


def _mutate_retry(jid: str) -> None:
    def _fn(job: dict) -> None:
        job["retry_count"] = job.get("retry_count", 0) + 1
        job["status"] = jm.RETRYING
    jm._mutate(jid, _fn)


def _verify_step(skill: str, action: str, params: dict, out: str, step: dict) -> str:
    """Rekam klaim sukses + verifikasi fakta (blueprint §17).
    Return "" bila lolos / tanpa expect; "unverified: ..." bila BOHONG."""
    if _metrics is None:
        return ""
    try:
        aid = _metrics.record_claim(skill, action or skill,
                                    target=str(params.get("target", "")),
                                    claim_success=True, result=out)
        expect = str(step.get("expect") or "").strip()
        if not expect:
            return ""                    # klaim tercatat, verifikasi menyusul
        ok = expect.lower() in (out or "").lower()
        _metrics.record_verification(aid, ok, method="expect_substring")
        return "" if ok else f"unverified: expect '{expect}' tidak ditemukan di hasil"
    except Exception:
        return ""                        # metrik gagal tidak boleh gagalkan job


def _audit_ok(action: str, params: dict, result: str) -> None:
    if _audit:
        _audit({"skill": "orchestrator", "action": action,
                "target": str(params)[:120], "decision": "allow",
                "result": "success", "verification": "skill_output",
                "note": result[:120]})


def status(job_id: str = "") -> str:
    if not job_id:
        jobs = jm.list_jobs(5)
        if not jobs:
            return "Belum ada job."
        return "\n\n".join(jm.fmt_job(j) for j in jobs)
    job = jm.get_job(job_id)
    return jm.fmt_job(job) if job else f"Job '{job_id}' tidak ditemukan."


def cancel(job_id: str, reason: str = "") -> str:
    job = jm.cancel(job_id, reason)
    return (f"🚫 {job_id} dibatalkan." if job else f"Job '{job_id}' tidak ditemukan.")


# ── Tool declaration (auto-discovered kedua otak) ────────────────────────────
def orchestrator(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "run").lower().strip()
    try:
        if cmd == "run":
            return run(p.get("goal", ""), p.get("steps") or [],
                       job_id=p.get("job_id", ""), confirm=bool(p.get("confirm")),
                       risk_level=str(p.get("risk_level") or "medium"))
        if cmd == "status":
            return status(p.get("job_id", ""))
        if cmd in ("cancel", "batal"):
            return cancel(p.get("job_id", ""), p.get("reason", ""))
        return "cmd tidak dikenal. Gunakan: run | status | cancel"
    except Exception as e:
        return f"orchestrator gagal: {e}"


TOOL = {
    "name": "orchestrator",
    "description": (
        "Jalankan tugas multi-langkah secara terstruktur: setiap langkah lewat "
        "policy gate, bisa minta konfirmasi user, ada retry 1x, bisa dijeda/"
        "dibatalkan, statusnya tersimpan. Untuk tugas panjang berurutan."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING", "description": "run | status | cancel (default: run)"},
            "goal": {"type": "STRING", "description": "Tujuan tugas (untuk run baru)"},
            "steps": {"type": "ARRAY",
                      "description": ("Daftar langkah [{\"skill\": \"open_app\", "
                                      "\"params\": {...}, \"policy_action\": \"app.open\"}]")},
            "job_id": {"type": "STRING", "description": "ID job untuk resume/status/cancel"},
            "confirm": {"type": "BOOLEAN",
                        "description": "true setelah user menyetujui langkah berisiko"},
        },
        "required": [],
    },
    "handler": orchestrator,
}
