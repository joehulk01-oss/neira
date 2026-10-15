# workflow_manager.py — Blueprint Tahap 6
"""
Satu-satunya pintu EKSEKUSI workflow (cmd=run) — dengan 3 gerbang wajib:
emergency stop → policy gate (workflow.run) → audit. cmd read-only
(list/show) tetap tersedia di workflow_engine (core).

Pemakaian dari Hermes/model:
    {"action": "workflow_manager", "cmd": "list"}
    {"action": "workflow_manager", "cmd": "show", "name": "morning_briefing"}
    {"action": "workflow_manager", "cmd": "run", "name": "morning_briefing"}
    {"action": "workflow_manager", "cmd": "run", "name": "shutdown_routine",
     "confirm": true}          # setelah user menyetujui langkah berisiko
"""
from __future__ import annotations

try:
    from core import workflow_engine as _we
except Exception:
    _we = None
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


def workflow_manager(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "list").lower().strip()
    name = str(p.get("name") or "").strip()
    confirm = bool(p.get("confirm"))

    try:
        # ── Read-only commands: delegasi murni ke workflow_engine ────────────
        if cmd in ("list", "show"):
            return _we.workflow_engine({"cmd": cmd, "name": name})

        if cmd == "run":
            # 1) Emergency stop
            if is_stopped():
                return "⛔ EMERGENCY STOP aktif — semua eksekusi diblokir. " \
                       "Ucapkan 'resume' untuk menonaktifkan."
            # 2) Policy gate
            if _decide is not None:
                d = _decide("workflow.run", target=name)
                if d.get("decision") == "deny":
                    if _audit:
                        _audit({"skill": "workflow_manager", "action": "workflow.run",
                                "target": name[:120], "decision": "deny",
                                "risk_level": d.get("risk", ""), "result": "denied"})
                    return (f"⛔ Workflow '{name}' DITOLAK policy: "
                            f"{d.get('reason', '')}")
                if d.get("decision") == "confirm" and not confirm:
                    if _audit:
                        _audit({"skill": "workflow_manager", "action": "workflow.run",
                                "target": name[:120], "decision": "confirm",
                                "risk_level": d.get("risk", ""),
                                "result": "awaiting_confirmation"})
                    return (f"⚠️ Workflow '{name}' mengandung langkah berisiko dan "
                            f"butuh konfirmasi. Panggil ulang: {{\"action\": "
                            f"\"workflow_manager\", \"cmd\": \"run\", \"name\": "
                            f"\"{name}\", \"confirm\": true}}")
            # 3) Audit + eksekusi lewat orchestrator (satu pintu eksekusi)
            if _audit:
                _audit({"skill": "workflow_manager", "action": "workflow.run",
                        "target": name[:120], "decision": "allow",
                        "risk_level": d.get("risk", "") if _decide else "",
                        "result": "success", "correlation_id": _corr()})
            return _we.run(name, confirm=confirm)

        return "cmd tidak dikenal. Gunakan: list | show | run"
    except Exception as e:
        return f"workflow_manager gagal: {e}"


TOOL = {
    "name": "workflow_manager",
    "description": (
        "Workflow tersimpan (workflows/*.yaml): list daftar, show detail, run "
        "eksekusi rangkaian langkah lewat orchestrator (policy + konfirmasi + "
        "verifikasi tetap aktif per langkah). Workflow berisiko butuh confirm=true."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING", "description": "list | show | run (default: list)"},
            "name": {"type": "STRING", "description": "Nama workflow, contoh: morning_briefing"},
            "confirm": {"type": "BOOLEAN",
                        "description": "true setelah user menyetujui workflow berisiko"},
        },
        "required": [],
    },
    "handler": workflow_manager,
}
