"""
Hermes Remediator - Autonomous Self-Healing & Learning Engine for Hermes Agent.
Acts as the background problem-solver and fixer when tasks or commands fail.
Mark-LIV serves as the Supervisor (Mandor) that delegates failures here to be resolved and learned.
"""
from __future__ import annotations

import ctypes
import glob
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
MEMORIES_DIR = BASE_DIR / "hermes-agent" / "data" / "memories"
SHARED_MEM_DIR = BASE_DIR / "shared" / "memory"
SKILLS_DIR = BASE_DIR / "hermes-agent" / "data" / "skills"

for d in (MEMORIES_DIR, SHARED_MEM_DIR, SKILLS_DIR):
    d.mkdir(parents=True, exist_ok=True)

FIXES_FILE = MEMORIES_DIR / "learned_fixes.json"
SHARED_FIXES_FILE = SHARED_MEM_DIR / "learned_fixes.json"

_IS_WINDOWS = platform.system() == "Windows"
_SW_SHOWNORMAL = 1


def load_learned_fixes() -> Dict[str, Any]:
    """Loads previously learned fixes from disk."""
    for f in (FIXES_FILE, SHARED_FIXES_FILE):
        if f.exists():
            try:
                return json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                pass
    return {}


def save_learned_fix(key: str, fix_info: Dict[str, Any]) -> None:
    """Saves a newly learned fix to core memory and shared memory."""
    data = load_learned_fixes()
    fix_info["timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
    data[key.lower().strip()] = fix_info

    content = json.dumps(data, indent=2, ensure_ascii=False)
    for f in (FIXES_FILE, SHARED_FIXES_FILE):
        try:
            f.write_text(content, encoding="utf-8")
        except Exception as e:
            print(f"[CoreRemediator] Error saving fix: {e}")

    # Also log as a learned skill summary
    try:
        skill_file = SKILLS_DIR / f"fix_{re_clean(key)}.md"
        skill_text = (
            f"# Learned Skill: How to run/fix '{key}'\n\n"
            f"- **Action**: {fix_info.get('action')}\n"
            f"- **Resolved Target**: {fix_info.get('target')}\n"
            f"- **Learned At**: {fix_info.get('timestamp')}\n"
            f"- **Explanation**: {fix_info.get('explanation')}\n"
        )
        skill_file.write_text(skill_text, encoding="utf-8")
    except Exception:
        pass


def re_clean(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in text).strip("_")


def find_all_start_menu_shortcuts() -> List[str]:
    """Finds all *.lnk files in user and system Start Menu."""
    if not _IS_WINDOWS:
        return []
    paths = [
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\**\*.lnk"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\**\*.lnk"),
    ]
    links = []
    for p in paths:
        try:
            links.extend(glob.glob(p, recursive=True))
        except Exception:
            pass
    return links


