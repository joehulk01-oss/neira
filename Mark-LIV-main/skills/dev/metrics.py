#metrics.py
"""Skill Metrics — metrik anti-bohong Neira (Tahap 4) untuk kedua otak.

false_success_rate = klaim "sukses" yang FAKTANYA gagal / total terverifikasi.
Target blueprint: ≤ 5%. Read-mostly; reset butuh confirm=true.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

_BASE = Path(__file__).resolve().parent.parent.parent
if str(_BASE) not in sys.path:
    sys.path.insert(0, str(_BASE))

try:
    from core import metrics as m
except Exception:  # pragma: no cover
    m = None

try:
    from core.audit_logger import log_command, new_correlation_id
except Exception:
    def log_command(**kw): pass
    def new_correlation_id(): return ""


def metrics(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "stats").strip().lower()
    t0 = time.time()
    if m is None:
        return "❌ core.metrics tidak tersedia"
    try:
        if cmd == "stats":
            out = m.format_stats()
        elif cmd == "pending":
            rows = m.pending(limit=int(p.get("limit") or 10))
            if not rows:
                out = "✅ Tidak ada klaim yang menunggu verifikasi."
            else:
                lines = [f"⏳ {len(rows)} klaim belum diverifikasi:"]
                for a in rows:
                    lines.append(f"  • {a['attempt_id']} | {a['skill']}:{a['action']} "
                                 f"| {a['target'][:50]}")
                out = "\n".join(lines)
        elif cmd == "recent":
            rows = m.recent(limit=int(p.get("limit") or 10))
            lines = [f"🕘 {len(rows)} attempt terakhir:"]
            for a in rows:
                v = a.get("verified")
                tag = "✅" if v else ("❌ bohong" if v is False else "⏳ pending")
                lines.append(f"  • {tag} {a['attempt_id']} | {a['skill']}:{a['action']} "
                             f"| {a['result'][:50]}")
            out = "\n".join(lines)
        elif cmd == "reset":
            if not bool(p.get("confirm")):
                out = "⚠️ reset menghapus seluruh riwayat metrik — ulangi dengan confirm=true."
            else:
                from core import metrics as _m
                _m._save({"attempts": [], "updated_at": _m._now()})
                out = "✅ Riwayat metrik direset."
        else:
            out = "❌ cmd tidak dikenal. Pakai: stats | pending | recent | reset."
    except Exception as e:
        out = f"❌ metrics gagal: {e}"

    try:
        log_command(skill="metrics", action=f"metrics.{cmd}", target="",
                    decision="allow", risk_level="low", result=out[:200],
                    duration_ms=int((time.time() - t0) * 1000),
                    brain="skill", correlation_id=new_correlation_id())
    except Exception:
        pass
    return out


TOOL = {
    "name": "metrics",
    "description": (
        "Lihat metrik kejujuran Neira: false_success_rate (klaim sukses yang "
        "faktanya gagal), daftar klaim yang belum diverifikasi ke realita, dan "
        "riwayat attempt terakhir. Panggil untuk audit diri berkala."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "stats | pending | recent | reset (default: stats)"},
            "limit": {"type": "INTEGER",
                      "description": "Jumlah baris untuk pending/recent (default: 10)"},
            "confirm": {"type": "BOOLEAN",
                        "description": "Wajib true untuk reset"},
        },
        "required": [],
    },
    "handler": metrics,
}
