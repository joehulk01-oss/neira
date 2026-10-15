# remote_approval_skill.py — Blueprint Tahap 14
"""
Wrapper skill utk core/remote_approval.py — 3 gerbang wajib pada aksi
MENGUBAH keadaan (request/approve/deny):
    emergency stop → policy gate (approval.manage) → audit

Read-only (list/show) terbuka — hanya menampilkan antrian.

Pemakaian dari Hermes/model:
    {"action": "remote_approval_skill", "cmd": "list"}
    {"action": "remote_approval_skill", "cmd": "approve", "id": "job-202610-abc123"}
    {"action": "remote_approval_skill", "cmd": "deny", "id": "job-202610-abc123"}
"""
from __future__ import annotations

try:
    from core import remote_approval as _ra
except Exception:
    _ra = None
try:
    from core.policy_engine import decide as _decide
except Exception:
    _decide = None
try:
    from core.audit_logger import log_event as _audit, new_correlation_id as _corr
except Exception:
    _audit = None
    _corr = (lambda: "")
try:
    from skills.admin.emergency_stop import is_stopped
except Exception:
    def is_stopped() -> bool:            # type: ignore[misc]
        return False


def remote_approval_skill(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "list").lower().strip()
    aid = str(p.get("id") or p.get("approval_id") or p.get("job_id") or "").strip()

    try:
        # ── Read-only: delegasi murni ────────────────────────────────────────
        if cmd in ("list", "pending", "show"):
            if _ra is None:
                return "remote_approval_skill failed: core.remote_approval tidak tersedia"
            return _ra.remote_approval({"cmd": cmd, "id": aid})

        # ── Aksi mengubah keadaan: 3 gerbang ─────────────────────────────────
        if _ra is None:
            return "remote_approval_skill failed: core.remote_approval tidak tersedia"
        if is_stopped():
            return "⛔ EMERGENCY STOP aktif — keputusan approval diblokir. " \
                   "Ucapkan 'resume' untuk menonaktifkan."
        if _decide is not None:
            d = _decide("approval.manage", target=aid[:120])
            if d.get("decision") == "deny":
                if _audit:
                    _audit({"skill": "remote_approval_skill", "action": "approval.manage",
                            "target": aid[:120], "decision": "deny",
                            "risk_level": d.get("risk", ""), "result": "denied"})
                return f"⛔ Approval '{aid}' DITOLAK policy: {d.get('reason', '')}"
            if d.get("decision") == "confirm" and not p.get("confirm"):
                if _audit:
                    _audit({"skill": "remote_approval_skill", "action": "approval.manage",
                            "target": aid[:120], "decision": "confirm",
                            "risk_level": d.get("risk", ""),
                            "result": "awaiting_confirmation"})
                return (f"⚠️ Keputusan approval '{aid}' butuh konfirmasi. "
                        f"Panggil ulang dengan \"confirm\": true.")
            allow_risk = d.get("risk", "")
        else:
            allow_risk = ""
        if _audit:
            _audit({"skill": "remote_approval_skill", "action": "approval.manage",
                    "target": aid[:120], "decision": "allow",
                    "risk_level": allow_risk, "result": "success",
                    "correlation_id": _corr()})

        if cmd == "request":
            entry, err = _ra.register(aid, source="skill")
            if err:
                return f"❌ {err}"
            return f"✅ Permintaan terdaftar:\n{_ra.fmt_approval(entry)}"

        if cmd in ("approve", "deny"):
            return _ra.resolve(aid, cmd, by="skill")

        return ("Remote Approval Skill — cmd: list | show (id) (read-only) | "
                "request | approve | deny (butuh policy gate). Approve "
                "melanjutkan job via orchestrator (confirm=True).")
    except Exception as e:
        return f"remote_approval_skill gagal: {e}"


TOOL = {
    "name": "remote_approval_skill",
    "description": (
        "Setujui (approve) atau tolak (deny) job yang menunggu konfirmasi: "
        "list antrian, lalu putuskan by id. Approve melanjutkan eksekusi lewat "
        "orchestrator (confirm=True) — jangan pernah eksekusi manual di luar itu."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "list | show | request | approve | deny"},
            "id": {"type": "STRING", "description": "job_id / approval_id"},
            "confirm": {"type": "BOOLEAN",
                        "description": "true bila user sudah mengonfirmasi"},
        },
        "required": [],
    },
    "handler": remote_approval_skill,
}
