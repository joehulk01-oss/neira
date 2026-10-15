"""
Hermes Executor - Physical Action & OS Execution Engine for Hermes Agent.
Gives Hermes the hands to open applications, launch visible CMD terminals,
open coding tools (VS Code, Notepad, etc.), create scripts, and manipulate files.
"""
from __future__ import annotations

import ctypes
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _base_dir()
PROJECTS_DIR = Path.home() / "Desktop" / "NeiraProjects"
WORKSPACE_DIR = BASE_DIR / "workspace"

PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)

_IS_WINDOWS = platform.system() == "Windows"
_SW_SHOWNORMAL = 1


def open_visible_cmd(command: Optional[str] = None, cwd: Optional[str] = None, title: str = "Neira Terminal") -> Dict[str, Any]:
    """
    Opens a real, VISIBLE Windows Command Prompt on the user's desktop.
    Uses ShellExecuteW with SW_SHOWNORMAL so the window is never hidden by CREATE_NO_WINDOW.
    """
    work_dir = str(Path(cwd).resolve()) if cwd else str(PROJECTS_DIR)
    
    if command and command.strip():
        clean_cmd = command.strip()
        # Keep window open with /k and set title
        params = f'/k "title {title} & cd /d "{work_dir}" & echo [NEIRA TERMINAL] Menjalankan: {clean_cmd} & echo. & {clean_cmd}"'
    else:
        params = f'/k "title {title} & cd /d "{work_dir}" & echo [NEIRA TERMINAL] Siap menerima perintah. & echo."'

    if _IS_WINDOWS:
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "open", "cmd.exe", params, work_dir, _SW_SHOWNORMAL
            )
            if ret > 32:
                return {
                    "success": True,
                    "action": "open_visible_cmd",
                    "detail": f"Terminal CMD visual berhasil dibuka di layar ({work_dir}). Perintah: {command or 'CMD Siap'}"
                }
            else:
                os.system(f'start "" cmd.exe {params}')
                return {
                    "success": True,
                    "action": "open_visible_cmd",
                    "detail": f"Terminal CMD visual dibuka via fallback di {work_dir}."
                }
        except Exception as e:
            return {"success": False, "action": "open_visible_cmd", "error": str(e)}
    else:
        return {"success": False, "action": "open_visible_cmd", "error": "Hanya didukung di Windows."}


def open_visible_powershell(command: Optional[str] = None, cwd: Optional[str] = None) -> Dict[str, Any]:
    """Opens a visible PowerShell window on the screen."""
    work_dir = str(Path(cwd).resolve()) if cwd else str(PROJECTS_DIR)
    if command and command.strip():
        params = f'-NoExit -Command "Set-Location \'{work_dir}\'; Write-Host \'[NEIRA POWERSHELL]\' -ForegroundColor Cyan; {command}"'
    else:
        params = f'-NoExit -Command "Set-Location \'{work_dir}\'; Write-Host \'[NEIRA POWERSHELL] Siap.\' -ForegroundColor Cyan"'

    if _IS_WINDOWS:
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "open", "powershell.exe", params, work_dir, _SW_SHOWNORMAL
            )
            return {"success": ret > 32, "action": "open_powershell", "detail": "PowerShell dibuka di layar."}
        except Exception as e:
            return {"success": False, "action": "open_powershell", "error": str(e)}
    return {"success": False, "action": "open_powershell", "error": "Hanya di Windows."}


def run_command_hidden(command: str, cwd: Optional[str] = None, timeout: float = 180.0) -> Dict[str, Any]:
    """
    THE default way Neira runs commands: silently, output captured, window never
    shown. The user's desktop must not accumulate a pile of /k terminals every
    time a heavy task runs — a visible window is reserved for the rare case the
    user EXPLICITLY asks to open a terminal.

    Returns the real exit code plus stdout/stderr so the ✅/❌ verification loop
    (hermes_connector._execute_and_verify) judges facts, not guesses.
    """
    if not command or not command.strip():
        return {"success": False, "action": "run_cmd", "error": "Perintah kosong."}
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(Path(cwd).resolve()) if cwd else str(PROJECTS_DIR),
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        out = (completed.stdout or "").strip()
        err = (completed.stderr or "").strip()
        ok = completed.returncode == 0
        detail = f"exit={completed.returncode}"
        if out:
            detail += f" | output: {out[:400]}"
        if err:
            detail += f" | stderr: {err[:300]}"
        res = {
            "success": ok,
            "action": "run_cmd",
            "exit_code": completed.returncode,
            "detail": (detail if len(detail) > len("exit=0") else "selesai tanpa output"),
        }
        if not ok:
            res["error"] = f"exit={completed.returncode}" + (f": {err[:200]}" if err else "")
        return res
    except subprocess.TimeoutExpired:
        return {"success": False, "action": "run_cmd",
                "error": f"timeout: perintah belum selesai setelah {int(timeout)}s"}
    except Exception as e:
        return {"success": False, "action": "run_cmd", "error": str(e)}


