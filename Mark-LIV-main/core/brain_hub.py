"""
5-BRAIN HUB — dispatcher lima otak AI gratis dalam satu wadah.

Proyek "5 otak" (masing-masing punya keunggulan, semuanya gratis):
  1. HERMES   — inti otak utama (deep reasoning, kode, planning, eksekusi berat).
  2. DOLA     — dola.com (multi-mode: search/write/translate/coding/music/image).
  3. DUCK     — DuckDuckGo AI Chat (anonim, tanpa login, cepat utk tanya ringan).
  4. DEEPSEEK — DeepSeek (matematika, logika, coding, penalaran panjang).
  5. QWEN     — Qwen (multibahasa, dokumen, konten panjang, riset).

Prinsip:
  - Tiap otak = satu "Brain" dengan `strengths` (tag keunggulan) + `ask()` + `status()`.
  - `route()` memilih otak terbaik dari tag tugas; `ask_best()` mencoba berantai
    (fallback) sampai ada yang menjawab — 5 otak bergerak, satu tugas tetap selesai.
  - Otak yang belum dikonfigurasi tetap terdaftar (status jelas), tinggal diisi
    konektornya nanti tanpa mengubah pemanggil.

Dipakai oleh skill `brain_hub` (skills/dev/brain_hub.py) dan bisa dipanggil
langsung: `from core.brain_hub import brain_hub`.
"""
from __future__ import annotations

import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


class BrainError(Exception):
    """Otak gagal menjawab — dispatcher lanjut ke otak berikutnya."""


class BrainNotReady(BrainError):
    """Otak belum dikonfigurasi / konektor belum terpasang."""


# Cooldown rate-limit per otak — adopsi pola Brahma-Echo (or_client._rate_limited):
# otak yang baru gagal diistirahatkan sebentar supaya rantai fallback langsung
# pindah ke otak lain, bukan menabrak otak yang sama berulang kali.
RATE_LIMIT_COOLDOWN = 60.0  # detik


@dataclass
class Brain:
    """Satu otak AI: metadata keunggulan + dua fungsi operasional."""
    key: str
    label: str
    strengths: List[str] = field(default_factory=list)
    summary: str = ""
    ask_fn: Optional[Callable[[str], str]] = None
    status_fn: Optional[Callable[[], str]] = None
    ready: bool = True

    def ask(self, prompt: str) -> str:
        if not self.ask_fn:
            raise BrainNotReady(f"Otak '{self.key}' belum punya konektor.")
        return self.ask_fn(prompt)

    def status(self) -> str:
        if self.status_fn:
            try:
                return self.status_fn()
            except Exception as e:
                return f"error: {e}"
        return "siap" if self.ready else "belum dikonfigurasi"


# --------------------------------------------------------------------------- #
# Konektor otak — masing-masing mengembalikan teks jawaban atau raise BrainError
# --------------------------------------------------------------------------- #
def _hermes_ask(prompt: str) -> str:
    """Otak 1 — inti otak utama (deep core)."""
    try:
        from router.hermes_connector import process_heavy_task
    except Exception as e:
        raise BrainNotReady(f"Konektor Hermes tidak tersedia: {e}")
    result = process_heavy_task(prompt)
    text = result if isinstance(result, str) else str(result or "")
    if not text.strip():
        raise BrainError("Hermes mengembalikan jawaban kosong.")
    return text


def _hermes_status() -> str:
    try:
        from router.hermes_connector import HermesConnector  # noqa: F401
        return "siap (inti otak utama)"
    except Exception as e:
        return f"belum siap: {e}"


def _dola_ask(prompt: str) -> str:
    """Otak 2 — Dola (dola.com), rotasi akun via core/dola_pool.py.

    Mode percakapan otomatis terdeteksi dari isi pertanyaan
    (search/write/translate/coding/music/image/deep_search/completion).
    """
    try:
        from core.dola_client import DolaAPIError, DolaAuthError, dola_client
    except Exception as e:
        raise BrainNotReady(f"Konektor Dola tidak tersedia: {e}")

    # Deteksi mode dari pertanyaan (12 mode Dola)
    mode = _detect_dola_mode(prompt)
    try:
        return dola_client.chat(prompt, mode=mode)
    except (DolaAuthError, DolaAPIError) as e:
        raise BrainError(f"Dola: {e}")


