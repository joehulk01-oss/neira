"""
Brain Router for JARVIS HYBRID AI.
Decides dynamically whether a query should be handled by:
- GEMINI (Fast conversation, casual questions, quick lookups)
- HERMES (Heavy tasks, coding, architecture, deep data analysis, self-learning)
- DOLA   (Search, web, write, translate, music, image — via chat.dola.com)
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Optional, Tuple

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
    return Path(__file__).resolve().parent.parent

BASE_DIR = _base_dir()

# Add router directory to sys.path for direct imports
sys.path.insert(0, str(BASE_DIR / "router"))

from gemini_connector import GeminiConnector
from hermes_connector import HermesConnector


# Heavy task keywords defined in JARVIS-HYBRID-PLAN.md
HEAVY_KEYWORDS = (
    "analisa", "analisis", "buatkan", "rancang", "kode", "program",
    "data", "laporan", "ingat", "pelajari", "pola", "strategi",
    "perhitungan", "algoritma", "debug", "arsitektur", "refactor",
    "optimasi", "script", "database", "sql"
)

# Dola brain keywords — search, web, write, translate, music, image
DOLA_KEYWORDS = (
    "cari", "search", "terjemah", "translate", "tulis", "write",
    "artikel", "caption", "musik", "lagu", "lirik", "gambar", "image",
    "foto", "ilustrasi", "berita", "news", "harga", "price",
    "apa itu", "what is", "siapa", "kapan", "dimana", "website",
    "situs", "online", "internet", "puisi", "cerita", "essay",
    "riset", "research", "ringkas", "summary", "rangkum",
)


class BrainRouter:
    """Intelligent Brain Router connecting Gemini and Hermes."""

    def __init__(self, config_path: Path | str | None = None):
        self.config_path = Path(config_path) if config_path else BASE_DIR / "shared" / "config.env"
        self.gemini = GeminiConnector(self.config_path)
        self.hermes = HermesConnector(self.config_path)
        
        # Load threshold
        self.threshold = 5
        try:
            if self.config_path.exists():
                for line in self.config_path.read_text(encoding="utf-8").splitlines():
                    if line.startswith("ROUTER_THRESHOLD="):
                        self.threshold = int(line.split("=", 1)[1].strip())
        except Exception:
            pass

    def decide_brain(self, user_input: str) -> Tuple[str, str]:
        """
        Determines whether to route to 'HERMES', 'DOLA', or 'GEMINI'.
        Returns (brain_name, reason).
        """
        text_lower = user_input.lower().strip()
        words = re.findall(r"\b\w+\b", text_lower)

        # Rule 1: Check heavy keywords → Hermes
        matched_heavy = [kw for kw in HEAVY_KEYWORDS if kw in text_lower]
        if matched_heavy:
            return "HERMES", f"Kata kunci tugas berat terdeteksi: {', '.join(matched_heavy[:3])}"

        # Rule 2: Check Dola keywords → Dola (search/write/translate/music/image)
        matched_dola = [kw for kw in DOLA_KEYWORDS if kw in text_lower]
        if matched_dola:
            return "DOLA", f"Kata kunci Dola terdeteksi: {', '.join(matched_dola[:3])}"

        # Rule 3: Check text length (> 20 words) → Hermes
        if len(words) > 20:
            return "HERMES", f"Panjang teks > 20 kata ({len(words)} kata)"

        # Rule 4: Complexity score via Gemini
        score = self.gemini.rate_complexity(user_input)
        if score > self.threshold:
            return "HERMES", f"Skor kompleksitas tinggi ({score} > {self.threshold})"

        # Rule 5: Otherwise, Gemini
        return "GEMINI", f"Percakapan ringan / umum (skor: {score})"

    def route_response(self, user_input: str, context: Optional[str] = None) -> str:
        """
        Route input to the appropriate brain and return the final answer.
        Includes automatic fallback: Dola → Hermes → Gemini.
        """
        user_input_clean = user_input.strip()
        if not user_input_clean:
            return "Halo, ada yang bisa saya bantu?"

        target_brain, reason = self.decide_brain(user_input_clean)
        print(f"\n[BrainRouter] [TARGET] Brain: {target_brain} ({reason})")

        if target_brain == "DOLA":
            try:
                print(f"[BrainRouter] [DOLA] Processing with Dola (chat.dola.com)...")
                result = self._ask_dola(user_input_clean)
                if result and result.strip():
                    return result
            except Exception as e:
                print(f"[BrainRouter] [WARN] Dola encountered an error ({e}). Falling back to Hermes...")

        if target_brain in ("HERMES", "DOLA"):
            try:
                print(f"[BrainRouter] [HERMES] Processing with Hermes Agent...")
                result = self.hermes.process_heavy_task(user_input_clean, context=context)
                if result and result.strip():
                    # The connector appends "[Status Eksekusi di Laptop]" with the
                    # REAL per-action outcome — surface failures in the log too.
                    if "[Status Eksekusi di Laptop]" in result:
                        if "❌" in result:
                            print("[BrainRouter] [HERMES] ⚠️ Some actions FAILED — honest status included in the reply.")
                        else:
                            print("[BrainRouter] [HERMES] ✅ All actions verified successful.")
                    return result
            except Exception as e:
                print(f"[BrainRouter] [WARN] Hermes encountered an error ({e}). Falling back to Gemini...")
                fallback_reply = self.gemini.chat(
                    f"Pengguna bertanya: '{user_input_clean}'. Berikan jawaban ringkas dan bantu semampunya."
                )
                return f"Saya coba jawab dengan cara yang lebih sederhana ya:\n\n{fallback_reply}"

        # Default / Gemini
        print(f"[BrainRouter] [GEMINI] Processing with Gemini...")
        return self.gemini.chat(user_input_clean)

    @staticmethod
    def _ask_dola(prompt: str) -> str:
        """Kirim pertanyaan ke otak Dola (chat.dola.com) via core/dola_client.py."""
        try:
            from core.dola_client import dola_client
        except Exception as e:
            raise RuntimeError(f"Konektor Dola tidak tersedia: {e}") from e
        return dola_client.chat(prompt)
