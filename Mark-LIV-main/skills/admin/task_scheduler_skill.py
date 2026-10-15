# task_scheduler_skill.py — Blueprint Tahap 11
"""
Wrapper skill utk core/scheduler.py — 3 gerbang wajib pada aksi EKSEKUSI:
    emergency stop → policy gate (scheduler.manage) → audit

Read-only (list/show/tick) tetap terbuka — tick hanya MEMICU; per langkah
eksekusi tetap melewati policy orchestrator sendiri, jadi read-only aman.

Pemakaian dari Hermes/model:
    {"action": "task_scheduler_skill", "cmd": "list"}
    {"action": "task_scheduler_skill", "cmd": "add", "name": "backup pagi",
     "goal": "backup workspace", "at": "07:00",
     "steps": [{"skill": "workspace_dev", "params": {"cmd": "backup"}}]}
    {"action": "task_scheduler_skill", "cmd": "remove", "name": "backup pagi"}
"""
from __future__ import annotations

try:
    from core import scheduler as _ts
except Exception:
    _ts = None
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


def task_scheduler_skill(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "list").lower().strip()
    name = str(p.get("name") or "").strip()

    try:
        # ── Read-only: delegasi murni ────────────────────────────────────────
        if cmd in ("list", "show", "tick"):
            return _ts.task_scheduler({"cmd": cmd, "name": name})

        # ── Aksi mengubah jadwal: 3 gerbang ──────────────────────────────────
        if _ts is None:
            return "task_scheduler_skill failed: core.scheduler tidak tersedia"
        if is_stopped():
            return "⛔ EMERGENCY STOP aktif — perubahan jadwal diblokir. " \
                   "Ucapkan 'resume' untuk menonaktifkan."
        if _decide is not None:
            d = _decide("scheduler.manage", target=name[:120])
            if d.get("decision") == "deny":
                if _audit:
                    _audit({"skill": "task_scheduler_skill", "action": "scheduler.manage",
                            "target": name[:120], "decision": "deny",
                            "risk_level": d.get("risk", ""), "result": "denied"})
                return f"⛔ Jadwal '{name}' DITOLAK policy: {d.get('reason', '')}"
            if d.get("decision") == "confirm" and not p.get("confirm"):
                if _audit:
                    _audit({"skill": "task_scheduler_skill", "action": "scheduler.manage",
                            "target": name[:120], "decision": "confirm",
                            "risk_level": d.get("risk", ""),
                            "result": "awaiting_confirmation"})
                return (f"⚠️ Perubahan jadwal '{name}' butuh konfirmasi. "
                        f"Panggil ulang dengan \"confirm\": true.")
            allow_risk = d.get("risk", "") if _decide else ""
        else:
            allow_risk = ""
        if _audit:
            _audit({"skill": "task_scheduler_skill", "action": "scheduler.manage",
                    "target": name[:120], "decision": "allow",
                    "risk_level": allow_risk, "result": "success",
                    "correlation_id": _corr()})

        if cmd == "add":
            s, created, err = _ts.add(name, p.get("goal") or "", p.get("steps") or [],
                                      every_minutes=p.get("every_minutes"),
                                      at=str(p.get("at") or ""),
                                      risk_level=str(p.get("risk_level") or "medium"))
            if err:
                return f"❌ {err}"
            if not created:
                return f"⚠️ Jadwal '{name}' sudah ada (anti duplikat):\n{_ts.fmt_schedule(s)}"
            return f"✅ Jadwal dibuat:\n{_ts.fmt_schedule(s)}"

        if cmd == "remove":
            return (f"🗑 Jadwal '{name}' dihapus."
                    if _ts.remove(name) else f"Jadwal '{name}' tidak ditemukan.")

        if cmd in ("enable", "disable"):
            s = _ts.set_enabled(name, cmd == "enable")
            if s is None:
                return f"Jadwal '{name}' tidak ditemukan."
            return f"{'▶️ Diaktifkan' if cmd == 'enable' else '⏸ Dimatikan'}: {_ts.fmt_schedule(s)}"

        return ("Task Scheduler Skill — cmd: list | show | tick (read-only) | "
                "add | remove | enable | disable (butuh policy gate). "
                "Eksekusi jadwal tetap lewat orchestrator.")
    except Exception as e:
        return f"task_scheduler_skill gagal: {e}"


TOOL = {
    "name": "task_scheduler_skill",
    "description": (
        "Kelola jadwal tugas otomatis Neira: add (name+goal+steps+every_minutes|at), "
        "remove, enable/disable, list/show, tick (jalankan yang jatuh tempo lewat "
        "orchestrator). Perubahan jadwal melewati policy gate."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "add | remove | list | show | enable | disable | tick"},
            "name": {"type": "STRING", "description": "Nama jadwal"},
            "goal": {"type": "STRING", "description": "Tujuan tugas (add)"},
            "steps": {"type": "ARRAY", "description": "Langkah [{skill, params}] (add)"},
            "every_minutes": {"type": "NUMBER", "description": "Interval menit (add)"},
            "at": {"type": "STRING", "description": "Jam harian HH:MM (add)"},
            "confirm": {"type": "BOOLEAN",
                        "description": "true setelah user menyetujui (bila policy minta)"},
        },
        "required": [],
    },
    "handler": task_scheduler_skill,
}