def _detect_dola_mode(prompt: str) -> str:
    """Deteksi mode Dola dari isi pertanyaan (default: completion)."""
    low = (prompt or "").lower()
    mode_kw = {
        "search": ["cari", "search", "siapa", "apa itu", "kapan", "dimana", "terbaru", "berita", "harga", "price"],
        "write": ["tulis", "write", "artikel", "caption", "naskah", "essay", "puisi", "cerita", "story", "copywriting", "draft"],
        "translate": ["terjemah", "translate", "alih bahasa", "ke inggris", "ke indonesia"],
        "coding": ["kode", "code", "script", "fungsi", "function", "bug", "error", "python", "javascript", "program", "debug"],
        "music": ["musik", "music", "lagu", "song", "lirik", "chord", "playlist"],
        "image": ["gambar", "image", "foto", "picture", "ilustrasi", "desain grafis", "poster"],
        "deep_search": ["riset", "research", "studi mendalam", "analisis mendalam", "deep search"],
    }
    scores: Dict[str, int] = {}
    for mode, words in mode_kw.items():
        for w in words:
            if w in low:
                scores[mode] = scores.get(mode, 0) + len(w)
    if scores:
        return max(scores, key=scores.get)
    return "completion"


def _dola_status() -> str:
    try:
        from core.dola_client import dola_client
        return dola_client.account_summary()
    except Exception as e:
        return f"belum siap: {e}"


def _duck_ask(prompt: str) -> str:
    """Otak 3 — DuckDuckGo AI Chat (anonim, tanpa login)."""
    try:
        from skills.konten.duck_chat import duck_ask  # konektor diisi belakangan
    except Exception as e:
        raise BrainNotReady(
            "Otak Duck belum terpasang konektornya (skills/konten/duck_chat.py). "
            f"Detail: {e}"
        )
    return duck_ask(prompt)


def _deepseek_ask(prompt: str) -> str:
    """Otak 4 — DeepSeek (matematika, logika, coding)."""
    try:
        from skills.konten.deepseek_chat import deepseek_ask
    except Exception as e:
        raise BrainNotReady(
            "Otak DeepSeek belum terpasang konektornya (skills/konten/deepseek_chat.py). "
            f"Detail: {e}"
        )
    return deepseek_ask(prompt)


def _qwen_ask(prompt: str) -> str:
    """Otak 5 — Qwen (multibahasa, dokumen, konten panjang)."""
    try:
        from skills.konten.qwen_chat import qwen_ask
    except Exception as e:
        raise BrainNotReady(
            "Otak Qwen belum terpasang konektornya (skills/konten/qwen_chat.py). "
            f"Detail: {e}"
        )
    return qwen_ask(prompt)


# --------------------------------------------------------------------------- #
# Peta rute: tag tugas → kunci otak terbaik (urut = prioritas)
# --------------------------------------------------------------------------- #
ROUTE_MAP: Dict[str, List[str]] = {
    "reasoning": ["hermes", "deepseek", "dola", "qwen", "duck"],
    "code": ["deepseek", "hermes", "dola", "qwen", "duck"],
    "math": ["deepseek", "hermes", "qwen", "dola", "duck"],
    "logic": ["deepseek", "hermes", "qwen", "dola", "duck"],
    "plan": ["hermes", "deepseek", "qwen", "dola", "duck"],
    "heavy": ["hermes", "deepseek", "qwen", "dola", "duck"],
    "search": ["dola", "duck", "qwen", "hermes", "deepseek"],
    "web": ["dola", "duck", "qwen", "hermes", "deepseek"],
    "news": ["dola", "duck", "qwen", "hermes", "deepseek"],
    "write": ["qwen", "dola", "hermes", "deepseek", "duck"],
    "content": ["qwen", "dola", "hermes", "deepseek", "duck"],
    "translate": ["dola", "qwen", "deepseek", "hermes", "duck"],
    "doc": ["qwen", "deepseek", "hermes", "dola", "duck"],
    "long": ["qwen", "deepseek", "hermes", "dola", "duck"],
    "multilang": ["qwen", "dola", "deepseek", "hermes", "duck"],
    "chat": ["duck", "dola", "qwen", "hermes", "deepseek"],
    "quick": ["duck", "dola", "qwen", "hermes", "deepseek"],
    "music": ["dola", "qwen", "duck", "hermes", "deepseek"],
    "image": ["dola", "qwen", "duck", "hermes", "deepseek"],
}

