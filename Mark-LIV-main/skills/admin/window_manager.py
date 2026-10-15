#window_manager.py
"""Skill Window Manager — kendali jendela Neira (Tahap 3, blueprint §6).

Semua aksi lewat 3 gerbang wajib (urutan konsisten dgn orchestrator):
  1. EMERGENCY STOP  — is_stopped() → tolak semua aksi
  2. POLICY GATE     — decide("window.<cmd>", target=...) → deny/confirm/allow
  3. AUDIT           — log_command ke audit/events.jsonl

cmd:
  list      : daftar jendela terlihat (policy: window.list)
  active    : jendela yang sedang fokus (policy: window.active)
  focus     : bawa jendela ke depan (policy: window.focus)
  minimize / maximize / restore (policy: window.minimize|window.maximize|window.restore)
  close     : tutup jendela sopan (WM_CLOSE) (policy: window.close → confirm!)
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

try:
    from core.computer_awareness import (
        window_entries, active_window, proc_name, IS_WINDOWS,
        SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE,
    )
except Exception:  # pragma: no cover
    IS_WINDOWS = False
    def window_entries(): return []
    def active_window(): return {}
    def proc_name(_pid): return ""

try:
    from core.policy_engine import decide, deny_message, confirm_message
except Exception:
    decide = None
    def deny_message(**_k): return "⛔ Ditolak policy."
    def confirm_message(**_k): return "⚠️ Perlu konfirmasi."

try:
    from skills.admin.emergency_stop import is_stopped
except Exception:
    def is_stopped(): return False

try:
    from core.audit_logger import log_command, new_correlation_id
except Exception:
    def log_command(**kw): pass
    def new_correlation_id(): return ""

try:
    from core.action_loader import get_audit_context  # type: ignore
except Exception:
    def get_audit_context():  # type: ignore
        return {}


def _user32():
    import ctypes
    return ctypes.windll.user32


def _find_windows(target: str) -> list:
    """Cari jendela berdasar PID, judul (case-insensitive substring), atau nama proses."""
    t = (target or "").strip().lower()
    if not t:
        return []
    wins = window_entries()
    # 1) PID eksak
    if t.isdigit():
        return [w for w in wins if w["pid"] == int(t)]
    # 2) substring judul
    hit = [w for w in wins if t in w["title"].lower()]
    if hit:
        return hit
    # 3) nama proses
    return [w for w in wins if proc_name(w["pid"]) == t or
            proc_name(w["pid"]).startswith(t)]


def _fmt_windows(wins: list, limit: int = 20) -> str:
    lines = [f"🪟 {len(wins)} jendela terlihat:"]
    for w in wins[:limit]:
        lines.append(f"  • [{w['pid']}] {proc_name(w['pid']) or '?'} — {w['title'][:70]}")
    if len(wins) > limit:
        lines.append(f"  … +{len(wins) - limit} lagi")
    return "\n".join(lines)


def _show(wins: list, cmd_const: int) -> int:
    u = _user32()
    n = 0
    for w in wins:
        try:
            if u.ShowWindow(w["hwnd"], cmd_const):
                n += 1
        except Exception:
            pass
    return n


def _focus_one(w: dict) -> str:
    u = _user32()
    import ctypes
    try:
        # Trik ALT-tap: Windows menolak SetForegroundWindow dari proses lain
        # kecuali ada input event terbaru (keybd_event menipu aturan ini).
        u.keybd_event(0x12, 0, 0, 0)          # ALT down
        try:
            u.SetForegroundWindow(w["hwnd"])
        finally:
            u.keybd_event(0x12, 0, 2, 0)      # ALT up (KEYEVENTF_KEYUP)
        if u.GetForegroundWindow() == w["hwnd"]:
            return f"✅ Fokus: [{w['pid']}] {w['title'][:60]}"
        # fallback: restore dulu lalu coba lagi
        u.ShowWindow(w["hwnd"], SW_RESTORE)
        u.SetForegroundWindow(w["hwnd"])
        if u.GetForegroundWindow() == w["hwnd"]:
            return f"✅ Fokus (setelah restore): [{w['pid']}] {w['title'][:60]}"
        return f"⚠️ Windows menolak pindah fokus ke '{w['title'][:50]}'"
    except Exception as e:
        return f"❌ focus gagal: {e}"


def _close_one(w: dict) -> str:
    u = _user32()
    try:
        # WM_CLOSE = sopan (aplikasi boleh menolak / menyimpan dulu).
        # Bukan kill — kill tetap di app_manager (policy app.kill).
        if u.PostMessageW(w["hwnd"], 0x0010, 0, 0):
            return f"✅ Sinyal tutup dikirim ke [{w['pid']}] {w['title'][:60]} (tunggu aplikasi menutup sendiri)"
        return f"❌ Gagal kirim WM_CLOSE ke '{w['title'][:50]}'"
    except Exception as e:
        return f"❌ close gagal: {e}"


def _audit(action: str, target: str, d: dict, result: str, t0: float) -> None:
    try:
        log_command(skill="window_manager", action=action, target=target[:80],
                    decision=d.get("decision", "allow"),
                    risk_level=d.get("risk", "low"), result=result[:200],
                    duration_ms=int((time.time() - t0) * 1000),
                    brain="skill", correlation_id=new_correlation_id())
    except Exception:
        pass


def window_manager(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "list").strip().lower()
    target = str(p.get("target") or "").strip()
    confirm = bool(p.get("confirm") or p.get("confirmed"))
    t0 = time.time()

    # ── Gerbang 1: emergency stop ────────────────────────────────────────────
    if is_stopped():
        return "⛔ Emergency stop aktif — semua aksi jendela dihentikan. Ucapkan 'lanjutkan' untuk melepas."

    if not IS_WINDOWS:
        return "❌ window_manager hanya untuk Windows."

    action = f"window.{cmd}"

    # ── Gerbang 2: policy gate ───────────────────────────────────────────────
    d = {"decision": "allow", "risk": "low", "reason": ""}
    if decide:
        try:
            d = decide(action, target=target)
        except Exception:
            pass
    if d.get("decision") == "deny":
        out = f"⛔ Ditolak policy: {action}" + (f" — {d.get('reason')}" if d.get("reason") else "")
        _audit(action, target, d, out, t0)
        return out
    if d.get("decision") == "confirm" and not confirm:
        out = (f"⚠️ Aksi '{action}' (risk {d.get('risk', '?')}) butuh konfirmasi user. "
               "Ulangi dengan confirm=true setelah user menyetujui.")
        _audit(action, target, d, out, t0)
        return out

    # ── Eksekusi ─────────────────────────────────────────────────────────────
    try:
        if cmd == "list":
            out = _fmt_windows(window_entries())
        elif cmd == "active":
            a = active_window()
            out = (f"✅ Jendela aktif: [{a.get('pid', 0)}] "
                   f"{a.get('process') or '?'} — {a.get('title') or '(tanpa judul)'}")
        elif cmd == "focus":
            wins = _find_windows(target)
            if not wins:
                out = f"❌ Jendela '{target}' tidak ditemukan. Coba cmd=list dulu."
            else:
                out = _focus_one(wins[0])
        elif cmd in ("minimize", "maximize", "restore"):
            const = {"minimize": SW_MINIMIZE, "maximize": SW_MAXIMIZE, "restore": SW_RESTORE}[cmd]
            wins = _find_windows(target)
            if not wins:
                out = f"❌ Jendela '{target}' tidak ditemukan. Coba cmd=list dulu."
            else:
                n = _show(wins, const)
                out = f"✅ {cmd} → {n}/{len(wins)} jendela: {', '.join(w['title'][:40] for w in wins[:3])}"
        elif cmd == "close":
            wins = _find_windows(target)
            if not wins:
                out = f"❌ Jendela '{target}' tidak ditemukan. Coba cmd=list dulu."
            else:
                out = "\n".join(_close_one(w) for w in wins[:5])
        else:
            out = ("❌ cmd tidak dikenal. Pakai: list | active | focus | "
                   "minimize | maximize | restore | close.")
    except Exception as e:
        out = f"❌ window_manager gagal: {e}"

    _audit(action, target, d, out, t0)
    return out


# ── Tool declaration (auto-discovered oleh core/skill_hub.py) ────────────────
TOOL = {
    "name": "window_manager",
    "description": (
        "Kendalikan jendela di layar: lihat daftar jendela, cek jendela aktif, "
        "pindah fokus, minimize/maximize/restore, dan tutup jendela secara sopan "
        "(close sopan, bukan paksa mati — itu app_manager)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {
                "type": "STRING",
                "description": ("list | active | focus | minimize | maximize | "
                                "restore | close (default: list)"),
            },
            "target": {
                "type": "STRING",
                "description": ("PID, judul jendela, atau nama proses — wajib "
                                "untuk focus/minimize/maximize/restore/close"),
            },
            "confirm": {
                "type": "BOOLEAN",
                "description": "true bila user sudah menyetujui aksi berisiko (close)",
            },
        },
        "required": [],
    },
    "handler": window_manager,
}
