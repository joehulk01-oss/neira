"""
Jev Ultrafast Browser Agent Skill for Neira & Hermes.

Autonomous browser automation: give ONE natural-language goal plus a starting
URL, and the agent decides every click / type / select by itself until the goal
is satisfied. Backed by the `jev-ultrafast` library
(https://github.com/browser-use/jev-ultrafast) which uses TypeSafe for the
operation+target decision and a small OpenAI-compatible model only for the text
of fields that need typing.

Requires (set in shared/config.env):
    TYPESAFE_API_KEY      — TypeSafe key (decides operation + target)
    TEXT_MODEL_API_KEY    — OpenAI-compatible key (writes field text)
    TEXT_MODEL_BASE_URL   — optional, defaults to OpenRouter
    TEXT_MODEL            — optional, defaults to inception/mercury-2.5

Auto-discovered by core/action_loader.py (skills/**/*.py) and core/skill_hub.py.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Any, Dict

_MAX_DEFAULT_STEPS = 25


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = _base_dir()
CONFIG_ENV = BASE_DIR / "shared" / "config.env"
WORKSPACE_DIR = BASE_DIR / "workspace" / "browser_traces"


def _load_env() -> None:
    """Pull TYPESAFE_* / TEXT_MODEL_* from shared/config.env into the process env."""
    if not CONFIG_ENV.exists():
        return
    try:
        for line in CONFIG_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, value = s.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())
    except Exception:
        pass


def _log(player: Any, text: str) -> None:
    short = str(text)[:200]
    print(f"[BrowserAgent] {short}")
    if player is not None:
        try:
            player.write_log(f"[browser_agent] {short[:120]}")
        except Exception:
            pass


def _missing_keys() -> list[str]:
    need = []
    if not os.environ.get("TYPESAFE_API_KEY"):
        need.append("TYPESAFE_API_KEY")
    if not os.environ.get("TEXT_MODEL_API_KEY"):
        need.append("TEXT_MODEL_API_KEY")
    return need


def browser_agent(parameters: Dict[str, Any] = None, player: Any = None, **kwargs) -> str:
    """
    Runs an autonomous browser session toward a goal.

    parameters:
        goal       (str, required) — the full goal in natural language
        url        (str, required) — the page to start from
        max_steps  (int, optional) — hard cap on executed actions (default 25)
        keep_open  (bool, optional) — leave the automation tab open when finished
    """
    parameters = parameters or {}
    goal = str(parameters.get("goal") or "").strip()
    url = str(parameters.get("url") or "").strip()
    try:
        max_steps = int(parameters.get("max_steps") or _MAX_DEFAULT_STEPS)
    except (TypeError, ValueError):
        max_steps = _MAX_DEFAULT_STEPS
    keep_open = bool(parameters.get("keep_open"))

    if not goal:
        return "Mohon berikan 'goal' (tujuan) untuk agen browser."
    if not url:
        return "Mohon berikan 'url' halaman awal untuk agen browser."
    if "://" not in url:
        url = "https://" + url

    _load_env()

    try:
        from jev_ultrafast import Agent
        from jev_ultrafast.browser import StalePage
    except ImportError:
        return (
            "Modul 'jev-ultrafast' belum terpasang di environment ini.\n"
            "Jalankan: .venv\\Scripts\\python.exe -m pip install vendor\\jev-ultrafast"
        )

    missing = _missing_keys()
    if missing:
        return (
            "Kunci API untuk agen browser belum lengkap: " + ", ".join(missing) + "\n"
            "Tambahkan ke shared/config.env lalu coba lagi."
        )

    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    _log(player, f"Mulai sesi browser: {url}")
    _log(player, f"Goal: {goal}")

    agent = None
    try:
        agent = Agent(url, goal)
    except Exception as exc:
        return f"Gagal membuka sesi browser: {exc}"

    steps: list[str] = []
    status = "unknown"
    try:
        while agent.state["status"] not in {"done", "blocked"}:
            if len(agent.state["history"]) >= max_steps:
                status = "budget_exhausted"
                _log(player, f"Batas {max_steps} aksi tercapai, berhenti.")
                break
            try:
                state = agent.command("tick")
            except StalePage:
                time.sleep(0.2)
                continue
            status = state.get("status", "ready")
            history = state.get("history") or []
            if history:
                last = history[-1]
                line = (
                    f"[{last.get('step')}] {last.get('operation')} -> {last.get('action')}"
                    f" (target={last.get('target')}"
                    + (f", text='{last.get('text')}'" if last.get("text") else "")
                    + ")"
                )
                if line not in steps:
                    steps.append(line)
                    _log(player, line)

        final_status = agent.state.get("status", status)
        final_url = (agent.state.get("page") or {}).get("url", url)
        elapsed = round(time.perf_counter() - started, 2)

        trace_dir = WORKSPACE_DIR / f"run_{int(time.time())}"
        try:
            trace_dir.mkdir(parents=True, exist_ok=True)
            (trace_dir / "actions.log").write_text("\n".join(steps), encoding="utf-8")
        except Exception:
            trace_dir = None

        label = {
            "done": "selesai mencapai tujuan",
            "blocked": "berhenti (tidak ada aksi yang bisa memajukan)",
            "budget_exhausted": f"berhenti karena batas {max_steps} aksi",
        }.get(final_status, f"berakhir dengan status '{final_status}'")

        out = [
            f"Agen browser {label} dalam {elapsed} detik.",
            f"Aksi dieksekusi: {len(agent.state.get('history') or [])}",
            f"URL akhir: {final_url}",
        ]
        if steps:
            out.append("Jejak aksi:")
            out.extend(f"  {s}" for s in steps[-12:])
        else:
            out.append("Tidak ada aksi yang dijalankan.")
        if trace_dir:
            out.append(f"Log tersimpan di: {trace_dir}")
        return "\n".join(out)
    except Exception as exc:
        return f"Kesalahan saat menjalankan agen browser: {exc}"
    finally:
        if agent is not None and not keep_open:
            try:
                agent.close()
            except Exception:
                pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "browser_agent",
    "description": (
        "Autonomous browser agent: give it one goal and a starting URL and it drives the "
        "browser by itself (click, type, select, scroll, wait) until the goal is reached. "
        "Use this for multi-step web tasks instead of step-by-step browser_control, e.g. "
        "'cari tiket pesawat Zurich ke London', 'isi formulir pendaftaran ini', "
        "'filter hasil pencarian hotel ini'. Requires TYPESAFE_API_KEY and TEXT_MODEL_API_KEY."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "goal": {
                "type": "STRING",
                "description": "The complete goal in natural language, including every detail needed (cities, dates, filters, values to type).",
            },
            "url": {
                "type": "STRING",
                "description": "The page to start from (e.g. 'https://www.google.com/travel/flights?hl=en').",
            },
            "max_steps": {
                "type": "INTEGER",
                "description": "Optional hard cap on executed browser actions (default 25).",
            },
            "keep_open": {
                "type": "BOOLEAN",
                "description": "Optional: leave the automation tab open after finishing (default false).",
            },
        },
        "required": ["goal", "url"],
    },
    "handler": browser_agent,
}