# Kata kunci → tag (deteksi jenis tugas dari teks pertanyaan)
_KEYWORDS: Dict[str, List[str]] = {
    "reasoning": ["kenapa", "jelaskan", "analisis", "analisa", "fikir", "pikir", "reason", "why", "explain", "evaluate", "bandingkan", "compare"],
    "code": ["kode", "code", "script", "fungsi", "function", "bug", "error", "python", "javascript", "program", "compile", "refactor", "debug"],
    "math": ["hitung", "calculate", "rumus", "matematika", "integral", "turunan", "persamaan", "aljabar", "statistik", "probabilitas", "=", "∑"],
    "logic": ["logika", "logic", "puzzle", "teka-teki", "silogisme", "bukti", "proof", "asumsi"],
    "plan": ["rencana", "plan", "strategi", "roadmap", "langkah", "step", "jadwal", "timeline", "proposal"],
    "heavy": ["berat", "kompleks", "kompleksitas", "deep", "mendalam", "riset", "research", "studi"],
    "search": ["cari", "search", "siapa", "apa itu", "what is", "kapan", "when", "dimana", "where", "terbaru", "berita", "news", "harga", "price"],
    "web": ["situs", "website", "url", "online", "internet", "web"],
    "write": ["tulis", "write", "buat artikel", "artikel", "artikel", "caption", "naskah", "essay", "puisi", "cerita", "story", "copywriting", "draft"],
    "content": ["konten", "content", "caption", "deskripsi", "ringkas", "summary", "rangkum", "summary"],
    "translate": ["terjemah", "translate", "alih bahasa", "dalam bahasa inggris", "dalam bahasa indonesia", "ke inggris", "ke indonesia"],
    "doc": ["dokumen", "document", "pdf", "laporan", "report", "kontrak", "proposal"],
    "long": ["panjang", "detail", "lengkap", "komprehensif", "comprehensive", "mendetail"],
    "multilang": ["bahasa jepang", "bahasa korea", "bahasa arab", "bahasa mandarin", "bahasa prancis", "japanese", "korean", "arabic", "chinese"],
    "music": ["musik", "music", "lagu", "song", "lirik", "chord", "playlist"],
    "image": ["gambar", "image", "foto", "picture", "ilustrasi", "desain grafis", "poster"],
    "chat": ["halo", "hai", "hi", "hello", "assalam", "apa kabar", "ngobrol", "chat"],
    "quick": ["cepat", "quick", "singkat", "brief", "sekilas"],
}

_DEFAULT_CHAIN = ["hermes", "dola", "deepseek", "qwen", "duck"]


