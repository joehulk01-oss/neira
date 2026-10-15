# injection_guard_skill.py — Blueprint Tahap 9
"""
Wrapper skill utk core.injection_guard. Read-only murni: check/sanitize
TIDAK mengeksekusi apa pun — jadi tetap lewat 3 gerbang standar (stop →
policy → audit) demi konsistensi arsitektur, meski risikonya low.

Pemakaian dari Hermes/model:
    {"action": "injection_guard_skill", "cmd": "check", "text": "..."}
    {"action": "injection_guard_skill", "cmd": "sanitize", "text": "...",
     "source": "reddit"}
"""
from __future__ import annotations

try:
    from core import injection_guard as _ig
except Exception:
    _ig = None
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


def injection_guard_skill(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "help").lower().strip()

    try:
        if cmd in ("check", "sanitize"):
            if _ig is None:
                return "injection_guard (core) tidak tersedia"
            # 1) Emergency stop (konsistensi gerbang; read-only tetap dihentikan)
            if is_stopped():
                return "⛔ EMERGENCY STOP aktif."
            # 2) Policy gate
            if _decide is not None:
                d = _decide("guard.check")
                if d.get("decision") == "deny":
                    return f"⛔ DITOLAK policy: {d.get('reason', '')}"
            text = str(p.get("text") or "")
            if not text.strip():
                return "❌ text kosong — sertakan teks yang mau diperiksa"
            # 3) Audit + jalankan
            if _audit:
                _audit({"skill": "injection_guard_skill", "action": "guard.check",
                        "target": str(p.get("source") or cmd)[:60],
                        "result": "success", "correlation_id": _corr()})
            return _ig.injection_guard({"cmd": cmd, "text": text,
                                        "source": p.get("source")})

        return ("Injection Guard Skill — cmd: check (deteksi pola injection) | "
                "sanitize (bentuk aman/blokir + sumber). Read-only.")
    except Exception as e:
        return f"injection_guard_skill gagal: {e}"


TOOL = {
    "name": "injection_guard_skill",
    "description": (
        "Periksa teks dari internet/file sebelum dipakai: check=deteksi "
        "percobaan prompt-injection, sanitize=tampilkan bentuk aman atau "
        "blokir. Read-only."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING", "description": "check | sanitize"},
            "text": {"type": "STRING", "description": "Teks yang mau diperiksa"},
            "source": {"type": "STRING", "description": "Nama sumber (reddit, web, file)"},
        },
        "required": [],
    },
    "handler": injection_guard_skill,
}
