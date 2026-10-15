#memory_compaction.py
"""Skill Memory Compaction — kesehatan long-term memory (Tahap 5).

cmd: analyze (read-only) | compact (butuh confirm=true untuk menulis).
Selalu backup sebelum kompaksi; entri tua diARSIPKAN, bukan dihapus.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

try:
    from core import memory_compaction as mc
except Exception:  # pragma: no cover
    mc = None

try:
    from core.policy_engine import decide
except Exception:
    decide = None

try:
    from core.audit_logger import log_command, new_correlation_id
except Exception:
    def log_command(**kw): pass
    def new_correlation_id(): return ""


def memory_compaction(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "analyze").strip().lower()
    confirm = bool(p.get("confirm") or p.get("confirmed"))
    t0 = time.time()
    if mc is None:
        return "❌ core.memory_compaction tidak tersedia"

    d = {"decision": "allow", "risk": "low"}
    if decide:
        try:
            d = decide("memory.compact" if cmd == "compact" else "memory.analyze")
        except Exception:
            pass
    if d.get("decision") == "deny":
        return f"⛔ Ditolak policy: memory.{cmd}"

    try:
        if cmd == "analyze":
            a = mc.analyze()
            out = ("🧠 KESEHATAN MEMORY (read-only)\n"
                   f"Ukuran   : {a['size_chars']:,} karakter\n"
                   f"Kategori : {a['categories']} | entri: {a['entries']}\n"
                   f"Duplikat : {a['dup_groups']} kelompok\n"
                   f"Tertua   : {a['oldest_updated'] or '?'}\n"
                   f"Tercatat : {a['archived_entries']} entri di arsip")
        elif cmd == "compact":
            dry = not confirm
            out = mc.compact(dry_run=dry, max_age_days=int(p.get("max_age_days") or 90))
            if dry:
                out += "\n(ℹ️ Ini simulasi — tambahkan confirm=true untuk menerapkan.)"
        else:
            out = "❌ cmd tidak dikenal. Pakai: analyze | compact."
    except Exception as e:
        out = f"❌ memory_compaction gagal: {e}"

    try:
        log_command(skill="memory_compaction", action=f"memory.{cmd}", target="",
                    decision=d.get("decision", "allow"), risk_level=d.get("risk", "low"),
                    result=out[:200], duration_ms=int((time.time() - t0) * 1000),
                    brain="skill", correlation_id=new_correlation_id())
    except Exception:
        pass
    return out


TOOL = {
    "name": "memory_compaction",
    "description": (
        "Cek kesehatan ingatan jangka-panjang Neira dan rapikan bila membengkak: "
        "hitung ukuran/entri/duplikat, lalu kompaksi (gabung duplikat, arsipkan "
        "entri tua) DENGAN backup otomatis. analyze aman; compact perlu konfirmasi."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "analyze | compact (default: analyze)"},
            "confirm": {"type": "BOOLEAN",
                        "description": "Wajib true untuk menerapkan kompaksi"},
            "max_age_days": {"type": "INTEGER",
                             "description": "Batas usia entri untuk diarsipkan (default: 90)"},
        },
        "required": [],
    },
    "handler": memory_compaction,
}
