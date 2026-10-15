"""Smoke test: app_manager skill — Jarvis-grade running-app control.

Real end-to-end on this Windows machine:
  1. list            — enumerates actual running windowed apps
  2. spawn notepad   — open a real window
  3. switch          — focus it
  4. close           — polite close, verify process gone
  5. kill            — spawn again, force-kill
  6. protection      — attempt to kill 'csrss' must be refused
  7. discovery       — skill_hub (Hermes brain) sees the new skill
Run from Mark-LIV-main:  python scratch\\test_app_manager.py
"""
import subprocess
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from skills.admin.app_manager import app_manager, _list_apps  # noqa: E402

passed, failed = [], []


def check(name, cond, extra=""):
    (passed if cond else failed).append(name)
    print(("PASS" if cond else "FAIL"), "-", name, ("| " + extra if extra else ""))


def spawn_notepad() -> int:
    """Spawn notepad and return the PID that actually owns the window.

    On Windows 11 notepad is a Store app: the spawned pid can be a short-lived
    stub while the window belongs to a different pid — so we wait for the
    window to appear and report the pid from the window list itself."""
    proc = subprocess.Popen(["notepad.exe"])
    deadline = time.time() + 10.0
    while time.time() < deadline:
        for a in _list_apps():
            if (a["name"].lower() == "notepad"
                    or "notepad" in a["title"].lower()):
                return a["pid"]
        time.sleep(0.5)
    return proc.pid


def notepad_visible() -> list[dict]:
    return [a for a in _list_apps()
            if a["name"].lower() == "notepad"
            or "notepad" in a["title"].lower()]


try:
    # ── 1. list on the real desktop ──────────────────────────────────────────
    out = app_manager({"cmd": "list"})
    check("list returns app list", "Aplikasi aktif" in out, out.splitlines()[0][:60])
    apps = _list_apps()
    check("enumeration found windowed apps", len(apps) > 0, f"{len(apps)} apps")

    # ── 2. spawn a real notepad window ───────────────────────────────────────
    pid = spawn_notepad()
    try:
        vis = notepad_visible()
        check("spawned notepad appears in list", len(vis) > 0,
              f"pid={pid}, visible={[(a['pid'], a['title'][:20]) for a in vis]}")

        # ── 3. switch focus to it ────────────────────────────────────────────
        out = app_manager({"cmd": "switch", "target": "notepad"})
        check("switch focuses notepad", "✅" in out and "Fokus" in out, out[:80])

        # ── 4. polite close ──────────────────────────────────────────────────
        out = app_manager({"cmd": "close", "target": "notepad"})
        time.sleep(1.0)
        gone = len(notepad_visible()) == 0
        check("close shuts notepad down", "✅" in out and gone, out[:80])

        # ── 5. force kill ────────────────────────────────────────────────────
        pid2 = spawn_notepad()
        out = app_manager({"cmd": "kill", "target": str(pid2)})
        time.sleep(0.8)
        check("kill force-stops by PID",
              "✅" in out and len(notepad_visible()) == 0, out[:80])

        # ── 6. protected process rejection ───────────────────────────────────
        out = app_manager({"cmd": "kill", "target": "csrss"})
        check("protected system process refused", "Ditolak" in out, out[:80])

        # ── 7. unknown target message ────────────────────────────────────────
        out = app_manager({"cmd": "close", "target": "aplikasi_tidak_ada_123"})
        check("unknown target handled", "tidak ada aplikasi aktif" in out.lower(), out[:80])

        # ── 8. skill_hub discovery (Hermes brain) ────────────────────────────
        from core.skill_hub import skill_hub
        skill_hub.discover(force_reload=True)
        check("skill_hub sees app_manager", skill_hub.has("app_manager"))
        cat = skill_hub.get_hermes_catalog()
        check("app_manager in Hermes catalog", "app_manager" in cat)
        route = skill_hub.get_routing_guide()
        check("app_manager in routing map (ADMIN)", "app_manager" in route)
    finally:
        subprocess.run(["taskkill", "/F", "/IM", "notepad.exe"],
                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW)

    print()
    print(f"RESULT: {len(passed)} passed, {len(failed)} failed")
    sys.exit(1 if failed else 0)
except Exception as e:
    print(f"TEST CRASH: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
