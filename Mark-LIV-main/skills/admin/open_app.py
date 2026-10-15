import ctypes
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "msedge",                  "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "msedge",                  "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "x-terminal-emulator"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "vansrouter":         {"Windows": "vansrouter.cmd",          "Darwin": "vansrouter",           "Linux": "vansrouter"},
    "vans router":        {"Windows": "vansrouter.cmd",          "Darwin": "vansrouter",           "Linux": "vansrouter"},
    "vanrouter":          {"Windows": "vansrouter.cmd",          "Darwin": "vansrouter",           "Linux": "vansrouter"},
    "van router":         {"Windows": "vansrouter.cmd",          "Darwin": "vansrouter",           "Linux": "vansrouter"},
    "vansrouter.cmd":     {"Windows": "vansrouter.cmd",          "Darwin": "vansrouter",           "Linux": "vansrouter"},
    "vanrouter.cmd":      {"Windows": "vansrouter.cmd",          "Darwin": "vansrouter",           "Linux": "vansrouter"},
}


def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)

    return raw  

def _find_windows_app_path(app_name: str) -> str | None:
    try:
        import winreg
        names = [app_name]
        if not app_name.lower().endswith(".exe"):
            names.append(f"{app_name}.exe")
        for n in names:
            for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"):
                    try:
                        with winreg.OpenKey(root, f"{sub}\\{n}") as k:
                            val, _ = winreg.QueryValueEx(k, "")
                            clean = val.replace('"', '').strip()
                            if clean and os.path.exists(clean):
                                return clean
                    except Exception:
                        pass
    except Exception:
        pass
    return None


def _launch_windows(app_name: str) -> bool:
    # 1. Registry App Paths lookup (e.g. excel.exe, winword.exe, powerpnt.exe)
    reg_path = _find_windows_app_path(app_name)
    if reg_path:
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", reg_path, "", None, 1)
            if ret > 32:
                time.sleep(1.0)
                return True
        except Exception:
            pass

    # 2. Check PATH with ShellExecute / subprocess
    which_exe = shutil.which(app_name) or shutil.which(app_name.split(".")[0])
    if which_exe:
        if which_exe.lower().endswith((".cmd", ".bat")):
            try:
                subprocess.Popen(f'start "" "{which_exe}"', shell=True)
                time.sleep(1.0)
                return True
            except Exception as e:
                print(f"[open_app] batch launch failed: {e}")
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", which_exe, "", None, 1)
            if ret > 32:
                time.sleep(1.0)
                return True
        except Exception:
            pass
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(1.5)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    # 3. Direct ShellExecute with .exe name
    try:
        exe_n = app_name if app_name.endswith(".exe") else f"{app_name}.exe"
        ret = ctypes.windll.shell32.ShellExecuteW(None, "open", exe_n, "", None, 1)
        if ret > 32:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    if ":" in app_name:
        try:
            subprocess.Popen(f"start {app_name}", shell=True)
            time.sleep(1.0)
            return True
        except Exception:
            pass

    # 4. Fallback to start menu search
    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(0.7)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.9)
        pyautogui.press("enter")
        time.sleep(2.5)
        return True
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


_LINUX_TERMINAL_FALLBACKS = [
    "x-terminal-emulator", "gnome-terminal", "konsole", "xfce4-terminal",
    "xterm", "lxterminal", "mate-terminal", "tilix", "alacritty", "kitty",
]