def deep_scan_app_locations(app_name: str) -> List[Dict[str, str]]:
    """
    Scans the Windows filesystem and Registry deeply for any matching executable or shortcut.
    """
    results: List[Dict[str, str]] = []
    name_clean = app_name.lower().strip()
    words = [w for w in name_clean.replace("-", " ").replace("_", " ").split() if len(w) > 2]

    # 1. Start Menu shortcuts
    all_links = find_all_start_menu_shortcuts()
    for lnk in all_links:
        base = os.path.basename(lnk).lower().replace(".lnk", "")
        if name_clean == base or (words and all(w in base for w in words)):
            results.append({"type": "start_menu_lnk", "path": lnk, "name": os.path.basename(lnk)})

    # 2. Windows Registry App Paths
    if _IS_WINDOWS:
        try:
            import winreg
            candidates = [name_clean, f"{name_clean}.exe"]
            for c in candidates:
                for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
                    for sub in (r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths",
                                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths"):
                        try:
                            with winreg.OpenKey(root, f"{sub}\\{c}") as k:
                                val, _ = winreg.QueryValueEx(k, "")
                                clean_val = val.replace('"', '').strip()
                                if clean_val and os.path.exists(clean_val):
                                    results.append({"type": "registry", "path": clean_val, "name": c})
                        except Exception:
                            pass
        except Exception:
            pass

    # 3. PATH search
    which_path = shutil.which(name_clean) or shutil.which(f"{name_clean}.exe")
    if which_path:
        results.append({"type": "path", "path": which_path, "name": name_clean})

    # 4. Program Files & LocalAppData scan for common office/apps
    known_patterns = {
        "excel": [
            r"%ProgramFiles%\Microsoft Office\root\Office*\EXCEL.EXE",
            r"%ProgramFiles(x86)%\Microsoft Office\root\Office*\EXCEL.EXE",
            r"%ProgramFiles%\Microsoft Office\Office*\EXCEL.EXE",
        ],
        "word": [
            r"%ProgramFiles%\Microsoft Office\root\Office*\WINWORD.EXE",
            r"%ProgramFiles(x86)%\Microsoft Office\root\Office*\WINWORD.EXE",
            r"%ProgramFiles%\Microsoft Office\Office*\WINWORD.EXE",
        ],
        "powerpoint": [
            r"%ProgramFiles%\Microsoft Office\root\Office*\POWERPNT.EXE",
            r"%ProgramFiles(x86)%\Microsoft Office\root\Office*\POWERPNT.EXE",
            r"%ProgramFiles%\Microsoft Office\Office*\POWERPNT.EXE",
        ],
        "chrome": [
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe",
        ],
        "vscode": [
            r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe",
            r"%ProgramFiles%\Microsoft VS Code\Code.exe",
        ],
    }

    for k, patterns in known_patterns.items():
        if k in name_clean or name_clean in k:
            for pat in patterns:
                expanded = os.path.expandvars(pat)
                for match in glob.glob(expanded):
                    if os.path.exists(match):
                        results.append({"type": "program_files", "path": match, "name": os.path.basename(match)})

    return results


def is_process_running(proc_name: str) -> bool:
    """Checks if a process is running using tasklist or psutil."""
    try:
        proc_clean = proc_name.lower().replace(".exe", "").strip()
        out = subprocess.check_output("tasklist /NH", shell=True, text=True, errors="replace")
        for line in out.splitlines():
            if proc_clean in line.lower():
                return True
    except Exception:
        pass
    return False


def launch_target_path(path: str) -> bool:
    """Launches an executable or shortcut cleanly via ShellExecuteW."""
    if not _IS_WINDOWS:
        return False
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(None, "open", path, "", None, _SW_SHOWNORMAL)
        if ret > 32:
            return True
    except Exception:
        pass
    try:
        os.startfile(path)
        return True
    except Exception:
        pass
    try:
        subprocess.Popen(f'start "" "{path}"', shell=True)
        return True
    except Exception:
        pass
    return False


def remediate_app_launch(app_name: str, failure_reason: str = "") -> Dict[str, Any]:
    """
    Autonomous Self-Healing: Called when normal app launch fails.
    Hermes deeply investigates, finds the real executable or shortcut,
    launches it, verifies it, and persists the learned solution.
    """
    key = app_name.lower().strip()
    print(f"\n[CoreRemediator] 🛠️ Neira requested failure analysis for: '{app_name}'...")
    if failure_reason:
        print(f"[CoreRemediator] Reason for failure: {failure_reason}")

    # 1. Check if we already have a learned fix for this app
    learned = load_learned_fixes().get(key)
    if learned and learned.get("target") and os.path.exists(learned["target"]):
        target = learned["target"]
        print(f"[CoreRemediator] [MEMORY] Found previously learned fix: '{target}'")
        if launch_target_path(target):
            return {
                "success": True,
                "action": "remediated_via_memory",
                "target": target,
                "detail": f"Saya membuka '{app_name}' menggunakan rute yang telah dipelajari sebelumnya ({target}).",
                "learned": True,
            }

    # 2. Run deep system scan
    candidates = deep_scan_app_locations(app_name)
    print(f"[CoreRemediator] [SCAN] Found {len(candidates)} candidate location(s).")

    for cand in candidates:
        target_path = cand["path"]
        print(f"[CoreRemediator] [REMEDIATION] Attempting launch via {cand['type']}: '{target_path}'...")
        if launch_target_path(target_path):
            # Give it a moment to spin up
            time.sleep(1.0)
            
            # Save learned fix
            fix_record = {
                "app": app_name,
                "target": target_path,
                "type": cand["type"],
                "explanation": f"Aplikasi '{app_name}' tidak terdaftar di PATH standar tetapi ditemukan di {cand['type']} ({target_path}).",
            }
            save_learned_fix(key, fix_record)

            report = (
                f"Analisis saya: '{app_name}' sebelumnya gagal karena tidak terdaftar di PATH Windows standar. "
                f"Saya menelusuri sistem dan menemukan jalurnya di: {target_path}. "
                f"Aplikasi telah berhasil diluncurkan dan rute ini saya simpan untuk perbaikan berikutnya."
            )
            return {
                "success": True,
                "action": "remediated_deep_scan",
                "target": target_path,
                "detail": report,
                "learned": True,
            }

    # 3. Fallback: Try Windows protocol or powershell start-process
    try:
        ps_cmd = f'powershell -Command "Start-Process \'{app_name}\' -ErrorAction SilentlyContinue"'
        subprocess.run(ps_cmd, shell=True, timeout=5)
        time.sleep(1.0)
        if is_process_running(app_name):
            save_learned_fix(key, {"app": app_name, "target": f"Start-Process {app_name}", "type": "powershell"})
            return {
                "success": True,
                "action": "remediated_powershell",
                "detail": f"Berhasil memicu proses '{app_name}' melalui subsistem PowerShell.",
                "learned": True,
            }
    except Exception:
        pass

    # If all failed, provide a thorough diagnostic report
    diagnostic = (
        f"Analisis Kegagalan: Aplikasi '{app_name}' tidak ditemukan di PATH, Registri Windows, "
        f"maupun Menu Start. Kemungkinan aplikasi belum terpasang di laptop ini atau terpasang dengan nama berbeda."
    )
    return {
        "success": False,
        "action": "remediation_failed",
        "detail": diagnostic,
        "learned": False,
    }


# --------------------------------------------------------------------------- #
# PATCH AMAN — sandbox validasi AST + backup atomik + rollback.
# Adopsi pola Brahma-Echo (SafetySandbox di actions/auto_heal_engine.py):
# kode kandidat WAJIB lolos ast.parse()+compile() di memori sebelum menyentuh
# disk; file inti yang dilindungi (IMMUNE) tidak bisa di-patch otomatis; setiap
# patch yang diterapkan dicatat ke riwayat supaya core.boot_sentry bisa
# me-rollback otomatis kalau crash terjadi setelah patch.
# --------------------------------------------------------------------------- #

# File inti yang TIDAK BOLEH di-patch otomatis (keamanan anti-brick).
IMMUNE_FILES = {
    "boot_sentry.py",
    "hermes_remediator.py",
    "task_queue.py",
    "learned_rules.py",
}


def validate_code(code_str: str, file_name: str = "<staging>") -> Tuple[bool, Optional[str]]:
    """Validasi kode kandidat: parse AST + compile di memori (tanpa menulis file)."""
    try:
        import ast
        ast.parse(code_str, filename=file_name)
    except SyntaxError as e:
        return False, f"sintaks tidak valid: {e}"
    try:
        compile(code_str, file_name, "exec")
    except Exception as e:
        return False, f"gagal compile: {e}"
    return True, None


def apply_patch_safely(
    target_file: Path,
    new_code: str,
    patch_id: str = "",
) -> Dict[str, Any]:
    """Terapkan patch kode ke file secara aman.

    Alur: tolak file immune → validasi AST → backup .bak → tulis atomik →
    catat ke riwayat patch (dibaca core.boot_sentry saat boot berikutnya).
    """
    target_file = Path(target_file)
    patch_id = patch_id or f"patch_{int(time.time())}"

    if target_file.name.lower() in IMMUNE_FILES:
        return {
            "success": False,
            "patch_id": patch_id,
            "detail": f"File '{target_file.name}' dilindungi (immune) — patch otomatis ditolak.",
        }

    ok, err = validate_code(new_code, file_name=target_file.name)
    if not ok:
        return {"success": False, "patch_id": patch_id, "detail": f"Patch ditolak: {err}"}

    try:
        target_file.parent.mkdir(parents=True, exist_ok=True)
        backup_path = target_file.with_suffix(target_file.suffix + ".bak")
        if target_file.exists():
            shutil.copy2(target_file, backup_path)

        tmp_path = target_file.with_suffix(target_file.suffix + ".tmp")
        tmp_path.write_text(new_code, encoding="utf-8")
        os.replace(tmp_path, target_file)  # tulis atomik

        try:
            from core.boot_sentry import record_patch
            record_patch(patch_id, target_file, backup_path)
        except Exception as e:
            print(f"[CoreRemediator] gagal catat riwayat patch: {e}")

        return {
            "success": True,
            "patch_id": patch_id,
            "target": str(target_file),
            "backup": str(backup_path),
            "detail": f"Patch '{patch_id}' diterapkan aman ke {target_file.name} (backup tersedia).",
        }
    except Exception as e:
        return {"success": False, "patch_id": patch_id, "detail": f"Gagal menerapkan patch: {e}"}


def rollback_patch(patch_id: str) -> Dict[str, Any]:
    """Kembalikan file yang pernah di-patch ke backup (.bak) berdasarkan patch_id."""
    try:
        from core.boot_sentry import load_patch_history, save_patch_history
    except Exception as e:
        return {"success": False, "detail": f"Riwayat patch tidak tersedia: {e}"}

    history = load_patch_history()
    for record in reversed(history):
        if record.get("patch_id") != patch_id:
            continue
        backup_file = Path(record.get("backup_path", ""))
        target_file = Path(record.get("target_file", ""))
        if not backup_file.exists():
            return {"success": False, "detail": f"Backup untuk '{patch_id}' tidak ditemukan."}
        try:
            shutil.copy2(backup_file, target_file)
            record["status"] = "rolled_back"
            save_patch_history(history)
            return {
                "success": True,
                "detail": f"Patch '{patch_id}' dibatalkan — {target_file.name} dikembalikan.",
            }
        except Exception as e:
            return {"success": False, "detail": f"Rollback gagal: {e}"}
    return {"success": False, "detail": f"Patch '{patch_id}' tidak ada di riwayat."}
