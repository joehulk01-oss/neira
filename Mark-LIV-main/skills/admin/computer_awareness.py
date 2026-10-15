#computer_awareness.py
"""Skill Computer Awareness — lihat kondisi PC (READ-ONLY) untuk kedua otak.

Snapshot: CPU/RAM/baterai/uptime/layar/jendela aktif/daftar jendela/top RAM.
Tidak mengubah apa pun. Kendali jendela → skills/admin/window_manager.py.
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
        snapshot, format_snapshot, active_window, window_entries,
    )
except Exception:  # pragma: no cover
    def snapshot(): return {}
    def format_snapshot(_s): return "❌ core.computer_awareness tidak tersedia"
    def active_window(): return {}
    def window_entries(): return []

try:
    from core.policy_engine import decide
except Exception:
    decide = None

try:
    from core.audit_logger import log_command, new_correlation_id
except Exception:
    def log_command(**kw): pass
    def new_correlation_id(): return ""


def computer_awareness(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = (p.get("cmd") or "snapshot").strip().lower()
    t0 = time.time()

    d = {"decision": "allow", "risk": "low"}
    if decide:
        try:
            d = decide("awareness.snapshot", cmd=cmd)
        except Exception:
            pass
    if d.get("decision") == "deny":
        return f"⛔ Ditolak policy: awareness.{cmd} — {d.get('reason', '')}"

    try:
        if cmd == "snapshot":
            out = format_snapshot(snapshot())
        elif cmd == "active":
            a = active_window()
            out = (f"✅ Jendela aktif: [{a.get('pid', 0)}] "
                   f"{a.get('process') or '?'} — {a.get('title') or '(tanpa judul)'}")
        elif cmd == "windows":
            ws = window_entries()
            lines = [f"✅ {len(ws)} jendela terlihat:"]
            for w in ws[:20]:
                lines.append(f"  • pid {w['pid']} | {w['title'][:70]}")
            out = "\n".join(lines)
        else:
            out = f"❌ cmd tidak dikenal: '{cmd}'. Pakai: snapshot | active | windows."
    except Exception as e:
        out = f"❌ awareness gagal: {e}"

    try:
        log_command(skill="computer_awareness", action=f"awareness.{cmd}",
                    target="", decision=d.get("decision", "allow"),
                    risk_level=d.get("risk", "low"), result=out[:200],
                    duration_ms=int((time.time() - t0) * 1000),
                    brain="skill", correlation_id=new_correlation_id())
    except Exception:
        pass
    return out


# ── Tool declaration (auto-discovered oleh core/skill_hub.py) ────────────────
TOOL = {
    "name": "computer_awareness",
    "description": (
        "Lihat kondisi PC saat ini (read-only): CPU, RAM, baterai, uptime, "
        "layar, jendela yang sedang aktif, daftar jendela terlihat, dan "
        "aplikasi pemakan RAM terbesar. Panggil dulu sebelum mengendalikan "
        "jendela atau menjawab 'apa yang terbuka'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {
                "type": "STRING",
                "description": "snapshot | active | windows (default: snapshot)",
            },
        },
        "required": [],
    },
    "handler": computer_awareness,
}
