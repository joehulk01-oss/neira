"""
Duck Chat — konektor otak ke-3 (DuckDuckGo AI Chat, anonim, tanpa login).

PLACEHOLDER: fungsi `duck_ask()` sudah dipanggil oleh core/brain_hub.py, tapi
logika transportnya belum diisi. Rencana pengisian (butuh riset API seperti
scratch/dola_research/):
  1. Cari endpoint chat DuckDuckGo (duckduckgo.com/aichat atau duck.ai).
  2. Isi `duck_ask()` dengan request HTTP (anonim / rotasi vqd token).
  3. Kembalikan teks jawaban; lempar Exception bila gagal (dispatcher lanjut
     otak berikutnya).

Begitu `duck_ask()` diisi, otak ke-3 otomatis aktif di brain_hub tanpa ubah kode lain.
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


def duck_ask(prompt: str) -> str:
    """Kirim pertanyaan ke DuckDuckGo AI Chat. BELUM terisi — implementasi menyusul."""
    raise NotImplementedError(
        "Konektor Duck belum diisi. Tahap berikutnya: riset API duck.ai lalu "
        "isi fungsi ini (lihat docstring modul untuk resepnya)."
    )


def duck_chat(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Tanya jawab via DuckDuckGo AI Chat (anonim)."""
    p = parameters or {}
    prompt = str(p.get("prompt", "")).strip()
    if not prompt:
        return "Butuh 'prompt' (pertanyaan untuk Duck AI)."
    try:
        return duck_ask(prompt)
    except NotImplementedError as e:
        return f"[Duck] Konektor belum aktif: {e}"
    except Exception as e:
        return f"[Duck] Error: {e}"


TOOL: Dict[str, Any] = {
    "name": "duck_chat",
    "description": (
        "Ask the DuckDuckGo AI Chat brain (anonymous, no login, fast quick-chat "
        "answers). NOTE: connector not implemented yet — returns a clear notice."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "Pertanyaan untuk Duck AI."},
        },
        "required": ["prompt"],
    },
    "handler": duck_chat,
    "behavior": "NON_BLOCKING",
}
