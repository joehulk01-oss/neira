# orchestrator.py — Skill wrapper untuk core/jarvis_orchestrator.py
"""
orchestrator.py — Skill eksekusi tugas multi-langkah (Blueprint Tahap 2).

Logika inti ada di core/jarvis_orchestrator.py (job_manager + policy_engine +
audit_logger + emergency_stop). File ini adalah jembatan TOOL agar KEDUA otak
(Gemini via action_loader, Hermes via skill_hub) bisa memanggilnya — skill_hub
hanya memindai folder skills/.

Contoh:
  {"action": "orchestrator", "cmd": "run", "goal": "rapikan desktop",
   "steps": [{"skill": "desktop_control", "params": {"mode": "by_type"},
              "policy_action": "desktop.organize"}]}
  {"action": "orchestrator", "cmd": "status"}
  {"action": "orchestrator", "cmd": "run", "job_id": "job-202610-xxxx", "confirm": true}
  {"action": "orchestrator", "cmd": "cancel", "job_id": "job-202610-xxxx"}
"""
from __future__ import annotations

try:
    from core.jarvis_orchestrator import orchestrator as _handler
except Exception:                                     # pragma: no cover
    def _handler(parameters=None, params=None, **kw):  # type: ignore[misc]
        return "orchestrator: core/jarvis_orchestrator.py tidak bisa diimpor."


def orchestrator(parameters: dict = None, params: dict = None, **kwargs) -> str:
    return _handler(parameters, params, **kwargs)


TOOL = {
    "name": "orchestrator",
    "description": (
        "Jalankan tugas multi-langkah secara terstruktur: setiap langkah lewat "
        "policy gate (denay/confirm/allow), konfirmasi user untuk aksi berisiko, "
        "retry 1x per langkah, anti double-run, status tersimpan (job_id), bisa "
        "dijeda emergency-stop dan dibatalkan. Untuk tugas panjang berurutan."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "run | status | cancel (default: run)"},
            "goal": {"type": "STRING",
                     "description": "Tujuan tugas (wajib untuk run baru)"},
            "steps": {"type": "ARRAY",
                      "description": ("Langkah berurutan: [{\"skill\": \"open_app\", "
                                      "\"params\": {...}, \"policy_action\": \"app.open\"}]")},
            "job_id": {"type": "STRING",
                       "description": "ID job untuk resume/status/cancel"},
            "confirm": {"type": "BOOLEAN",
                        "description": "true setelah user menyetujui langkah berisiko"},
            "risk_level": {"type": "STRING",
                           "description": "low | medium | high (default: medium)"},
        },
        "required": [],
    },
    "handler": orchestrator,
}
