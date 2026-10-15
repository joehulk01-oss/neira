# task_planner_agent.py — Blueprint Tahap 8
"""
Wrapper skill utk task_planner (core). 3 gerbang wajib pada cmd=execute:
emergency stop → policy gate (planner.execute) → audit. cmd plan/validate
read-only (tidak mengeksekusi apa pun).

Pemakaian dari Hermes/model:
    {"action": "task_planner_agent", "cmd": "plan", "goal": "cek kesehatan repo"}
    {"action": "task_planner_agent", "cmd": "validate", "steps": [...]}
    {"action": "task_planner_agent", "cmd": "execute", "goal": "...",
     "steps": [...], "confirm": true}
"""
from __future__ import annotations

try:
    from core import task_planner as _tp
except Exception:
    _tp = None
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


def _fmt_steps(raw) -> str:
    steps, errors = _tp.validate_steps(raw or [])
    if errors:
        return "❌ " + "; ".join(errors[:3])
    return "✅ " + _tp.fmt_plan(steps)


def task_planner_agent(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "help").lower().strip()

    try:
        # ── Read-only: plan & validate (tidak mengeksekusi) ──────────────────
        if cmd == "plan":
            if _tp is None:
                return "task_planner (core) tidak tersedia"
            steps, msg = _tp.plan(str(p.get("goal") or ""))
            if _audit:
                _audit({"skill": "task_planner_agent", "action": "planner.plan",
                        "target": str(p.get("goal") or "")[:120],
                        "result": "ok" if steps else "empty"})
            if not steps:
                return f"❌ {msg}"
            return f"✅ {msg}\n{_tp.fmt_plan(steps)}\n" \
                   'Jalankan: {"action":"task_planner_agent","cmd":"execute",' \
                   '"goal":...,"steps":[...],"confirm":true}'

        if cmd == "validate":
            if _tp is None:
                return "task_planner (core) tidak tersedia"
            return _fmt_steps(p.get("steps"))

        if cmd == "execute":
            if _tp is None:
                return "task_planner (core) tidak tersedia"
            goal = str(p.get("goal") or "tanpa judul")
            steps, errors = _tp.validate_steps(p.get("steps") or [])
            if errors:
                if _audit:
                    _audit({"skill": "task_planner_agent", "action": "planner.execute",
                            "target": goal[:120], "result": "invalid_plan"})
                return "❌ Plan ditolak: " + "; ".join(errors[:3])
            if not steps:
                return "❌ steps kosong — sertakan langkah yang sudah divalidasi"

            confirm = bool(p.get("confirm"))
            if not confirm:
                # Tampilkan plan & minta konfirmasi eksplisit
                return "⚠️ Plan siap dieksekusi:\n" + _tp.fmt_plan(steps) + \
                       '\n\nPanggil ulang dengan "confirm": true untuk mengeksekusi.'

            # 1) Emergency stop
            if is_stopped():
                if _audit:
                    _audit({"skill": "task_planner_agent", "action": "planner.execute",
                            "target": goal[:120], "result": "blocked_emergency_stop"})
                return "⛔ EMERGENCY STOP aktif — eksekusi diblokir. " \
                       "Ucapkan 'resume' untuk menonaktifkan."
            # 2) Policy gate
            risk = ""
            if _decide is not None:
                d = _decide("planner.execute", target=goal)
                risk = d.get("risk", "")
                if d.get("decision") == "deny":
                    if _audit:
                        _audit({"skill": "task_planner_agent", "action": "planner.execute",
                                "target": goal[:120], "decision": "deny",
                                "risk_level": risk, "result": "denied"})
                    return f"⛔ Eksekusi plan DITOLAK policy: {d.get('reason', '')}"
                if d.get("decision") == "confirm":
                    risk = risk or "medium"
            # 3) Audit + eksekusi lewat orchestrator (satu pintu)
            if _audit:
                _audit({"skill": "task_planner_agent", "action": "planner.execute",
                        "target": goal[:120], "decision": "allow",
                        "risk_level": risk or "medium", "result": "success",
                        "steps": len(steps), "correlation_id": _corr()})
            return _tp.execute(goal, steps, confirm=True, risk_level=risk or "medium")

        return ("Task Planner Agent — cmd: plan (niat→langkah via LLM lokal) | "
                "validate (cek steps) | execute (jalankan lewat orchestrator, "
                'butuh "confirm": true).')
    except Exception as e:
        return f"task_planner_agent gagal: {e}"


TOOL = {
    "name": "task_planner_agent",
    "description": (
        "Rencanakan & jalankan tugas multi-langkah. plan=niat user→daftar "
        "langkah (LLM lokal, skill valid dari skill_hub), validate=cek steps, "
        "execute=jalankan lewat orchestrator (policy+verifikasi per langkah, "
        "butuh confirm=true setelah user setuju)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "plan | validate | execute (default: help)"},
            "goal": {"type": "STRING",
                     "description": "Niat user, contoh: analisis repo lalu backup core"},
            "steps": {"type": "ARRAY",
                      "description": "Daftar langkah utk validate/execute: [{skill, params}]"},
            "confirm": {"type": "BOOLEAN",
                        "description": "true untuk benar-benar mengeksekusi plan"},
        },
        "required": [],
    },
    "handler": task_planner_agent,
}
