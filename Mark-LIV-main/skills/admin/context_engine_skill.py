# context_engine_skill.py — Blueprint Tahap 10
"""
Wrapper skill utk core.context_engine. Read-only murni (merangkai fakta,
tidak mengeksekusi OS) — tetap lewat 3 gerbang standar demi konsistensi.

Pemakaian dari Hermes/model:
    {"action": "context_engine_skill", "cmd": "build", "query": "backup core"}
    {"action": "context_engine_skill", "cmd": "stats"}
"""
from __future__ import annotations

try:
    from core import context_engine as _ce
except Exception:
    _ce = None
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


def context_engine_skill(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "build").lower().strip()

    try:
        if cmd in ("build", "stats"):
            if _ce is None:
                return "context_engine (core) tidak tersedia"
            # 1) Emergency stop
            if is_stopped():
                return "⛔ EMERGENCY STOP aktif."
            # 2) Policy gate
            if _decide is not None:
                d = _decide("context.build")
                if d.get("decision") == "deny":
                    return f"⛔ DITOLAK policy: {d.get('reason', '')}"
            # 3) Audit + jalankan
            if _audit:
                _audit({"skill": "context_engine_skill", "action": "context.build",
                        "target": str(p.get("query") or "")[:60],
                        "result": "success", "correlation_id": _corr()})
            return _ce.context_engine({"cmd": cmd, "query": p.get("query"),
                                       "max_chars": p.get("max_chars")})

        return ("Context Engine Skill — cmd: build (konteks siap-prompt dgn "
                "budget) | stats (ringkasan seksi). Read-only.")
    except Exception as e:
        return f"context_engine_skill gagal: {e}"


TOOL = {
    "name": "context_engine_skill",
    "description": (
        "Bangun konteks lengkap utk menjawab user: kondisi PC, metrik, tugas "
        "terakhir, memori relevan (dari query), sesi sebelumnya — dengan "
        "token budget. Read-only."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING", "description": "build | stats (default: build)"},
            "query": {"type": "STRING", "description": "Niat user utk memilih memori relevan"},
            "max_chars": {"type": "INTEGER", "description": "Budget karakter (default 4000)"},
        },
        "required": [],
    },
    "handler": context_engine_skill,
}