def _launch_linux(app_name: str) -> bool:

    # terminal emulators: try common ones in order
    if app_name in ("x-terminal-emulator", "gnome-terminal", "terminal"):
        for term in _LINUX_TERMINAL_FALLBACKS:
            if shutil.which(term):
                try:
                    subprocess.Popen([term], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    time.sleep(1.0)
                    return True
                except Exception:
                    continue

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

def _try_focus_existing(app_name: str, normalized: str) -> str | None:
    """Kalau aplikasi SUDAH jalan, fokuskan jendelanya — jangan buka instance baru.

    Memakai app_manager.switch (restore + foreground via Win32). Return None
    kalau app_manager tidak tersedia atau jendelanya tidak ketemu, sehingga
    pemanggil lanjut ke launcher normal.
    """
    if _SYSTEM != "Windows":
        return None
    try:
        import importlib.util
        am_path = Path(__file__).resolve().parent / "app_manager.py"
        spec = importlib.util.spec_from_file_location("_neira_app_manager", am_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        for target in (normalized, app_name):
            if not target:
                continue
            result = mod.app_manager({"cmd": "switch", "target": target})
            # Hanya sukses bila app_manager konfirmasi fokus (✅). Pesan
            # 'tidak ditemukan' / 'tidak sedang berjalan' artinya lanjut launch.
            if result and "✅" in result:
                print(f"[open_app] Already running → focused: '{target}'")
                return result
    except Exception as e:
        print(f"[open_app] focus-existing check skipped: {e}")
    return None


def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()

    if not app_name:
        return "No application name provided."

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    normalized = _normalize(app_name)
    print(f"[open_app] Request: '{app_name}' -> '{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    # ── Sudah jalan? Fokus jendelanya, jangan buka dobel ─────────────────────
    focused = _try_focus_existing(app_name, normalized)
    if focused:
        return focused

    try:
        if launcher(normalized):
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower():
            if launcher(app_name):
                return f"Opened {app_name}."

        # ── installed_apps cache lookup (fast, no deep scan) ─────────────────
        # Try the cached catalog before the expensive hermes_remediator scan.
        try:
            import importlib.util as _ilu
            _ia_path = Path(__file__).resolve().parent / "installed_apps.py"
            _ia_spec = _ilu.spec_from_file_location("_neira_installed_apps", _ia_path)
            _ia_mod = _ilu.module_from_spec(_ia_spec)
            _ia_spec.loader.exec_module(_ia_mod)
            catalog = _ia_mod._get_catalog()
            matches = _ia_mod._search_apps(catalog, app_name)
            if matches:
                result = _ia_mod._launch_entry(matches[0])
                if "✅" in result:
                    return result
        except Exception as err:
            print(f"[open_app] installed_apps fallback skipped: {err}")

        # ── Autonomous Self-Healing by Hermes (CLI Worker) ──────────────────
        # If normal launcher cannot confirm, Mandor (Mark-LIV) delegates to
        # Hermes Remediator to perform deep scanning, CLI resolution, and learning.
        try:
            from core.hermes_remediator import remediate_app_launch
            remediation = remediate_app_launch(app_name, failure_reason="Standard launcher failed to resolve application path.")
            if remediation.get("success"):
                return remediation.get("detail", f"Berhasil membuka {app_name} setelah investigasi sistem.")
            else:
                return remediation.get("detail", f"Tidak dapat mengonfirmasi {app_name} terbuka.")
        except Exception as err:
            print(f"[open_app] Remediation error: {err}")

        return (
            f"Could not confirm that {app_name} launched. "
            f"It may still be loading, or it might not be installed."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        # Even on exception, attempt Hermes remediation!
        try:
            from core.hermes_remediator import remediate_app_launch
            remediation = remediate_app_launch(app_name, failure_reason=str(e))
            if remediation.get("success"):
                return remediation.get("detail", f"Berhasil mengatasi error dan membuka {app_name}.")
        except Exception:
            pass
        return f"Failed to open {app_name}: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "open_app",
    "description": "Opens any application on the computer. Use this whenever the user asks to open, launch, or start any app, website, or program. Always call this tool — never just say you opened it.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "app_name": {
                "type": "STRING",
                "description": "Exact name of the application (e.g. 'WhatsApp', 'Chrome', 'Spotify')"
            }
        },
        "required": [
            "app_name"
        ]
    },
    "handler": open_app,
}