class BrainHub:
    """Registri + dispatcher 5 otak."""

    def __init__(self) -> None:
        self._brains: Dict[str, Brain] = {}
        self._rate_limited: Dict[str, float] = {}
        self._register_defaults()

    # ---- registri --------------------------------------------------------- #
    def _register_defaults(self) -> None:
        self.register(Brain(
            key="hermes", label="Hermes · inti otak utama",
            strengths=["reasoning", "code", "plan", "heavy", "logic"],
            summary="Otak 1 — deep reasoning, kode, planning, eksekusi berat.",
            ask_fn=_hermes_ask, status_fn=_hermes_status,
        ))
        self.register(Brain(
            key="dola", label="Dola · multi-mode",
            strengths=["search", "web", "write", "translate", "music", "image", "content"],
            summary="Otak 2 — dola.com: search/write/translate/coding/music/image.",
            ask_fn=_dola_ask, status_fn=_dola_status,
        ))
        self.register(Brain(
            key="duck", label="Duck · anonim cepat",
            strengths=["chat", "quick", "search", "web"],
            summary="Otak 3 — DuckDuckGo AI Chat: anonim, tanpa login, tanya ringan.",
            ask_fn=_duck_ask,
        ))
        self.register(Brain(
            key="deepseek", label="DeepSeek · logika & kode",
            strengths=["math", "logic", "code", "reasoning", "doc"],
            summary="Otak 4 — DeepSeek: matematika, logika, coding, penalaran panjang.",
            ask_fn=_deepseek_ask,
        ))
        self.register(Brain(
            key="qwen", label="Qwen · konten & multibahasa",
            strengths=["write", "content", "multilang", "doc", "long", "translate"],
            summary="Otak 5 — Qwen: multibahasa, dokumen, konten panjang, riset.",
            ask_fn=_qwen_ask,
        ))

    def register(self, brain: Brain) -> None:
        self._brains[brain.key] = brain

    def get(self, key: str) -> Optional[Brain]:
        return self._brains.get(key)

    def list_brains(self) -> List[Brain]:
        return list(self._brains.values())

    # ---- cooldown rate-limit ---------------------------------------------- #
    def is_rate_limited(self, key: str) -> bool:
        """True kalau otak sedang di-cooldown (baru gagal / kena limit)."""
        ts = self._rate_limited.get(key)
        if ts is None:
            return False
        if time.time() - ts > RATE_LIMIT_COOLDOWN:
            del self._rate_limited[key]
            return False
        return True

    def mark_rate_limited(self, key: str, cooldown: float = RATE_LIMIT_COOLDOWN) -> None:
        """Tandai otak sedang limit — dilewati rantai fallback sampai cooldown habis."""
        self._rate_limited[key] = time.time()
        print(f"[BrainHub] ⏸️ otak '{key}' di-cooldown {cooldown:.0f}s")

    def clear_rate_limited(self, key: str) -> None:
        self._rate_limited.pop(key, None)

    # ---- deteksi & rute --------------------------------------------------- #
    def detect_tags(self, text: str) -> List[str]:
        """Deteksi tag tugas dari teks pertanyaan (urut = paling cocok dulu)."""
        low = (text or "").lower()
        scores: Dict[str, int] = {}
        for tag, words in _KEYWORDS.items():
            for w in words:
                if w in low:
                    scores[tag] = scores.get(tag, 0) + len(w)
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        return [tag for tag, _ in ranked]

    def route(self, text: str) -> List[str]:
        """Urutan kunci otak terbaik untuk teks tugas (untuk fallback berantai)."""
        tags = self.detect_tags(text)
        chain: List[str] = []
        for tag in tags:
            for key in ROUTE_MAP.get(tag, []):
                if key not in chain:
                    chain.append(key)
        for key in _DEFAULT_CHAIN:
            if key not in chain:
                chain.append(key)
        return chain

    # ---- eksekusi --------------------------------------------------------- #
    def ask(self, brain_key: str, prompt: str) -> str:
        brain = self._brains.get(brain_key)
        if not brain:
            raise BrainError(
                f"Otak '{brain_key}' tidak dikenal. Pilihan: {', '.join(self._brains)}."
            )
        return brain.ask(prompt)

    def ask_best(self, prompt: str, force: bool = False) -> Dict[str, Any]:
        """Kirim ke otak terbaik; kalau gagal, lanjut ke otak berikutnya (fallback).

        Otak yang sedang cooldown dilewati (kecuali SELURUH rantai sedang cooldown
        — anti lockout total, tetap dicoba). `force=True` mengabaikan cooldown.
        """
        chain = self.route(prompt)
        attempts: List[str] = []
        all_cooling = all(
            self.is_rate_limited(k) for k in chain if self._brains.get(k)
        )
        for key in chain:
            brain = self._brains.get(key)
            if not brain:
                continue
            if not force and self.is_rate_limited(key) and not all_cooling:
                attempts.append(f"{key}: dilewati (cooldown)")
                continue
            try:
                text = brain.ask(prompt)
                self.clear_rate_limited(key)
                return {
                    "answer": text,
                    "brain": key,
                    "label": brain.label,
                    "attempts": attempts + [f"{key}: ok"],
                }
            except BrainNotReady as e:
                # belum terpasang ≠ kena limit: jangan di-cooldown
                attempts.append(f"{key}: {e}")
            except Exception as e:
                self.mark_rate_limited(key)
                attempts.append(f"{key}: {e}")
        return {
            "answer": "",
            "brain": "",
            "label": "",
            "attempts": attempts,
            "error": "Semua otak gagal / belum siap.",
        }

    def status_report(self) -> str:
        lines = ["# STATUS 5 OTAK"]
        for brain in self._brains.values():
            lines.append(
                f"- {brain.label} [{brain.key}] — keunggulan: {', '.join(brain.strengths)}"
            )
            status = brain.status()
            if self.is_rate_limited(brain.key):
                status += f" (cooldown {RATE_LIMIT_COOLDOWN:.0f}s)"
            lines.append(f"    status: {status}")
        return "\n".join(lines)


# Global instance
brain_hub = BrainHub()
