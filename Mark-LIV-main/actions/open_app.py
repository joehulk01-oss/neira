import ctypes
import os
import platform
import shutil
import subprocess
import sys
import time

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

# ── Window focus helpers (Windows-only) ──────────────────────────────────────

def _iter_windows() -> list[tuple[int, str, int]]:
    """Return list of (hwnd, title, pid) for all visible, non-minimized-to-nothing windows."""
    results = []
    if _SYSTEM != "Windows":
        return results
    try:
        import ctypes
        EnumWindows        = ctypes.windll.user32.EnumWindows
        EnumWindowsProc    = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int))
        GetWindowTextW     = ctypes.windll.user32.GetWindowTextW
        GetWindowTextLenW  = ctypes.windll.user32.GetWindowTextLengthW
        IsWindowVisible    = ctypes.windll.user32.IsWindowVisible
        GetWindowThreadProcessId = ctypes.windll.user32.GetWindowThreadProcessId

        def _cb(hwnd, _):
            if not IsWindowVisible(hwnd):
                return True
            length = GetWindowTextLenW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            pid = ctypes.c_ulong(0)
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            results.append((hwnd, title, pid.value))
            return True

        EnumWindows(EnumWindowsProc(_cb), 0)
    except Exception as e:
        print(f"[open_app] EnumWindows error: {e}")
    return results


def _exe_stem(proc_name: str) -> str:
    """'Spotify.exe' → 'spotify', 'chrome' → 'chrome'."""
    return proc_name.lower().removesuffix(".exe")


def _find_and_focus_window(app_name: str, normalized: str) -> bool:
    """Check if app is already running and focus/restore its window.
    
    Strategy (in order):
    1. Match running process name via psutil against app_name / normalized
    2. Match window title containing app_name / normalized
    
    Returns True if a window was found and focused.
    """
    if _SYSTEM != "Windows":
        return False

    # Build candidate name set for matching
    candidates = {_exe_stem(app_name), _exe_stem(normalized)}
    # Also add aliases: if normalized maps to e.g. "msedge" add "edge"
    for alias_key, os_map in _APP_ALIASES.items():
        win_val = os_map.get("Windows", "")
        if _exe_stem(win_val) in candidates or _exe_stem(alias_key) in candidates:
            candidates.add(_exe_stem(alias_key))
            candidates.add(_exe_stem(win_val))

    print(f"[open_app] Checking if already running: {candidates}")

    # Step 1: find PIDs of matching processes
    target_pids: set[int] = set()
    if _PSUTIL:
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                pname = _exe_stem(proc.info.get("name") or "")
                if any(c in pname or pname in c for c in candidates if len(c) >= 3):
                    target_pids.add(proc.info["pid"])
        except Exception as e:
            print(f"[open_app] psutil scan error: {e}")

    # Step 2: scan windows
    windows = _iter_windows()
    matched_hwnd = None

    # Priority: window belonging to a known PID
    if target_pids:
        for hwnd, title, pid in windows:
            if pid in target_pids:
                matched_hwnd = hwnd
                print(f"[open_app] Found via PID {pid}: '{title}' hwnd={hwnd}")
                break

    # Fallback: title match
    if matched_hwnd is None:
        for hwnd, title, pid in windows:
            title_l = title.lower()
            if any(c in title_l for c in candidates if len(c) >= 3):
                matched_hwnd = hwnd
                print(f"[open_app] Found via title: '{title}' hwnd={hwnd}")
                break

    if matched_hwnd is None:
        return False

    # Restore + bring to foreground
    try:
        SW_RESTORE = 9
        ctypes.windll.user32.ShowWindow(matched_hwnd, SW_RESTORE)
        ctypes.windll.user32.SetForegroundWindow(matched_hwnd)
        # If SetForegroundWindow is blocked (focus steal prevention), use keybd trick
        try:
            import ctypes
            INPUT_KEYBOARD = 1
            KEYEVENTF_KEYUP = 0x0002
            VK_MENU = 0x12  # Alt key
            class KEYBDINPUT(ctypes.Structure):
                _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                            ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                            ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]
            class INPUT_UNION(ctypes.Union):
                _fields_ = [("ki", KEYBDINPUT)]
            class INPUT(ctypes.Structure):
                _fields_ = [("type", ctypes.c_ulong), ("_", INPUT_UNION)]
            # Press+release Alt to allow SetForegroundWindow past focus lock
            inp = (INPUT * 2)()
            inp[0].type = INPUT_KEYBOARD
            inp[0]._.ki.wVk = VK_MENU
            inp[1].type = INPUT_KEYBOARD
            inp[1]._.ki.wVk = VK_MENU
            inp[1]._.ki.dwFlags = KEYEVENTF_KEYUP
            ctypes.windll.user32.SendInput(2, inp, ctypes.sizeof(INPUT))
            ctypes.windll.user32.SetForegroundWindow(matched_hwnd)
        except Exception:
            pass
        time.sleep(0.3)
        return True
    except Exception as e:
        print(f"[open_app] Focus failed: {e}")
        return False

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
    print(f"[open_app] Launching: '{app_name}' -> '{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        # ── Step 0: focus/restore if already running ──────────────────────────
        if _SYSTEM == "Windows" and _find_and_focus_window(app_name, normalized):
            return f"{app_name} sudah terbuka — saya bawa ke depan."

        if launcher(normalized):
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower():
            if launcher(app_name):
                return f"Opened {app_name}."

        # ── Autonomous Self-Healing by Hermes (CLI Worker) ──────────────────
        # If normal launcher cannot confirm, Mandor (Mark-LIV) delegates to
        # Hermes Remediator to perform deep scanning, CLI resolution, and learning.
        try:
            from core.hermes_remediator import remediate_app_launch
            remediation = remediate_app_launch(app_name, failure_reason="Standard launcher failed to resolve application path.")
            if remediation.get("success"):
                return remediation.get("detail", f"Hermes berhasil membuka {app_name} setelah investigasi sistem.")
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
                return remediation.get("detail", f"Hermes berhasil mengatasi error dan membuka {app_name}.")
        except Exception:
            pass
        return f"Failed to open {app_name}: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "open_app",
    "description": (
        "Opens any application on the computer, or focuses/restores it if already running. "
        "Use this whenever the user asks to open, launch, start, switch to, or bring up any app, website, or program. "
        "If the app is already open but minimized, this will restore and focus it without opening a new instance. "
        "Always call this tool — never just say you opened it."
    ),
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