def find_coding_tool() -> Tuple[str, str]:
    """
    Finds available coding tools on the system:
    Returns (tool_type, executable_or_command) e.g. ('vscode', 'code'), ('notepad++', path), or ('notepad', 'notepad.exe').
    """
    # 1. VS Code in PATH
    code_path = shutil.which("code") or shutil.which("code.cmd")
    if code_path:
        return "vscode", code_path
    
    # Common VS Code install paths
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    prog_files = os.environ.get("ProgramFiles", "C:\\Program Files")
    candidates = [
        Path(local_app_data) / "Programs" / "Microsoft VS Code" / "Code.exe",
        Path(prog_files) / "Microsoft VS Code" / "Code.exe",
    ]
    for c in candidates:
        if c.exists():
            return "vscode", str(c)

    # 2. Notepad++
    npp_paths = [
        Path(prog_files) / "Notepad++" / "notepad++.exe",
        Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "Notepad++" / "notepad++.exe",
    ]
    for c in npp_paths:
        if c.exists():
            return "notepad++", str(c)

    # 3. Fallback to standard Notepad
    return "notepad", "notepad.exe"


def open_coding_tool(target_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Opens a coding tool (VS Code if available, otherwise Notepad++ or Notepad)
    with the target file or folder loaded.
    """
    tool_type, exe_path = find_coding_tool()
    target = str(Path(target_path).resolve()) if target_path else str(PROJECTS_DIR)

    try:
        if tool_type == "vscode":
            if _IS_WINDOWS:
                ctypes.windll.shell32.ShellExecuteW(None, "open", exe_path, f'"{target}"', None, _SW_SHOWNORMAL)
            else:
                subprocess.Popen([exe_path, target])
            return {
                "success": True,
                "action": "open_coding_tool",
                "tool": "Visual Studio Code",
                "detail": f"Membuka VS Code dengan target: {target}"
            }
        elif tool_type == "notepad++":
            ctypes.windll.shell32.ShellExecuteW(None, "open", exe_path, f'"{target}"', None, _SW_SHOWNORMAL)
            return {
                "success": True,
                "action": "open_coding_tool",
                "tool": "Notepad++",
                "detail": f"Membuka Notepad++ dengan file: {target}"
            }
        else:
            # Notepad
            if Path(target).is_file():
                ctypes.windll.shell32.ShellExecuteW(None, "open", "notepad.exe", f'"{target}"', None, _SW_SHOWNORMAL)
                detail = f"Membuka file di Notepad: {target}"
            else:
                ctypes.windll.shell32.ShellExecuteW(None, "open", "explorer.exe", f'"{target}"', None, _SW_SHOWNORMAL)
                detail = f"Membuka folder proyek di File Explorer: {target}"
            return {
                "success": True,
                "action": "open_coding_tool",
                "tool": "Notepad/Explorer",
                "detail": detail
            }
    except Exception as e:
        return {"success": False, "action": "open_coding_tool", "error": str(e)}


def find_windows_app_path(app_name: str) -> Optional[str]:
    """
    Finds exact executable path from Windows Registry App Paths.
    Supports names like 'excel', 'winword', 'powerpnt', etc.
    """
    if not _IS_WINDOWS:
        return None
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


def _launch_shell(exe: str, params: str = "", fallback: str = "") -> bool:
    if _IS_WINDOWS:
        target_path = exe
        if not os.path.isabs(target_path):
            found = find_windows_app_path(target_path)
            if found:
                target_path = found

        if target_path.lower().endswith((".cmd", ".bat")):
            try:
                os.system(f'start "" "{target_path}" {params}')
                return True
            except Exception:
                pass

        try:
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", target_path, params, None, _SW_SHOWNORMAL)
            if ret > 32:
                return True
        except Exception:
            pass

        # Try appending .exe if not present
        if not target_path.lower().endswith(".exe"):
            try:
                ret = ctypes.windll.shell32.ShellExecuteW(None, "open", f"{target_path}.exe", params, None, _SW_SHOWNORMAL)
                if ret > 32:
                    return True
            except Exception:
                pass

        if fallback:
            try:
                os.system(fallback)
                return True
            except Exception:
                pass

        try:
            if os.path.exists(target_path):
                os.system(f'start "" "{target_path}" {params}')
            else:
                clean_cmd = target_path if target_path.endswith(".exe") else f"{target_path}.exe"
                os.system(f'start {clean_cmd} {params}')
            return True
        except Exception:
            pass
    return False


def _try_focus_existing(app_name: str) -> Optional[str]:
    """App sudah jalan? Fokuskan jendelanya (restore + foreground) — jangan buka dobel.

    Memakai skills/admin/app_manager.py cmd=switch. Return string sukses bila
    fokus berhasil (bertanda ✅), None bila app tidak jalan / helper gagal,
    sehingga pemanggil lanjut ke launcher normal.
    """
    if not _IS_WINDOWS:
        return None
    try:
        import importlib.util
        am_path = BASE_DIR / "skills" / "admin" / "app_manager.py"
        if not am_path.exists():
            return None
        spec = importlib.util.spec_from_file_location("_neira_app_manager", am_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        for target in (app_name.strip().lower().removesuffix(".exe"), app_name.strip()):
            if not target:
                continue
            result = mod.app_manager({"cmd": "switch", "target": target})
            # Hanya sukses bila app_manager konfirmasi fokus (✅).
            if isinstance(result, str) and "✅" in result:
                print(f"[hermes_executor] Already running → focused: '{target}'")
                return result
    except Exception as e:
        print(f"[hermes_executor] focus-existing check skipped: {e}")
    return None


def open_app(app_name: str) -> Dict[str, Any]:
    """
    Intelligently discovers and opens any application on the laptop.
    Supports names like 'excel', 'word', 'powerpoint', 'chrome', 'vscode', 'terminal', 'cmd', 'explorer', 'notepad', 'calculator', etc.
    """
    name_clean = app_name.strip().lower()

    # ── Sudah jalan? Fokus jendelanya, jangan buka dobel ─────────────────────
    focused = _try_focus_existing(app_name)
    if focused:
        return {"success": True, "action": "open_app", "detail": focused}

    aliases = {
        "excel": lambda: _launch_shell("excel.exe"),
        "ms excel": lambda: _launch_shell("excel.exe"),
        "microsoft excel": lambda: _launch_shell("excel.exe"),
        "spreadsheet": lambda: _launch_shell("excel.exe"),
        "word": lambda: _launch_shell("winword.exe"),
        "ms word": lambda: _launch_shell("winword.exe"),
        "microsoft word": lambda: _launch_shell("winword.exe"),
        "powerpoint": lambda: _launch_shell("powerpnt.exe"),
        "powerpnt": lambda: _launch_shell("powerpnt.exe"),
        "ppt": lambda: _launch_shell("powerpnt.exe"),
        "ms powerpoint": lambda: _launch_shell("powerpnt.exe"),
        "outlook": lambda: _launch_shell("outlook.exe"),
        "onenote": lambda: _launch_shell("onenote.exe"),
        "access": lambda: _launch_shell("msaccess.exe"),
        "paint": lambda: _launch_shell("mspaint.exe"),
        "cmd": lambda: open_visible_cmd(),
        "command prompt": lambda: open_visible_cmd(),
        "terminal": lambda: open_visible_cmd(),
        "powershell": lambda: open_visible_powershell(),
        "vscode": lambda: open_coding_tool(),
        "vs code": lambda: open_coding_tool(),
        "code": lambda: open_coding_tool(),
        "coding tool": lambda: open_coding_tool(),
        "calculator": lambda: _launch_shell("calc.exe"),
        "kalkulator": lambda: _launch_shell("calc.exe"),
        "notepad": lambda: _launch_shell("notepad.exe"),
        "catatan": lambda: _launch_shell("notepad.exe"),
        "explorer": lambda: _launch_shell("explorer.exe"),
        "file manager": lambda: _launch_shell("explorer.exe"),
        "chrome": lambda: _launch_shell("chrome.exe", fallback="start chrome"),
        "google chrome": lambda: _launch_shell("chrome.exe", fallback="start chrome"),
        "edge": lambda: _launch_shell("msedge.exe", fallback="start msedge"),
        "browser": lambda: _launch_shell("msedge.exe", fallback="start msedge"),
        "spotify": lambda: _launch_shell("spotify.exe", fallback="start spotify:"),
        "task manager": lambda: _launch_shell("taskmgr.exe"),
        "vansrouter": lambda: _launch_shell("vansrouter.cmd", fallback="start vansrouter.cmd"),
        "vans router": lambda: _launch_shell("vansrouter.cmd", fallback="start vansrouter.cmd"),
        "vanrouter": lambda: _launch_shell("vanrouter.cmd", fallback="start vanrouter.cmd"),
        "van router": lambda: _launch_shell("vanrouter.cmd", fallback="start vanrouter.cmd"),
        "vansrouter.cmd": lambda: _launch_shell("vansrouter.cmd", fallback="start vansrouter.cmd"),
        "vanrouter.cmd": lambda: _launch_shell("vanrouter.cmd", fallback="start vanrouter.cmd"),
    }

    if name_clean in aliases:
        res = aliases[name_clean]()
        if isinstance(res, dict):
            return res
        return {"success": True, "action": "open_app", "detail": f"Aplikasi '{app_name}' berhasil dibuka."}

    # Check Windows Registry App Paths directly
    reg_path = find_windows_app_path(name_clean)
    if reg_path and _launch_shell(reg_path):
        return {"success": True, "action": "open_app", "detail": f"Aplikasi '{app_name}' ditemukan dan dibuka ({reg_path})."}

    # Check PATH
    which_exe = shutil.which(name_clean) or shutil.which(f"{name_clean}.exe")
    if which_exe and _launch_shell(which_exe):
        return {"success": True, "action": "open_app", "detail": f"Aplikasi '{app_name}' ditemukan dan dibuka ({which_exe})."}

    # Try general shell launch with .exe
    if _launch_shell(name_clean):
        return {"success": True, "action": "open_app", "detail": f"Membuka '{app_name}' melalui Windows shell."}

    return {"success": False, "action": "open_app", "error": f"Aplikasi '{app_name}' tidak ditemukan di sistem."}


def create_and_run_script(
    code: str,
    filename: Optional[str] = None,
    run_in_terminal: bool = True,
    open_editor: bool = True,
    folder: Optional[str] = None
) -> Dict[str, Any]:
    """
    Creates a script file in the Neira projects folder,
    opens it in the coding tool, and optionally executes it in a visible CMD terminal.
    """
    target_dir = Path(folder).resolve() if folder else PROJECTS_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    if not filename:
        filename = f"neira_script_{int(time.time())}.py"
    elif not filename.endswith((".py", ".bat", ".js", ".html", ".sh", ".ps1", ".txt")):
        filename += ".py"

    file_path = target_dir / filename
    try:
        file_path.write_text(code, encoding="utf-8")
        results = [f"File berhasil dibuat: {file_path.name}"]

        if open_editor:
            tool_res = open_coding_tool(str(file_path))
            if tool_res.get("success"):
                results.append(f"Dibuka di editor ({tool_res.get('tool')})")

        if run_in_terminal:
            if filename.endswith(".py"):
                cmd = f'python "{file_path}"'
            elif filename.endswith(".bat"):
                cmd = f'"{file_path}"'
            elif filename.endswith(".ps1"):
                cmd = f'powershell -ExecutionPolicy Bypass -File "{file_path}"'
            else:
                cmd = f'type "{file_path}"'

            # Run SILENTLY and capture the real output — no more one-window-per-
            # script pile-up on the desktop, and the report now states the actual
            # exit code / printed output instead of "a terminal was opened".
            run_res = run_command_hidden(cmd, cwd=str(target_dir))
            if run_res.get("success"):
                results.append(f"Script dijalankan: {run_res.get('detail', 'selesai')}")
            else:
                results.append(f"Script GAGAL: {run_res.get('error') or run_res.get('detail', 'tanpa detail')}")

        return {
            "success": True,
            "action": "create_and_run_script",
            "file_path": str(file_path),
            "detail": " | ".join(results)
        }
    except Exception as e:
        return {"success": False, "action": "create_and_run_script", "error": str(e)}


def execute_hermes_actions(actions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Executes a list of actions parsed from Hermes's reasoning response.
    """
    results = []
    for item in actions:
        act = item.get("action") or item.get("type") or ""
        act = act.lower().strip()

        if act in ("open_app", "launch_app"):
            name = item.get("name") or item.get("target") or item.get("app") or ""
            res = open_app(name)
            if not res.get("success"):
                try:
                    from core.hermes_remediator import remediate_app_launch
                    rem = remediate_app_launch(name, failure_reason=res.get("error", "Quick alias failed"))
                    if rem.get("success"):
                        res = rem
                except Exception:
                    pass
            results.append(res)

        elif act in ("open_cmd", "open_terminal", "run_cmd", "run_command"):
            cmd = item.get("command") or item.get("cmd") or ""
            cwd = item.get("cwd") or None
            if cmd and not item.get("visible"):
                # Automation: hidden run with captured output — the desktop never
                # accumulates terminals, and verification gets a REAL exit code.
                res = run_command_hidden(cmd, cwd=cwd,
                                         timeout=float(item.get("timeout", 180)))
            else:
                # No command, or the model explicitly marked it visible → this is
                # a genuine "user wants a terminal window" request.
                res = open_visible_cmd(command=cmd if item.get("visible") else None,
                                       cwd=cwd)
            results.append(res)

        elif act in ("open_code_tool", "open_coding_tool", "open_editor"):
            path = item.get("path") or item.get("target") or None
            res = open_coding_tool(path)
            results.append(res)

        elif act in ("create_script", "write_code", "create_and_run"):
            code = item.get("code") or item.get("content") or ""
            fname = item.get("filename") or item.get("name") or None
            run_term = item.get("run_in_terminal", True)
            open_ed = item.get("open_editor", True)
            res = create_and_run_script(code=code, filename=fname, run_in_terminal=run_term, open_editor=open_ed)
            results.append(res)

        elif act in ("open_path", "open_file", "open_url"):
            target = item.get("target") or item.get("path") or item.get("url") or ""
            try:
                if target.startswith(("http://", "https://")):
                    os.system(f'start "" "{target}"')
                elif _IS_WINDOWS and Path(target).exists():
                    os.startfile(target)
                results.append({"success": True, "action": act, "detail": f"Membuka: {target}"})
            except Exception as e:
                results.append({"success": False, "action": act, "error": str(e)})

        elif act in ("register_skill", "create_skill", "save_skill"):
            name = item.get("name") or item.get("skill_name") or f"skill_{int(time.time())}"
            code = item.get("code") or item.get("content") or ""
            category = item.get("category") or "custom"
            try:
                from core.skill_hub import skill_hub
                reg_res = skill_hub.register_new_skill(name=name, code=code, category=category)
                if reg_res.get("success"):
                    results.append({
                        "success": True,
                        "action": "register_skill",
                        "detail": f"Skill baru '{name}' berhasil didaftarkan di kategori '{category}' dan langsung bisa dipakai."
                    })
                else:
                    results.append({"success": False, "action": "register_skill", "error": reg_res.get("error")})
            except Exception as e:
                results.append({"success": False, "action": "register_skill", "error": str(e)})

        elif act in ("use_skill_creator", "skill_creator"):
            # Self-improvement: Hermes creates a new skill via skill_creator
            sc_cmd = item.get("cmd") or item.get("skill_cmd") or "create"
            sc_name = item.get("name") or item.get("skill_name") or ""
            sc_code = item.get("code") or item.get("content") or ""
            sc_steps = item.get("steps") or ""
            sc_desc = item.get("description") or item.get("desc") or ""
            sc_cat = item.get("category") or "general"
            try:
                import importlib.util as _ilu
                sc_path = BASE_DIR / "skills" / "admin" / "skill_creator.py"
                sc_spec = _ilu.spec_from_file_location("_neira_skill_creator_exec", sc_path)
                sc_mod = _ilu.module_from_spec(sc_spec)
                sc_spec.loader.exec_module(sc_mod)
                sc_params = {
                    "cmd": sc_cmd,
                    "name": sc_name,
                    "code": sc_code,
                    "steps": sc_steps,
                    "description": sc_desc,
                    "category": sc_cat,
                }
                sc_result = sc_mod.skill_creator(sc_params)
                results.append({
                    "success": "✅" in str(sc_result) or "berhasil" in str(sc_result).lower(),
                    "action": "use_skill_creator",
                    "detail": str(sc_result),
                })
            except Exception as e:
                results.append({"success": False, "action": "use_skill_creator", "error": str(e)})

        else:
            # Universal Shared Skill Hub dispatch
            try:
                from core.skill_hub import skill_hub
                if skill_hub.has(act):
                    skill_res = skill_hub.run(act, item)
                    results.append({"success": True, "action": act, "detail": str(skill_res)})
                else:
                    results.append({"success": False, "action": act, "error": f"Aksi/skill '{act}' tidak dikenali."})
            except Exception as e:
                results.append({"success": False, "action": act, "error": str(e)})

    return results
