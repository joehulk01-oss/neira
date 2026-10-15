"""
Deep Reasoning Tool for Mark-LIV (Hybrid Dual-Brain System).
Routes complex logic, in-depth analysis, and heavy coding tasks to VansRouter (http://127.0.0.1:20128/v1).
Auto-discovered by core/action_loader.py.
"""
import json
import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

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

_BASE = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"

_DEFAULT_URL = "http://127.0.0.1:20128"
_DEFAULT_MODEL = "ag/gemini-3.8-flash-medium"


def _load_config() -> Dict[str, Any]:
    try:
        if _CONFIG_PATH.exists():
            return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[DeepThink] Warning: Failed to read config: {e}")
    return {}


from core.hermes_executor import (
    execute_hermes_actions,
    open_visible_cmd,
    open_coding_tool,
    open_app,
    create_and_run_script,
)

def _parse_hermes_action_block(text: str) -> Tuple[Optional[Dict[str, Any]], str]:
    """Extract ```hermes_action ... ``` block if present."""
    pattern = r"```(?:hermes_action|json)?\s*(\{.*?\})\s*```"
    match = re.search(pattern, text, re.DOTALL)
    if match:
        raw_json = match.group(1).strip()
        try:
            data = json.loads(raw_json)
            if isinstance(data, dict) and ("actions" in data or "action" in data or "report_for_mark" in data):
                clean_text = text[:match.start()] + text[match.end():]
                return data, clean_text.strip()
        except Exception:
            pass
    return None, text


