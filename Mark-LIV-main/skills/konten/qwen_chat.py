"""
Qwen Chat — konektor otak ke-5 (multibahasa, dokumen, konten panjang, riset).

PLACEHOLDER: fungsi `qwen_ask()` sudah dipanggil oleh core/brain_hub.py, tapi
logika transportnya belum diisi. Rencana pengisian:
  1. Opsi A (gratis via web): riset API web Qwen/Chat (tongyi.aliyun.com) seperti
     scratch/dola_research/ — login sekali → cookie → replay endpoint chat.
  2. Opsi B (gratis/bayar): DashScope API (DASHSCOPE_API_KEY di shared/config.env).
  3. Isi `qwen_ask()` — kembalikan teks jawaban; Exception = dispatcher lanjut.

Begitu `qwen_ask()` diisi, otak ke-5 otomatis aktif di brain_hub.
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


def qwen_ask(prompt: str) -> str:
    """Kirim pertanyaan ke Qwen. BELUM terisi — implementasi menyusul."""
    raise NotImplementedError(
        "Konektor Qwen belum diisi. Tahap berikutnya: riset endpoint web Qwen "
        "atau aktifkan DASHSCOPE_API_KEY (lihat docstring modul)."
    )


def qwen_chat(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Tanya jawab via Qwen (multibahasa, dokumen, konten panjang)."""
    p = parameters or {}
    prompt = str(p.get("prompt", "")).strip()
    if not prompt:
        return "Butuh 'prompt' (pertanyaan untuk Qwen)."
    try:
        return qwen_ask(prompt)
    except NotImplementedError as e:
        return f"[Qwen] Konektor belum aktif: {e}"
    except Exception as e:
        return f"[Qwen] Error: {e}"


TOOL: Dict[str, Any] = {
    "name": "qwen_chat",
    "description": (
        "Ask the Qwen brain (multilingual, documents, long-form content, research). "
        "NOTE: connector not implemented yet — returns a clear notice."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "Pertanyaan untuk Qwen."},
        },
        "required": ["prompt"],
    },
    "handler": qwen_chat,
    "behavior": "NON_BLOCKING",
}
