"""
DeepSeek Chat — konektor otak ke-4 (matematika, logika, coding, penalaran panjang).

Transport: API resmi DeepSeek (OpenAI-compatible).
  POST https://api.deepseek.com/v1/chat/completions
  Header: Authorization: Bearer <DEEPSEEK_API_KEY>

Sumber kunci (urut prioritas):
  1. env DEEPSEEK_API_KEY
  2. config/api_keys.json -> "deepseek_api_key"
  3. shared/config.env -> DEEPSEEK_API_KEY

Model default: deepseek-chat (bisa dioverride via DEEPSEEK_MODEL).
Base URL default: https://api.deepseek.com/v1 (bisa dioverride via DEEPSEEK_BASE_URL).

`deepseek_ask()` mengembalikan teks jawaban; Exception = dispatcher brain_hub
lanjut ke otak berikutnya (fallback chain).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _read_env_file(path: Path) -> Dict[str, str]:
    """Parse file .env sederhana (KEY=VALUE) tanpa dependensi eksternal."""
    out: Dict[str, str] = {}
    try:
        if not path.exists():
            return out
        for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"').strip("'")
    except Exception:
        pass
    return out


def _resolve_api_key() -> Optional[str]:
    """Cari DEEPSEEK_API_KEY dari env, lalu config/api_keys.json, lalu shared/config.env."""
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if key:
        return key

    # config/api_keys.json
    try:
        cfg = _base_dir() / "config" / "api_keys.json"
        if cfg.exists():
            data = json.loads(cfg.read_text(encoding="utf-8"))
            for field in ("deepseek_api_key", "DEEPSEEK_API_KEY", "deepseek_key"):
                val = str(data.get(field, "") or "").strip()
                if val:
                    return val
    except Exception:
        pass

    # shared/config.env
    env = _read_env_file(_base_dir() / "shared" / "config.env")
    val = env.get("DEEPSEEK_API_KEY", "").strip()
    return val or None


def _resolve_base_url() -> str:
    # 1. Cek VANSROUTER_URL atau DEEPSEEK_BASE_URL dari os.environ
    base = os.environ.get("VANSROUTER_URL", "").strip() or os.environ.get("DEEPSEEK_BASE_URL", "").strip()
    if not base:
        # 2. Cek config/api_keys.json
        try:
            cfg = _base_dir() / "config" / "api_keys.json"
            if cfg.exists():
                data = json.loads(cfg.read_text(encoding="utf-8"))
                base = str(data.get("vansrouter_url", "") or "").strip()
        except Exception:
            pass
    if not base:
        # 3. Cek shared/config.env
        env = _read_env_file(_base_dir() / "shared" / "config.env")
        base = env.get("VANSROUTER_URL", "").strip() or env.get("DEEPSEEK_BASE_URL", "").strip()
    base = base or "http://127.0.0.1:20128"
    base = base.rstrip("/")
    if not base.endswith("/v1"):
        base = f"{base}/v1"
    return base


def _resolve_model() -> str:
    # 1. Cek VANSROUTER_MODEL atau DEEPSEEK_MODEL dari os.environ
    model = os.environ.get("VANSROUTER_MODEL", "").strip() or os.environ.get("DEEPSEEK_MODEL", "").strip()
    if not model:
        # 2. Cek config/api_keys.json
        try:
            cfg = _base_dir() / "config" / "api_keys.json"
            if cfg.exists():
                data = json.loads(cfg.read_text(encoding="utf-8"))
                model = str(data.get("vansrouter_model", "") or "").strip()
        except Exception:
            pass
    if not model:
        # 3. Cek shared/config.env
        env = _read_env_file(_base_dir() / "shared" / "config.env")
        model = env.get("VANSROUTER_MODEL", "").strip() or env.get("DEEPSEEK_MODEL", "").strip()
    return model or "IC/deepseek-v4-flash"


def deepseek_ask(prompt: str) -> str:
    """Kirim pertanyaan ke DeepSeek via API OpenAI-compatible.

    Raise RuntimeError bila kunci tidak ada / request gagal, sehingga
    brain_hub dapat melanjutkan ke otak berikutnya.
    """
    prompt = (prompt or "").strip()
    if not prompt:
        raise ValueError("Prompt kosong untuk DeepSeek.")

    api_key = _resolve_api_key()
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY belum diset. Isi di config/api_keys.json "
            "(field 'deepseek_api_key') atau shared/config.env."
        )

    base_url = _resolve_base_url()
    model = _resolve_model()
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Kamu adalah DeepSeek, otak penalaran Neira. Jawab ringkas, "
                    "akurat, dan langsung pada intinya. Gunakan bahasa yang sama "
                    "dengan pertanyaan pengguna."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "temperature": 0.3,
    }

    try:
        import requests
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"Modul 'requests' tidak tersedia: {e}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=120)
    except Exception as e:
        raise RuntimeError(f"Gagal menghubungi DeepSeek: {e}")

    if resp.status_code == 401:
        raise RuntimeError("DeepSeek menolak kunci API (401 Unauthorized).")
    if resp.status_code == 429:
        raise RuntimeError("DeepSeek rate-limit (429). Coba lagi nanti.")
    if resp.status_code >= 400:
        snippet = (resp.text or "")[:300]
        raise RuntimeError(f"DeepSeek error {resp.status_code}: {snippet}")

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except Exception as e:
        raise RuntimeError(f"Respons DeepSeek tidak valid: {e}")

    text = (content or "").strip()
    if not text:
        raise RuntimeError("DeepSeek mengembalikan jawaban kosong.")
    return text


def deepseek_status() -> str:
    """Ringkasan status konektor untuk brain_hub.status()."""
    key = _resolve_api_key()
    if not key:
        return "belum dikonfigurasi (DEEPSEEK_API_KEY kosong)"
    masked = key[:6] + "..." + key[-4:] if len(key) > 12 else "***"
    return f"siap · model={_resolve_model()} · key={masked}"


def deepseek_chat(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Tanya jawab via DeepSeek (matematika, logika, coding)."""
    p = parameters or {}
    prompt = str(p.get("prompt", "")).strip()
    if not prompt:
        return "Butuh 'prompt' (pertanyaan untuk DeepSeek)."
    try:
        return deepseek_ask(prompt)
    except Exception as e:
        return f"[DeepSeek] Error: {e}"


TOOL: Dict[str, Any] = {
    "name": "deepseek_chat",
    "description": (
        "Ask the DeepSeek brain (math, logic, coding, long reasoning). "
        "Uses the official OpenAI-compatible DeepSeek API."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "Pertanyaan untuk DeepSeek."},
        },
        "required": ["prompt"],
    },
    "handler": deepseek_chat,
    "behavior": "NON_BLOCKING",
}
