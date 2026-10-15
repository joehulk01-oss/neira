"""
Gemini Connector for JARVIS Hybrid Brain Router.
Handles light chat, complexity scoring, and natural language formatting.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _base_dir()

def _load_env_dict(env_path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not env_path.exists():
        return out
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        out[k.strip()] = v.strip()
    return out


class GeminiConnector:
    """Connector for Gemini fast sensory brain."""

    def __init__(self, config_path: Path | str | None = None):
        self.config_path = Path(config_path) if config_path else BASE_DIR / "shared" / "config.env"
        self.env = _load_env_dict(self.config_path)
        self.api_key = self.env.get("GEMINI_API_KEY", "")
        self.router_url = self.env.get("VANSROUTER_URL", "http://127.0.0.1:20128").rstrip("/")

    def chat(self, user_input: str, system_prompt: Optional[str] = None) -> str:
        """Light conversation with Gemini."""
        prompt = system_prompt or "Kamu adalah JARVIS, asisten pintar ramah, ringkas, dan cerdas."
        
        # Priority 1: Use local VansRouter if available
        try:
            import requests
            endpoint = f"{self.router_url}/v1/chat/completions"
            active_model = os.environ.get("VANSROUTER_MODEL", self.env.get("VANSROUTER_MODEL", "ag/gemini-3.8-flash-medium"))
            payload = {
                "model": active_model,
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": user_input}
                ],
                "temperature": 0.7,
                "max_tokens": 300,
                "stream": False
            }
            res = requests.post(endpoint, json=payload, timeout=15)
            if res.status_code == 200:
                data = res.json()
                content = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                if content:
                    return content
        except Exception:
            pass

        # Priority 2: Fallback to core.gemini module
        try:
            from core import gemini
            resp = gemini.call(f"{prompt}\n\nUser: {user_input}", tier=gemini.FAST, timeout_ms=15000)
            if resp and hasattr(resp, "text") and resp.text:
                return resp.text.strip()
        except Exception as e:
            pass

        return f"Maaf, saya tidak dapat terhubung ke server saat ini."

    def rate_complexity(self, user_input: str) -> int:
        """
        Rate the complexity of the user's prompt on a scale of 1 to 10.
        Returns an integer 1-10 (default 1 for simple conversation).
        """
        system_instruction = (
            "You are a task complexity classifier for JARVIS AI. "
            "Rate the complexity of the following user request on an integer scale of 1 to 10:\n"
            "- 1-3: Casual chat, greetings, simple questions, basic facts, time, weather.\n"
            "- 4-5: Moderate search, simple file lookup, basic explanations.\n"
            "- 6-10: Complex reasoning, writing or debugging code, architecture, deep data analysis, complex calculations, self-learning.\n"
            "Return ONLY the single integer (e.g. '3' or '8') and nothing else."
        )

        try:
            import requests
            endpoint = f"{self.router_url}/v1/chat/completions"
            active_model = os.environ.get("VANSROUTER_MODEL", self.env.get("VANSROUTER_MODEL", "ag/gemini-3.8-flash-medium"))
            payload = {
                "model": active_model,
                "messages": [
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": user_input}
                ],
                "temperature": 0.0,
                "max_tokens": 5,
                "stream": False
            }
            res = requests.post(endpoint, json=payload, timeout=8)
            if res.status_code == 200:
                text = res.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
                for char in text:
                    if char.isdigit():
                        val = int(char)
                        if val == 1 and "10" in text:
                            return 10
                        return max(1, min(10, val))
        except Exception:
            pass

        # Heuristic fallback if offline/no response
        words = len(user_input.split())
        return 7 if words > 25 else 2

    def speak_nicely(self, text: str) -> str:
        """Format and polish heavy technical text from Hermes into spoken assistant summary."""
        if len(text) <= 150:
            return text
        try:
            return self.chat(
                f"Rangkum teks analitis berikut menjadi 2 kalimat singkat yang enak didengar dan jelas untuk dibacakan:\n\n{text}",
                system_prompt="Kamu adalah JARVIS. Buat ringkasan yang jelas, ringkas, dan santun."
            )
        except Exception:
            return text
