# self_healing.py
"""Tahap 5 — Self-Healing (blueprint): langkah gagal tidak boleh langsung
menyerah, tapi juga TIDAK BOLEH pura-pura sukses. Strategi:

  1. FALLBACK SKILL — jika skill utama gagal dan ada pemetaan fallback
     yang dikenal, coba fallback SEKALI (tetap lewat skill_hub + policy).
  2. Tanpa fallback yang aman → biarkan orchestrator melapor jujur
     (failed / reconciliation_required).

Pemetaan hanya berisi pasangan yang fallback-nya benar-benar terdaftar
di skill_hub — divalidasi saat eksekusi (anti-bohong: fallback fiktif
tidak akan pernah dipakai).
"""
from __future__ import annotations

try:
    from core.skill_hub import skill_hub as _hub
except Exception:
    _hub = None

# skill utama → fallback aman (semua fallback WAJIB ada di skills/)
RECOVERY_SKILLS: dict = {
    "browser_agent": "browser_control",
    "browser_skill": "browser_control",
    "dola_chat": "duck_chat",
    "deepseek_chat": "qwen_chat",
    "web_search": "duck_chat",
    "open_app": "app_manager",
    "desktop_control": "computer_control",
}

_BAD_PREFIX = ("failed", "❌", "⛔", "⚠️")


def recovery_plan(skill: str) -> list:
    """Rencana pemulihan untuk satu skill (untuk ditampilkan, read-only)."""
    fb = RECOVERY_SKILLS.get((skill or "").strip().lower(), "")
    if not fb:
        return []
    ok = bool(_hub and _hub.has(fb))
    return [{"strategy": "fallback_skill", "target": fb,
             "available": ok}]


def try_recover(skill: str, params: dict, error: str = ""):
    """Coba pulihkan langkah gagal via fallback skill (maks. SATU percobaan).
    Return (output, fallback_name) bila berhasil; None bila tidak ada jalan."""
    fb = RECOVERY_SKILLS.get((skill or "").strip().lower(), "")
    if not fb:
        return None
    if _hub is None or not _hub.has(fb):
        return None          # fallback fiktif → jangan bohong, biarkan gagal jujur
    try:
        out = _hub.run(fb, dict(params or {}))
        out = str(out or "")
    except Exception:
        return None
    if not out or out.strip().startswith(_BAD_PREFIX):
        return None
    return out, fb
