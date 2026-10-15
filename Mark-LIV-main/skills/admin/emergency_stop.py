# emergency_stop.py
"""
emergency_stop.py — Tombol STOP ALL Neira (Blueprint Tahap 1, §15).

Perintah yang HARUS selalu dikenali: stop / berhenti / batalkan / cancel /
jangan lanjut / pause. Saat aktif:

  - event global ter-set → skill loop lain bisa cek is_stopped() di tiap iterasi
  - TIDAK ada retry otomatis selagi berhenti
  - alasan + timestamp dicatat ke audit log
  - resume() hanya lewat perintah eksplisit user ("lanjutkan")

Pemakaian dari skill lain:
    from skills.admin.emergency_stop import is_stopped
    for step in steps:
        if is_stopped():
            return "⛔ Dihentikan oleh emergency stop."

Auto-discovered via TOOL dict — kedua otak bisa memanggil:
    {"action": "emergency_stop", "cmd": "stop",  "reason": "user bilang stop"}
    {"action": "emergency_stop", "cmd": "status"}
    {"action": "emergency_stop", "cmd": "resume"}
"""
from __future__ import annotations

import threading
import time

try:
    from core.audit_logger import log_event
except Exception:                                        # pragma: no cover
    def log_event(event: dict) -> bool:                  # type: ignore
        return False

# Kata/frasa stop — dipakai juga main.py untuk deteksi suara (blueprint §15)
STOP_PHRASES = (
    "stop", "berhenti", "batalkan", "cancel", "jangan lanjut",
    "hentikan", "cukup", "pause", "jeda",
)

_event = threading.Event()
_state_lock = threading.Lock()
_state: dict = {"reason": "", "at": "", "by": ""}


def is_stopped() -> bool:
    """True selagi emergency stop aktif — cek di setiap iterasi loop skill."""
    return _event.is_set()


def stop_reason() -> str:
    return _state.get("reason", "")


def trigger(reason: str = "", by: str = "user") -> str:
    """Aktifkan stop global. Aman dipanggil berkali-kali (idempotent)."""
    with _state_lock:
        first = not _event.is_set()
        _state["reason"] = reason or "tidak disebutkan"
        _state["at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _state["by"] = by
    _event.set()
    if first:
        log_event({"skill": "emergency_stop", "action": "stop.all",
                   "target": reason, "decision": "allow", "risk_level": "critical",
                   "result": "stopped", "actor": by,
                   "note": "EMERGENCY STOP diaktifkan"})
    return f"⛔ SEMUA aksi dihentikan. Alasan: {_state['reason']}"


def resume(by: str = "user") -> str:
    """Lepaskan stop — HANYA dari perintah eksplisit user."""
    with _state_lock:
        had = _event.is_set()
        _state.update({"reason": "", "at": "", "by": ""})
    _event.clear()
    if had:
        log_event({"skill": "emergency_stop", "action": "resume",
                   "decision": "allow", "result": "resumed", "actor": by})
    return "▶️ Emergency stop dilepas — Neira boleh bekerja lagi."


def status() -> str:
    if _event.is_set():
        return (f"⛔ EMERGENCY STOP AKTIF sejak {_state['at']} "
                f"(oleh {_state['by']}) — alasan: {_state['reason']}. "
                "Tidak ada skill yang boleh jalan. Ucapkan 'lanjutkan' untuk melepas.")
    return "▶️ Tidak ada stop aktif — semua sistem boleh berjalan normal."


def matches_stop_phrase(text: str) -> bool:
    """Cocokkan teks user dengan frasa stop (dipakai router/main)."""
    t = (text or "").strip().lower()
    return any(p == t or (len(p) > 3 and p in t) for p in STOP_PHRASES)


def emergency_stop(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or p.get("action_cmd") or "status").lower().strip()
    reason = str(p.get("reason") or p.get("note") or "").strip()
    try:
        if cmd in ("stop", "stop_all", "stopall", "halt", "kill_all"):
            return trigger(reason, by=str(p.get("by") or "user"))
        if cmd in ("resume", "continue", "lanjut", "lanjutkan", "clear"):
            return resume()
        return status()
    except Exception as e:
        return f"emergency_stop gagal: {e}"


TOOL = {
    "name": "emergency_stop",
    "description": (
        "Tombol darurat: hentikan SEMUA aksi Neira yang sedang berjalan "
        "(stop/berhenti/batalkan), cek status stop, atau lanjutkan kembali "
        "setelah user berkata 'lanjutkan'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "stop | status | resume (default: status)"},
            "reason": {"type": "STRING",
                       "description": "Alasan penghentian (untuk stop)"},
        },
        "required": [],
    },
    "handler": emergency_stop,
}
