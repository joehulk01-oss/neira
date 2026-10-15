#self_heal.py
"""Skill Self-Heal — lihat rencana pemulihan langkah gagal (Tahap 5).

Orchestrator SUDAH otomatis memakai fallback saat langkah gagal
(core/self_healing.try_recover). Skill ini untuk manusia/otak melihat:
skill mana punya fallback, dan fallback-nya masih terdaftar atau tidak.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

try:
    from core import self_healing as sh
except Exception:  # pragma: no cover
    sh = None

try:
    from core.audit_logger import log_command, new_correlation_id
except Exception:
    def log_command(**kw): pass
    def new_correlation_id(): return ""


def self_heal(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "map").strip().lower()
    target = str(p.get("skill") or p.get("target") or "").strip().lower()
    t0 = time.time()
    if sh is None:
        return "❌ core.self_healing tidak tersedia"
    try:
        if cmd == "map":
            lines = ["🩺 PETA PEMULIHAN (skill → fallback):"]
            for k in sorted(sh.RECOVERY_SKILLS):
                fb = sh.RECOVERY_SKILLS[k]
                ok = "✅" if (sh._hub and sh._hub.has(fb)) else "❌ tidak terdaftar"
                lines.append(f"  • {k} → {fb} {ok}")
            out = "\n".join(lines)
        elif cmd == "plan":
            if not target:
                out = "❌ Sebut skill: {\"cmd\": \"plan\", \"skill\": \"dola_chat\"}"
            else:
                plan = sh.recovery_plan(target)
                out = (f"🩺 {target}: " + ("tidak ada fallback — gagal = gagal jujur."
                       if not plan else
                       "; ".join(f"{s['strategy']} → {s['target']} "
                                 f"({'tersedia' if s['available'] else 'TIDAK ADA'})"
                                 for s in plan)))
        else:
            out = "❌ cmd tidak dikenal. Pakai: map | plan."
    except Exception as e:
        out = f"❌ self_heal gagal: {e}"

    try:
        log_command(skill="self_heal", action=f"selfheal.{cmd}", target=target,
                    decision="allow", risk_level="low", result=out[:200],
                    duration_ms=int((time.time() - t0) * 1000),
                    brain="skill", correlation_id=new_correlation_id())
    except Exception:
        pass
    return out


TOOL = {
    "name": "self_heal",
    "description": (
        "Tampilkan peta pemulihan Neira: skill mana yang punya fallback otomatis "
        "saat gagal, dan cek rencana pemulihan untuk satu skill tertentu."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING", "description": "map | plan (default: map)"},
            "skill": {"type": "STRING",
                      "description": "Nama skill untuk cmd=plan"},
        },
        "required": [],
    },
    "handler": self_heal,
}