def deep_think(parameters: dict = None, params: dict = None, **kwargs) -> str:
    """
    Execute deep reasoning and physical OS actions through the local VansRouter engine.
    Called automatically by Gemini Live when deep thinking, coding, or app execution is requested.
    """
    p = parameters if parameters is not None else (params if params is not None else {})
    task = str(p.get("task", "")).strip()
    context = str(p.get("context", "")).strip()

    if not task:
        return "DeepThink error: Tidak ada instruksi atau tugas ('task') yang diberikan."

    cfg = _load_config()
    raw_url = os.environ.get("VANSROUTER_URL", str(cfg.get("vansrouter_url", _DEFAULT_URL))).rstrip("/")
    if not raw_url.endswith("/v1"):
        endpoint = f"{raw_url}/v1/chat/completions"
    else:
        endpoint = f"{raw_url}/chat/completions"

    model = os.environ.get("VANSROUTER_MODEL", str(cfg.get("vansrouter_model", _DEFAULT_MODEL))).strip()
    api_key = os.environ.get("HERMES_API_KEY", str(cfg.get("vansrouter_api_key", "test"))).strip() or "test"

    print(f"\n[DeepThink] [THINKING] Delegating task to VansRouter ({model})...")
    print(f"[DeepThink] [TASK] Preview: {task[:80]}...")

    system_prompt = (
        "You are the deep reasoning, OS execution, and self-healing core (the inner brain) of Neira — "
        "one single desktop voice assistant. You work behind Neira's voice and are never a separate "
        "assistant: never name yourself, never say 'Hermes', and write every user-facing report in "
        "first person ('saya'), as if Neira herself did the work. "
        "When a commanded action previously failed (or when an error occurs): "
        "1. YOU MUST ANALYZE WHY IT FAILED (e.g. executable not found, wrong path, missing dependencies, permissions). "
        "2. YOU MUST SOLVE AND FIX IT AUTONOMOUSLY in the Windows environment (via CLI, PowerShell, registry search, Start Menu shortcuts, or script creation). "
        "3. YOU MUST LEARN FROM THE MISTAKE so it is permanently resolved in your memory and skills. "
        "You have full OS rights to open visible CMDs, launch coding tools (VS Code/Notepad), run scripts, and fix failures.\n\n"
        "If actions on the computer are needed, you MUST include an action block formatted like this:\n"
        "```hermes_action\n"
        "{\n"
        "  \"thought\": \"Jelaskan analisa mendalam mengapa sebelumnya gagal dan langkah teknis memperbaikinya\",\n"
        "  \"actions\": [\n"
        "    {\"action\": \"open_app\", \"name\": \"nama aplikasi e.g. excel, word, chrome, calc, vscode\"},\n"
        "    {\"action\": \"open_cmd\", \"command\": \"perintah CLI/PowerShell untuk dijalankan di CMD visual (opsional)\"},\n"
        "    {\"action\": \"open_code_tool\", \"path\": \"folder atau file untuk dibuka di VS Code\"},\n"
        "    {\"action\": \"create_script\", \"filename\": \"nama_file.py\", \"code\": \"kode perbaikan lengkap\", \"run_in_terminal\": true, \"open_editor\": true}\n"
        "  ],\n"
        "  \"learned_lesson\": \"Pelajaran spesifik dari kasus ini untuk disimpan ke memori\",\n"
        "  \"report_for_mark\": \"Laporan ramah dalam Bahasa Indonesia ORANG PERTAMA (pakai 'saya') untuk dibacakan Neira ke pengguna: jelaskan penyebab awal kegagalan, tindakan perbaikan yang saya lakukan di CLI/sistem, dan konfirmasi bahwa masalah telah tuntas. Jangan sebut nama internal.\"\n"
        "}\n"
        "```\n"
        "If no physical action is needed (pure discussion), provide clear, actionable answers in Indonesian with:\n"
        "REPORT_FOR_MARK: (Ringkasan ramah dalam Bahasa Indonesia, orang pertama 'saya', untuk disampaikan ke pengguna)."
    )

    user_content = task
    if context:
        user_content = f"KONTEKS / KODE TERKAIT:\n{context}\n\nTUGAS ANALISIS & EKSEKUSI:\n{task}"

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "stream": False,
        "temperature": 0.4,
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }

    raw_content = ""
    try:
        response = requests.post(endpoint, json=payload, headers=headers, timeout=120)
        
        if response.status_code != 200:
            err_msg = response.text[:200]
            print(f"[DeepThink] [ERROR] VansRouter returned HTTP {response.status_code}: {err_msg}")
            return (
                f"VansRouter error ({response.status_code}): {err_msg}. "
                "Pastikan model tersebut aktif di VansRouter."
            )

        data = response.text.strip()
        try:
            res_json = response.json()
            choices = res_json.get("choices", [])
            if choices and "message" in choices[0]:
                raw_content = choices[0]["message"].get("content", "").strip()
        except Exception:
            pass

        if not raw_content and "data:" in data:
            collected = []
            for line in data.splitlines():
                line = line.strip()
                if line.startswith("data: ") and line != "data: [DONE]":
                    try:
                        chunk_json = json.loads(line[6:])
                        delta = chunk_json.get("choices", [{}])[0].get("delta", {})
                        if "content" in delta and delta["content"]:
                            collected.append(delta["content"])
                    except Exception:
                        continue
            if collected:
                raw_content = "".join(collected).strip()

        if not raw_content:
            raw_content = data

    except requests.exceptions.ConnectionError:
        print(f"[DeepThink] [ERROR] Connection error to {endpoint}")
        return (
            f"[PERINGATAN] VansRouter tidak dapat dihubungi di {raw_url}.\n"
            "Pastikan VansRouter sudah dibuka dan berjalan di laptop Anda pada port 20128."
        )
    except requests.exceptions.Timeout:
        return "[PERINGATAN] VansRouter membutuhkan waktu terlalu lama (timeout > 120s)."
    except Exception as e:
        print(f"[DeepThink] [ERROR] Unexpected error: {e}")
        return f"Error saat menghubungi VansRouter: {e}"

    # ── Parse Hermes Actions & Execute ─────────────────────────────────────────
    action_data, cleaned_text = _parse_hermes_action_block(raw_content)
    action_results = []

    if action_data:
        actions_list = action_data.get("actions", [])
        if not actions_list and "action" in action_data:
            actions_list = [action_data]
        if actions_list:
            print(f"[DeepThink] [HERMES EXECUTOR] Executing {len(actions_list)} physical action(s)...")
            action_results = execute_hermes_actions(actions_list)

        # ── Persist Learned Lesson to Hermes Memory & Skills ──────────────────
        if action_data.get("learned_lesson"):
            try:
                from core.hermes_remediator import save_learned_fix
                save_learned_fix(
                    key=task[:50],
                    fix_info={
                        "action": "hermes_remediation",
                        "target": str(actions_list),
                        "explanation": str(action_data.get("learned_lesson")),
                    }
                )
                print(f"[DeepThink] [LEARNED] Lesson stored in core memory: {action_data['learned_lesson'][:60]}...")
            except Exception as e:
                print(f"[DeepThink] Warning: Could not save learned lesson: {e}")

    # ── Heuristic fallback if Hermes did not emit JSON but task asked to open/run ─
    task_lower = task.lower()
    if not action_results:
        from core.hermes_remediator import remediate_app_launch
        for app_candidate in ("excel", "word", "powerpoint", "chrome", "vscode"):
            if app_candidate in task_lower and ("buka" in task_lower or "open" in task_lower or "gagal" in task_lower):
                print(f"[DeepThink] [AUTO-REMEDIATE] Core investigating and launching {app_candidate}...")
                rem = remediate_app_launch(app_candidate, failure_reason="User or task requested opening/remediation")
                action_results.append(rem)
                break

    if not action_results:
        if "buka cmd" in task_lower or "terminal" in task_lower or "command prompt" in task_lower:
            print("[DeepThink] [HEURISTIC] Auto-opening visible CMD terminal...")
            action_results.append(open_visible_cmd(title="Neira Terminal - Permintaan Pengguna"))
        elif "buka vscode" in task_lower or "buka vs code" in task_lower or "tool coding" in task_lower or "coding tool" in task_lower:
            print("[DeepThink] [HEURISTIC] Auto-opening coding tool (VS Code)...")
            action_results.append(open_coding_tool())
        elif "kalkulator" in task_lower and ("buka" in task_lower or "open" in task_lower):
            action_results.append(open_app("calc"))

    # ── Build Collaborative Response for Mark ─────────────────────────────────
    report_text = ""
    if action_data and action_data.get("report_for_mark"):
        report_text = str(action_data["report_for_mark"]).strip()
    elif "REPORT_FOR_MARK:" in raw_content:
        report_text = raw_content.split("REPORT_FOR_MARK:", 1)[1].strip()
    else:
        # First 2 sentences of cleaned response
        sentences = [s.strip() for s in cleaned_text.split(".") if s.strip()]
        report_text = ". ".join(sentences[:3]) + ("." if sentences else "")

    exec_summaries = []
    for r in action_results:
        if r.get("detail"):
            exec_summaries.append(f"✓ {r['detail']}")
        elif r.get("error"):
            exec_summaries.append(f"⚠ {r['error']}")

    final_response = report_text
    if exec_summaries:
        summary_block = "\n".join(exec_summaries)
        final_response = f"{report_text}\n\n[Status Eksekusi di Laptop]:\n{summary_block}"

    print(f"[DeepThink] [OK] Completed with {len(action_results)} action(s) executed.")
    return final_response


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "deep_think",
    "description": (
        "Delegates complex reasoning, programming/coding problems, opening visible CMD terminals, "
        "launching coding tools (VS Code), opening applications, running scripts, or deep analysis "
        "to the internal deep reasoning & execution core. It physically executes the actions and "
        "reports back so you can speak the results in first person ('saya'), as your own work."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "task": {
                "type": "STRING",
                "description": "The specific complex task, question, coding request, or action to execute on the computer."
            },
            "context": {
                "type": "STRING",
                "description": "Optional background context, code snippet, or error details."
            }
        },
        "required": [
            "task"
        ]
    },
    "handler": deep_think,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
}

