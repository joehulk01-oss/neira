"""
Otak Dola — brain skill Neira yang terhubung ke chat.dola.com.

Ini adalah "otak" (brain) Neira yang menjawab pertanyaan via Dola AI.
Dola mendukung 12 mode percakapan (hasil riset endpoint):
  completion, search, deep_search, write, translate, coding,
  music, image, read_web, academic, doc, edu.

Mode otomatis terdeteksi dari isi pertanyaan
(misal "terjemah ..." → mode translate, "cari ..." → mode search).

Aksi:
  ask    : tanya jawab via Dola (param: prompt, mode opsional)
  setup  : login sekali via browser — cookie akun disimpan ke pool
  status : cek kesiapan otak (akun, template payload, mode)
  modes  : daftar semua mode percakapan yang tersedia

Dipakai Neira via SkillHub. Implementasi: core/dola_client.py + core/dola_pool.py.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = _base_dir()

# 12 mode percakapan Dola (hasil riset find_all_chat_endpoints.py)
DOLA_MODES: Dict[str, str] = {
    "completion": "Tanya jawab umum",
    "search": "Pencarian web",
    "deep_search": "Riset mendalam",
    "write": "Menulis artikel / konten",
    "translate": "Terjemahan bahasa",
    "coding": "Kode & programming",
    "music": "Musik, lagu, lirik",
    "image": "Buat gambar / ilustrasi",
    "read_web": "Baca & rangkum website",
    "academic": "Riset akademik",
    "doc": "Chat dengan dokumen",
    "edu": "Latihan edukasi",
}

# Kata kunci → mode (deteksi otomatis dari pertanyaan)
_MODE_KEYWORDS: Dict[str, list] = {
    "search": [
        "cari", "search", "siapa", "apa itu", "kapan", "dimana",
        "terbaru", "berita", "harga", "price",
    ],
    "write": [
        "tulis", "write", "artikel", "caption", "naskah", "essay",
        "puisi", "cerita", "story", "copywriting", "draft",
    ],
    "translate": [
        "terjemah", "translate", "alih bahasa",
        "dalam bahasa inggris", "dalam bahasa indonesia",
        "ke inggris", "ke indonesia",
    ],
    "coding": [
        "kode", "code", "script", "fungsi", "function", "bug", "error",
        "python", "javascript", "program", "compile", "refactor", "debug",
    ],
    "music": ["musik", "music", "lagu", "song", "lirik", "chord", "playlist"],
    "image": [
        "gambar", "image", "foto", "picture", "ilustrasi",
        "desain grafis", "poster",
    ],
    "deep_search": [
        "riset", "research", "studi mendalam",
        "analisis mendalam", "deep search",
    ],
}


def _detect_mode(prompt: str) -> str:
    """Deteksi mode Dola dari isi pertanyaan (default: completion)."""
    low = (prompt or "").lower()
    scores: Dict[str, int] = {}
    for mode, words in _MODE_KEYWORDS.items():
        for w in words:
            if w in low:
                scores[mode] = scores.get(mode, 0) + len(w)
    if scores:
        return max(scores, key=scores.get)
    return "completion"


def otak(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Otak Dola — jawab pertanyaan via chat.dola.com (12 mode, auto-detect)."""
    p = parameters or {}
    action = str(p.get("action", "ask")).strip().lower()
    prompt = str(p.get("prompt", "")).strip()
    mode = str(p.get("mode", "")).strip().lower()

    try:
        # ---- ask: tanya jawab via Dola ----
        if action == "ask":
            if not prompt:
                return "Butuh 'prompt' (pertanyaan yang mau dijawab otak Dola)."

            # Auto-detect mode kalau tidak dispesifikasi / tidak valid
            if not mode or mode not in DOLA_MODES:
                mode = _detect_mode(prompt)

            try:
                from core.dola_client import DolaAPIError, DolaAuthError, dola_client
            except Exception as e:
                return (
                    f"Konektor Dola tidak tersedia: {e}\n"
                    "Pastikan core/dola_client.py dan core/dola_pool.py ada."
                )

            try:
                answer = dola_client.chat(prompt, mode=mode)
                return f"[Otak Dola · mode={mode}]\n{answer}"
            except DolaAuthError as e:
                return (
                    f"⚠️ {e}\n\n"
                    "💡 Jalankan: otak(action='setup') — login sekali via browser, "
                    "cookie akun otomatis disimpan ke pool."
                )
            except DolaAPIError as e:
                return f"❌ Dola error: {e}"

        # ---- setup: login sekali via browser ----
        if action == "setup":
            try:
                import importlib.util as _ilu
                dc_path = BASE_DIR / "skills" / "konten" / "dola_chat.py"
                if not dc_path.exists():
                    return f"Skill dola_chat tidak ditemukan: {dc_path}"
                dc_spec = _ilu.spec_from_file_location(
                    "_neira_dola_chat_setup", dc_path
                )
                dc_mod = _ilu.module_from_spec(dc_spec)
                dc_spec.loader.exec_module(dc_mod)
                return dc_mod.dola_chat({"action": "setup", "name": prompt or "neira"})
            except Exception as e:
                return (
                    f"Setup gagal: {e}\n"
                    "Alternatif: jalankan skill dola_chat(action='setup') langsung."
                )

        # ---- status: cek kesiapan otak ----
        if action == "status":
            try:
                from core.dola_pool import dola_pool
                accounts = dola_pool.list_accounts()
            except Exception:
                accounts = []

            template_exists = (BASE_DIR / "config" / "dola_payload.json").exists()

            lines = ["# STATUS OTAK DOLA"]
            lines.append(f"- Akun: {len(accounts)} terdaftar di pool")
            for acc in accounts:
                lines.append(
                    f"  · {acc.get('name', '?')} [{acc.get('status', '?')}] "
                    f"dipakai={acc.get('usage_count', 0)}x "
                    f"error={acc.get('error_count', 0)}"
                )
            if not accounts:
                lines.append("  ⚠️ Belum ada akun — jalankan otak(action='setup')")
            lines.append(
                f"- Template payload: "
                f"{'✅ ada' if template_exists else '❌ belum ada (jalankan setup)'}"
            )
            lines.append("- Mode default: completion")
            lines.append(
                f"- Mode tersedia: {len(DOLA_MODES)} mode "
                f"({', '.join(DOLA_MODES.keys())})"
            )
            return "\n".join(lines)

        # ---- modes: daftar mode ----
        if action == "modes":
            lines = ["# MODE DOLA (12 mode)"]
            for m, desc in DOLA_MODES.items():
                lines.append(f"- {m}: {desc}")
            return "\n".join(lines)

        return (
            f"Aksi tidak dikenal: '{action}'. "
            "Pilihan action: ask | setup | status | modes "
            "(param: prompt, mode = completion/search/deep_search/write/"
            "translate/coding/music/image/read_web/academic/doc/edu)."
        )

    except Exception as e:
        return f"[Otak] Error: {e}"


TOOL: Dict[str, Any] = {
    "name": "otak",
    "description": (
        "Otak Dola — jawab pertanyaan via chat.dola.com (12 mode AI). "
        "Mode otomatis terdeteksi dari pertanyaan: search (cari web), "
        "write (tulis artikel), translate (terjemah), coding (kode), "
        "music (musik), image (gambar), deep_search (riset), "
        "completion (umum), dll. "
        "Actions: ask (tanya jawab), setup (login sekali), "
        "status (cek kesiapan), modes (daftar mode)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "ask = tanya jawab; setup = login sekali via browser; "
                    "status = kesiapan otak; modes = daftar mode."
                ),
                "enum": ["ask", "setup", "status", "modes"],
            },
            "prompt": {
                "type": "STRING",
                "description": "Pertanyaan / tugas (wajib utk action=ask).",
            },
            "mode": {
                "type": "STRING",
                "description": (
                    "Mode Dola (opsional — otomatis terdeteksi dari pertanyaan)."
                ),
                "enum": list(DOLA_MODES.keys()),
            },
        },
        "required": ["action"],
    },
    "handler": otak,
    "behavior": "NON_BLOCKING",
}

run = otak
