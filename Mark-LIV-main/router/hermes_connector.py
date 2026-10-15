"""
Hermes Agent Connector for JARVIS Hybrid Brain Router.
Handles heavy tasks, in-depth analysis, self-learning, and skill retrieval.
Uses VansRouter (http://127.0.0.1:20128) or direct OpenRouter/Hermes endpoint.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
import requests

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


class HermesConnector:
    """Connector for Hermes Agent / Heavy Reasoning Core."""

    def __init__(self, config_path: Path | str | None = None):
        self.config_path = Path(config_path) if config_path else BASE_DIR / "shared" / "config.env"
        self.skills_dir = BASE_DIR / "hermes-agent" / "data" / "skills"
        self.memories_dir = BASE_DIR / "hermes-agent" / "data" / "memories"
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self.memories_dir.mkdir(parents=True, exist_ok=True)

    def process_heavy_task(self, user_input: str, context: Optional[str] = None, execute_actions: bool = True) -> str:
        """
        Process complex analysis, coding, logic, or self-learning tasks.
        Can execute physical OS actions (launching CMD, coding tools, etc.) if requested.
        """
        # Fetch dynamic catalog of shared skills
        skill_catalog = ""
        try:
            from core.skill_hub import skill_hub
            skill_catalog = skill_hub.get_hermes_catalog()
        except Exception:
            pass

        # Persistent TASK HISTORY — a glimpse of tasks already executed
        # successfully on this machine, so past wins are reused, not
        # rediscovered. (Previously the core had zero memory of past runs.)
        task_history_block = ""
        try:
            from memory.memory_manager import recent_tasks_for_prompt
            task_history_block = recent_tasks_for_prompt()
            if task_history_block:
                task_history_block += "\n\n"
        except Exception:
            pass

        # Explicit STORAGE MAP — the core used to have no idea which folder
        # holds skills vs memories and would guess paths when the user asked.
        folder_map = (
            "=== STORAGE MAP (exact folders on this laptop — never guess paths) ===\n"
            "- Skills created via 'register_skill' are saved as Python files in:\n"
            f"  {BASE_DIR / 'skills' / '<category>' / '<name>'}.py "
            "(category ∈ konten/admin/dev/asisten/custom) — they hot-reload and join the catalog above.\n"
            f"- User memory lives in: {BASE_DIR / 'memory' / 'long_term.json'} "
            "(managed by Neira's surface brain; do not write raw JSON there yourself).\n"
            f"- Task execution history lives in: {BASE_DIR / 'memory' / 'task_ledger.json'} (mirrored in TASK HISTORY).\n"
            f"- Free-form learning notes: {self.skills_dir} (JSON; prefer 'register_skill' for reusable skills).\n"
            "When asked where anything is stored, answer from this map.\n\n"
        )

        system_prompt = (
            "You are the deep reasoning & execution core (the inner brain) of Neira — one single desktop "
            "voice assistant. Neira's surface voice talks to the user; you work silently behind it. The "
            "user must never learn that a separate engine exists: never name yourself, never say "
            "'Hermes', and never write as if a second assistant did the work.\n\n"
            "=== MANDATORY PROTOCOL: SKILL AWARENESS & ROUTING ===\n"
            "You have direct access to the SHARED SKILLS LIBRARY listed below — the SAME "
            "library and the SAME category map that Neira sees. Old skills and newly "
            "registered skills are all listed here, grouped by category.\n"
            "BEFORE creating custom scripts or opening raw terminals, ALWAYS inspect the catalog:\n"
            "1. Route by CATEGORY first, then pick the skill by name:\n"
            "   - KONTEN = content creation & research (video, web/news search, Reddit, HN, images, weather, YouTube)\n"
            "   - ADMIN  = system, browser, device & app control (open apps, volume, wifi, brightness, browser automation)\n"
            "   - DEV    = code, files, automation, deep reasoning\n"
            "   - ASISTEN= personal assistant (reminders, messages, flights, proactive)\n"
            "   - CUSTOM / GENERAL / PLUGIN = everything else\n"
            "   When the user says 'butuh konten' or asks for content work, CALL A KONTEN SKILL. "
            "When they ask for system/admin work, CALL AN ADMIN SKILL. Never pick a skill "
            "from the wrong category when a matching one exists.\n"
            "2. If a skill already exists for the task (e.g. 'web_search' for searching web/news, "
            "'generate_video' for AI videos, 'youtube_video' for YouTube, 'computer_settings' for volume/wifi/brightness, "
            "'open_app' for launching applications), CALL THAT SKILL DIRECTLY in your actions list!\n"
            "3. Only use 'create_script' or 'open_cmd' when no existing skill can accomplish the task.\n"
            "4. SELF-IMPROVEMENT: when you discover a capability gap — e.g. the user asks for an app "
            "or action that no skill covers — use 'use_skill_creator' to CREATE a new skill immediately. "
            "Example: {\"action\": \"use_skill_creator\", \"cmd\": \"create\", \"name\": \"open_photoshop\", "
            "\"code\": \"...TOOL dict + handler...\", \"category\": \"admin\"}. "
            "The skill is written, validated (AST + compile), registered and hot-reloaded INSTANTLY.\n"
            "4b. APP DISCOVERY: use 'installed_apps' to find and open ANY installed app — not just the "
            "hardcoded list. Commands: list (all apps), search (find by name), launch (open from catalog), "
            "refresh (rescan). Example: {\"action\": \"installed_apps\", \"cmd\": \"search\", \"query\": \"Photoshop\"}\n"
            "5. If you invent a reusable new capability, save it using 'use_skill_creator' so Neira has it permanently.\n"
            "6. TERMINAL POLICY: 'run_cmd' executes SILENTLY in the background and you receive the real "
            "exit code + output. NEVER open a visible CMD/PowerShell window for automation — the user's "
            "desktop must not fill up with terminal windows. Only add \"visible\": true to a run_cmd/open_cmd "
            "action when the user EXPLICITLY asks to see a terminal window.\n"
            "7. VERIFICATION: after your action block runs you will receive the REAL execution results "
            "(✅ success / ❌ failure per action). Your final report may only claim successes that "
            "actually happened; every ❌ must be admitted openly with its cause. Never announce "
            "success for an action that failed.\n\n"
            f"{skill_catalog}\n\n"
            f"{task_history_block}"
            f"{folder_map}"
            "=== ACTION EXECUTION FORMAT ===\n"
            "When actions are required, output a ```hermes_action block with JSON:\n"
            "```hermes_action\n"
            "{\n"
            "  \"thought\": \"Mengapa aksi ini dipilih dan skill apa yang dipanggil\",\n"
            "  \"actions\": [\n"
            "    {\"action\": \"<skill_name>\", \"<param>\": \"<value>\"}\n"
            "  ],\n"
            "  \"report_for_mark\": \"Laporan ramah dalam Bahasa Indonesia ORANG PERTAMA (pakai 'saya') untuk disampaikan Neira ke pengguna — seolah Neira sendiri yang mengerjakan; jangan pernah menyebut nama internal atau asisten lain.\"\n"
            "}\n"
            "```\n"
            "Examples:\n"
            "- User wants news: {\"action\": \"web_search\", \"query\": \"berita teknologi hari ini\", \"mode\": \"news\"}\n"
            "- User wants AI video: {\"action\": \"generate_video\", \"prompt\": \"drone flying over mountains\"}\n"
            "- User wants app opened: {\"action\": \"open_app\", \"app_name\": \"spotify\"}\n"
            "- User wants to see all installed apps: {\"action\": \"installed_apps\", \"cmd\": \"list\"}\n"
            "- User wants to find/open an app not in the alias list: {\"action\": \"installed_apps\", \"cmd\": \"search\", \"query\": \"<name>\"}\n"
            "- User wants a new skill created: {\"action\": \"use_skill_creator\", \"cmd\": \"create\", \"name\": \"<skill_name>\", \"code\": \"<TOOL+handler>\"}\n"
            "- User wants to see available skills: {\"action\": \"manage_skills\"}  (action defaults to 'list')\n"
            "Always deliver complete, robust, self-correcting solutions."
        )

        # Blueprint Tahap 9 (anti prompt-injection): konten eksternal adalah
        # DATA TIDAK TERPERCAYA — dibungkus pembatas eksplisit, pola fatal
        # diblokir total sebelum menyentuh otak eksekusi.
        safety_rules = ""
        try:
            from core.injection_guard import SANITIZE_NOTE as safety_rules
        except Exception:
            safety_rules = ""
        if context:
            safe_ctx = context
            try:
                from core.injection_guard import embed as _ig_embed
                safe_ctx, _ig_rep = _ig_embed(context, source="context")
            except Exception:
                pass
            user_content = (f"{safety_rules}\n\nKONTEKS TERKAIT:\n{safe_ctx}"
                            f"\n\nINSTRUKSI TUGAS (dari user asli):\n{user_input}")
        else:
            user_content = user_input

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        try:
            result_content = self._llm_call(messages)

            # ── CLOSED LOOP: plan → run → feed REAL results back → honest report ──
            # The old flow executed the plan and returned the model's *guessed*
            # success story, so a failed action was still announced as done.
            # Now every action's real outcome is shown to the model, which gets
            # one repair round before writing a report that only claims what
            # actually happened.
            if execute_actions:
                result_content = self._execute_and_verify(messages, result_content)

            return result_content
        except Exception as e:
            raise RuntimeError(f"Hermes Agent error: {e}")

    # ── Closed-loop helpers: verification turns a guess into a report ────────
    _ACTION_RE = re.compile(r"```(?:hermes_action|json)?\s*(\{.*?\})\s*```", re.DOTALL)

    def _refresh_env(self) -> None:
        """Selalu muat konfigurasi dan model terbaru dari shared/config.env, env process, atau api_keys.json."""
        self.env = _load_env_dict(self.config_path)
        self.router_url = os.environ.get(
            "VANSROUTER_URL",
            self.env.get("VANSROUTER_URL", "http://127.0.0.1:20128")
        ).rstrip("/")

        # Ambil model paling update (runtime os.environ > config/api_keys.json > shared/config.env)
        active_model = os.environ.get("VANSROUTER_MODEL", "").strip()
        if not active_model:
            try:
                cfg_file = BASE_DIR / "config" / "api_keys.json"
                if cfg_file.exists():
                    cfg_data = json.loads(cfg_file.read_text(encoding="utf-8"))
                    active_model = str(cfg_data.get("vansrouter_model", "")).strip()
            except Exception:
                pass
        if not active_model:
            active_model = self.env.get("VANSROUTER_MODEL", "ag/gemini-3.8-flash-medium")
        self.model = active_model
        self.api_key = self.env.get("HERMES_API_KEY", "test") or "test"

    def _llm_call(self, messages: list) -> str:
        """One chat completion against the router endpoint. Handles both a
        plain JSON body and an SSE stream body."""
        self._refresh_env()
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": 0.3,
            "stream": False,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key}"
        }
        res = requests.post(f"{self.router_url}/v1/chat/completions",
                            json=payload, headers=headers, timeout=120)
        if res.status_code != 200:
            raise RuntimeError(f"HTTP {res.status_code}: {res.text[:150]}")

        raw_text = res.text.strip()
        content = ""
        try:
            content = res.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        except Exception:
            pass

        if not content and "data:" in raw_text:
            chunks = []
            for line in raw_text.splitlines():
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        c = json.loads(line[6:])
                        delta = c.get("choices", [{}])[0].get("delta", {})
                        if delta.get("content"):
                            chunks.append(delta["content"])
                    except Exception:
                        continue
            if chunks:
                content = "".join(chunks).strip()

        return content or raw_text

    def _extract_actions(self, text: str) -> tuple:
        """Pull the first hermes_action JSON block out of an LLM reply.
        Returns (actions_list, report_text, cleaned_text)."""
        match = self._ACTION_RE.search(text or "")
        if not match:
            return [], "", text or ""
        try:
            act_json = json.loads(match.group(1))
        except Exception as e:
            print(f"[HermesConnector] Action block parse error: {e}")
            return [], "", text
        if not isinstance(act_json, dict):
            return [], "", text
        actions = act_json.get("actions", [])
        if not actions and "action" in act_json:
            actions = [act_json]
        report = str(act_json.get("report_for_mark", "") or "").strip()
        cleaned = text[:match.start()] + text[match.end():]
        return actions, report, cleaned

    @staticmethod
    def _summarize_results(results: list) -> str:
        """Human-readable ✅/❌ list of what ACTUALLY happened on this machine."""
        lines = []
        for i, r in enumerate(results, 1):
            r = r if isinstance(r, dict) else {"detail": str(r)}
            mark = "✅" if r.get("success") else "❌"
            detail = r.get("detail") or r.get("error") or "no detail returned"
            lines.append(f"{i}. {mark} {detail}")
        return "\n".join(lines) if lines else "(no actions were executed)"

    def _execute_and_verify(self, messages: list, first_reply: str) -> str:
        """Run the plan, show the real results back to the model, allow ONE
        repair round, then return a report that only claims verified outcomes."""
        from core.hermes_executor import execute_hermes_actions

        actions, report, cleaned = self._extract_actions(first_reply)
        if not actions:
            return first_reply          # pure answer, nothing to verify

        print(f"[HermesConnector] Executing {len(actions)} action(s)...")
        try:
            results = execute_hermes_actions(actions)
        except Exception as e:
            results = [{"success": False, "error": f"executor crashed: {e}"}]
        summary = self._summarize_results(results)
        print(f"[HermesConnector] Real results:\n{summary}")

        # Pass 2 — the model finally SEES reality and may repair or confess.
        verify_prompt = (
            "HASIL EKSEKUSI NYATA di laptop pengguna:\n"
            f"{summary}\n\n"
            "ATURAN VERIFIKASI (wajib):\n"
            "1. Jika ada aksi ❌ GAGAL dan masih bisa diperbaiki, keluarkan SATU blok "
            "```hermes_action``` baru berisi aksi perbaikan (retry dengan cara lain / langkah alternatif).\n"
            "2. Jika semua ✅, atau gagalnya tidak bisa diperbaiki, JANGAN keluarkan blok aksi.\n"
            "3. Tulis 'report_for_mark' final yang HANYA mengklaim keberhasilan yang benar-benar "
            "terjadi (berdasar ✅ di atas). Kegagalan diakui apa adanya dengan penyebab singkat. "
            "Bahasa Indonesia orang pertama ('saya').\n"
            "Balas dengan blok aksi perbaikan (jika perlu) + report_for_mark final."
        )
        try:
            second_reply = self._llm_call(messages + [
                {"role": "assistant", "content": first_reply},
                {"role": "user", "content": verify_prompt},
            ])
        except Exception as e:
            print(f"[HermesConnector] Verify pass failed ({e}) — returning pass-1 report + real status")
            second_reply = ""

        repair_actions, repair_report, _ = self._extract_actions(second_reply)
        repair_results: list = []
        if repair_actions:
            print(f"[HermesConnector] Repair round: {len(repair_actions)} action(s)...")
            try:
                repair_results = execute_hermes_actions(repair_actions)
            except Exception as e:
                repair_results = [{"success": False, "error": f"executor crashed: {e}"}]
            summary += "\nSetelah perbaikan:\n" + self._summarize_results(repair_results)
            if repair_report:
                report = repair_report

        final_report = report or cleaned.strip() or second_reply.strip() or first_reply.strip()

        # Persistent task ledger — record the REAL outcomes (including any
        # repair round) so future similar tasks reuse what actually worked.
        try:
            from memory.memory_manager import record_task_result
            task_text = str(messages[-1].get("content", "")) if messages else ""
            if "INSTRUKSI TUGAS:" in task_text:
                task_text = task_text.split("INSTRUKSI TUGAS:", 1)[1]
            record_task_result(task_text, list(actions) + list(repair_actions),
                               list(results) + list(repair_results))
        except Exception as e:
            print(f"[HermesConnector] task ledger skipped: {e}")

        return f"{final_report}\n\n[Status Eksekusi di Laptop]:\n{summary}"

    def save_learning(self, skill_name: str, content: str) -> bool:
        """Save an autonomously generated skill or learning insight."""
        try:
            safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in skill_name).lower()
            file_path = self.skills_dir / f"{safe_name}.json"
            record = {
                "skill_name": skill_name,
                "timestamp": time.time(),
                "content": content
            }
            file_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
            return True
        except Exception as e:
            print(f"[HermesConnector] Failed to save learning: {e}")
            return False

    def get_skill(self, skill_name: str) -> Optional[str]:
        """Retrieve a previously learned skill."""
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in skill_name).lower()
        file_path = self.skills_dir / f"{safe_name}.json"
        if file_path.exists():
            try:
                data = json.loads(file_path.read_text(encoding="utf-8"))
                return data.get("content")
            except Exception:
                pass
        return None


# ── Module-level wrapper ─────────────────────────────────────────────────────
# core/brain_hub.py does `from router.hermes_connector import process_heavy_task`.
# The name previously existed ONLY as a HermesConnector method, so that import
# always failed and the HERMES brain was permanently "belum punya konektor" —
# heavy tasks silently fell through to chat-only brains that cannot execute.
def process_heavy_task(user_input: str, context: Optional[str] = None,
                       execute_actions: bool = True) -> str:
    """Heavy-task entry point for the multi-brain layer (brain_hub et al.)."""
    return HermesConnector().process_heavy_task(
        user_input, context=context, execute_actions=execute_actions)
