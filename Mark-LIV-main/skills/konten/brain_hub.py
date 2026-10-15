"""
Brain Hub — gerbang 5 otak AI gratis (dispatcher).

Proyek "5 otak": 1 Hermes (inti utama), 2 Dola, 3 Duck, 4 DeepSeek, 5 Qwen.
Masing-masing punya keunggulan; dispatcher memilih otak terbaik dari tag tugas
dan punya rantai fallback — kalau otak pertama gagal, otak berikutnya mencoba.

Aksi:
  ask     : kirim tugas ke otak terbaik (atau otak pilihan via 'brain').
  status  : laporan 5 otak (keunggulan + kesiapan).
  route   : lihat urutan otak yang dipilih untuk sebuah teks tugas.
  brains  : daftar otak + keunggulannya.

Dipakai Neira & inti otak via SkillHub. Implementasi: core/brain_hub.py.
"""
from __future__ import annotations

import sys
from typing import Any, Dict

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from core.brain_hub import brain_hub
    _IMPORT_ERR = None
except Exception as _e:  # pragma: no cover
    brain_hub = None
    _IMPORT_ERR = _e


def brain_hub_skill(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Dispatcher 5 otak AI: ask (otak terbaik / pilihan), status, route, brains."""
    if _IMPORT_ERR is not None:
        return f"Skill brain_hub tidak bisa diimpor: {_IMPORT_ERR}"

    p = parameters or {}
    action = str(p.get("action", "ask")).strip().lower()
    prompt = str(p.get("prompt", "")).strip()
    brain = str(p.get("brain", "")).strip().lower() or None

    try:
        if action == "ask":
            if not prompt:
                return "Butuh 'prompt' (tugas yang mau dikerjakan otak)."
            if brain:
                answer = brain_hub.ask(brain, prompt)
                b = brain_hub.get(brain)
                label = b.label if b else brain
                return f"[{label}]\n{answer}"
            res = brain_hub.ask_best(prompt)
            if res.get("answer"):
                return f"[{res['label']}]\n{res['answer']}"
            detail = "\n".join(res.get("attempts", []))
            return f"Semua otak gagal menjawab.\n{detail}"

        if action == "route":
            if not prompt:
                return "Butuh 'prompt' untuk melihat rute otak."
            chain = brain_hub.route(prompt)
            tags = brain_hub.detect_tags(prompt)
            return (
                f"Tag tugas terdeteksi: {', '.join(tags) if tags else '(umum)'}\n"
                f"Urutan otak: {' → '.join(chain)}"
            )

        if action == "brains":
            lines = ["# 5 OTAK — keunggulan masing-masing"]
            for b in brain_hub.list_brains():
                lines.append(f"- {b.label} [{b.key}]: {b.summary}")
                lines.append(f"    keunggulan: {', '.join(b.strengths)}")
            return "\n".join(lines)

        if action == "status":
            return brain_hub.status_report()

        return (
            "Aksi tidak dikenal. Pilihan action: ask | route | brains | status "
            "(param: prompt, brain = hermes/dola/duck/deepseek/qwen)."
        )
    except Exception as e:
        return f"[BrainHub] Error: {e}"


TOOL: Dict[str, Any] = {
    "name": "brain_hub",
    "description": (
        "Dispatch a task to one of 5 free AI brains (hermes=main/deep reasoning, "
        "dola=search/write/translate/multimode, duck=quick anonymous chat, "
        "deepseek=math/logic/code, qwen=content/multilingual/docs) with automatic "
        "best-brain routing and fallback chain. Actions: ask, route, brains, status."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "ask = kirim tugas; route = lihat urutan otak utk teks; brains = daftar otak; status = kesiapan.",
                "enum": ["ask", "route", "brains", "status"],
            },
            "prompt": {"type": "STRING", "description": "Tugas / pertanyaan (wajib utk ask & route)."},
            "brain": {
                "type": "STRING",
                "description": "Paksa otak tertentu (opsional).",
                "enum": ["hermes", "dola", "duck", "deepseek", "qwen"],
            },
        },
        "required": ["action"],
    },
    "handler": brain_hub_skill,
    "behavior": "NON_BLOCKING",
}
