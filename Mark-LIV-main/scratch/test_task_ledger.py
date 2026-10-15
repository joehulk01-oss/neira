"""Smoke test: task ledger + multi-day session memory (amnesia fix).

Backs up the real long_term.json / task_ledger.json, runs assertions
against the live memory_manager API, then restores the originals.
Run from Mark-LIV-main:  python scratch\\test_task_ledger.py
"""
import json
import shutil
import sys
import tempfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from memory import memory_manager as mm   # noqa: E402

# ── Back up real stores ──────────────────────────────────────────────────────
tmp = Path(tempfile.mkdtemp())
lt_backup = None
tl_backup = None
if mm.MEMORY_PATH.exists():
    lt_backup = tmp / "long_term.json"
    shutil.copy2(mm.MEMORY_PATH, lt_backup)
if mm.TASK_LEDGER_PATH.exists():
    tl_backup = tmp / "task_ledger.json"
    shutil.copy2(mm.TASK_LEDGER_PATH, tl_backup)

passed = []
failed = []


def check(name, cond):
    (passed if cond else failed).append(name)
    print(("PASS" if cond else "FAIL"), "-", name)


try:
    # ── 1. Task ledger: record + prompt block ────────────────────────────────
    mm.TASK_LEDGER_PATH.unlink(missing_ok=True)
    mm.record_task_result(
        "buat ringkasan berita teknologi hari ini",
        [{"action": "web_search", "query": "berita teknologi"},
         {"action": "open_app", "app_name": "notepad"}],
        [{"success": True, "detail": "5 results"},
         {"success": True, "detail": "notepad opened"}],
    )
    mm.record_task_result(
        "ganti wallpaper desktop",
        [{"action": "run_cmd", "command": "powershell set-wallpaper"}],
        [{"success": False, "error": "file not found"}],
    )
    check("ledger file created", mm.TASK_LEDGER_PATH.exists())
    data = json.loads(mm.TASK_LEDGER_PATH.read_text(encoding="utf-8"))
    check("ledger has 2 entries", len(data) == 2)
    check("entry1 ok=2 fail=0", data[0]["ok"] == 2 and data[0]["fail"] == 0)

    block = mm.recent_tasks_for_prompt()
    check("TASK HISTORY block mentions task", "berita teknologi" in block)
    check("TASK HISTORY block marks success", "ok=2 fail=0" in block)
    check("TASK HISTORY block marks failure", "ok=0 fail=1" in block)

    # record with no real outcomes is ignored
    before = len(json.loads(mm.TASK_LEDGER_PATH.read_text(encoding="utf-8")))
    mm.record_task_result("empty run", [{"action": "x"}], [])
    after = len(json.loads(mm.TASK_LEDGER_PATH.read_text(encoding="utf-8")))
    check("no-op task not recorded", before == after)

    # ── 2. Session memory: peek (not pop) + greeted flag ────────────────────
    memory = mm._empty_memory()
    mm.save_memory(memory)                     # start from a clean store
    mm.save_session_summary("User discussed the Neira gateway pairing flow.")
    mm.save_session_summary("User built a skill for Reddit fetch.")

    entry = mm.peek_last_session()
    check("peek returns latest", entry is not None
          and "Reddit fetch" in entry.get("summary", ""))
    entry2 = mm.peek_last_session()
    check("peek does NOT consume (called twice, still there)", entry2 is not None)

    memory2 = mm.load_memory()
    check("sessions still on disk after peek", len(memory2.get("sessions", [])) == 2)

    mm.mark_session_greeted(entry)
    fresh = mm.load_memory().get("sessions", [])
    check("greeted flag saved", fresh[-1].get("greeted") is True)

    # ── 3. Multi-day block inside format_memory_for_prompt ──────────────────
    prompt_block = mm.format_memory_for_prompt(mm.load_memory())
    check("RECENT CONVERSATIONS block present",
          "RECENT CONVERSATIONS" in prompt_block)
    check("both day summaries in prompt",
          "pairing flow" in prompt_block and "Reddit fetch" in prompt_block)
    check("amnesia note present", "never claim you have no memory" in prompt_block)

    # ── 4. Folder map / task history injection in Hermes prompt ─────────────
    from router.hermes_connector import HermesConnector
    hc = HermesConnector()
    captured = {}
    real_call = hc._llm_call

    def fake_call(messages):
        captured["system"] = messages[0]["content"]
        return "No action needed."

    hc._llm_call = fake_call
    try:
        hc.process_heavy_task("test task", execute_actions=False)
    except Exception as e:                      # network down etc. — fine
        print("  (llm path raised, still inspectable:", e, ")")
    sys_text = captured.get("system", "")
    check("Hermes prompt has TASK HISTORY header", "TASK HISTORY" in sys_text)
    check("Hermes prompt has STORAGE MAP", "STORAGE MAP" in sys_text)
    check("folder map names skills path", "skills" in sys_text and "register_skill" in sys_text)
    check("folder map names memory path", "long_term.json" in sys_text)

    print()
    print(f"RESULT: {len(passed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)
finally:
    # ── Restore real stores ──────────────────────────────────────────────────
    if lt_backup and lt_backup.exists():
        shutil.copy2(lt_backup, mm.MEMORY_PATH)
    elif mm.MEMORY_PATH.exists():
        mm.MEMORY_PATH.unlink()
    if tl_backup and tl_backup.exists():
        shutil.copy2(tl_backup, mm.TASK_LEDGER_PATH)
    elif mm.TASK_LEDGER_PATH.exists():
        mm.TASK_LEDGER_PATH.unlink()
    print("restored real memory stores")
