# installed_apps.py
# ─────────────────────────────────────────────────────────────────────────────
# Discover, list, search, and launch ALL installed applications on this PC —
# not limited to the hardcoded alias list in open_app.py.
#
# Sources (Windows): Start Menu *.lnk, Registry Uninstall keys, PATH executables.
# Cache persists to shared/memory/installed_apps_cache.json (24h TTL).
#
# Commands:  list | search | refresh | launch
# ─────────────────────────────────────────────────────────────────────────────
from __future__ import annotations

import glob
import json
import os
import platform
import shutil
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# ── base dir (same pattern as skill_creator.py) ──────────────────────────────
def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent   # admin/ -> skills/ -> root

BASE_DIR = _base_dir()
CACHE_FILE = BASE_DIR / "shared" / "memory" / "installed_apps_cache.json"
CACHE_TTL = 24 * 3600  # 24 hours

_IS_WINDOWS = platform.system() == "Windows"


# ── optional policy / audit (same guard pattern as other admin skills) ───────
try:
    from core.policy_engine import decide as _policy_decide
except Exception:
    _policy_decide = None

try:
    from core.audit_logger import log_event as _audit_log
except Exception:
    _audit_log = None


# ═══════════════════════════════════════════════════════════════════════════════
#  DISCOVERY — scan the system for every installed app
# ═══════════════════════════════════════════════════════════════════════════════

def _scan_start_menu() -> List[Dict[str, str]]:
    """Scan all *.lnk shortcuts in Start Menu → return app entries."""
    if not _IS_WINDOWS:
        return []
    entries: List[Dict[str, str]] = []
    patterns = [
        os.path.expandvars(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs\**\*.lnk"),
        os.path.expandvars(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs\**\*.lnk"),
    ]
    for pat in patterns:
        try:
            for lnk in glob.glob(pat, recursive=True):
                name = os.path.splitext(os.path.basename(lnk))[0]
                # Skip system noise (Uninstall, Help, Read Me, etc.)
                lowered = name.lower()
                if any(skip in lowered for skip in ("uninstall", "help", "readme", "read me", "documentation", "license")):
                    continue
                entries.append({
                    "name": name,
                    "path": lnk,
                    "source": "start_menu",
                })
        except Exception:
            pass
    return entries


def _scan_registry_uninstall() -> List[Dict[str, str]]:
    """Scan Registry Uninstall keys for installed programs (64-bit + 32-bit + user)."""
    if not _IS_WINDOWS:
        return []
    entries: List[Dict[str, str]] = []
    try:
        import winreg
        uninstall_roots = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        for hive, subkey_path in uninstall_roots:
            try:
                key = winreg.OpenKey(hive, subkey_path)
            except OSError:
                continue
            i = 0
            while True:
                try:
                    sub_name = winreg.EnumKey(key, i)
                    i += 1
                except OSError:
                    break
                try:
                    with winreg.OpenKey(key, sub_name) as sk:
                        display_name, _ = winreg.QueryValueEx(sk, "DisplayName")
                        if not display_name or not display_name.strip():
                            continue
                        # Skip system updates / VC++ redistributables noise
                        dn_lower = display_name.lower()
                        if any(skip in dn_lower for skip in ("security update", "hotfix", "cumulative update", "kb", "microsoft visual c++", "microsoft .net")):
                            continue
                        display_icon = ""
                        try:
                            display_icon, _ = winreg.QueryValueEx(sk, "DisplayIcon")
                        except OSError:
                            pass
                        install_location = ""
                        try:
                            install_location, _ = winreg.QueryValueEx(sk, "InstallLocation")
                        except OSError:
                            pass
                        entries.append({
                            "name": display_name.strip(),
                            "path": display_icon or install_location or "",
                            "source": "registry",
                        })
                except OSError:
                    continue
            winreg.CloseKey(key)
    except Exception:
        pass
    return entries


def _scan_path_executables() -> List[Dict[str, str]]:
    """Scan PATH directories for .exe / .cmd / .bat / .lnk files."""
    if not _IS_WINDOWS:
        return []
    entries: List[Dict[str, str]] = []
    path_dirs = os.environ.get("PATH", "").split(os.pathsep)
    seen_names = set()
    for d in path_dirs:
        d = d.strip()
        if not d or not os.path.isdir(d):
            continue
        try:
            for fname in os.listdir(d):
                if not fname.lower().endswith((".exe", ".cmd", ".bat", ".lnk")):
                    continue
                base = os.path.splitext(fname)[0].lower()
                if base in seen_names:
                    continue
                seen_names.add(base)
                entries.append({
                    "name": os.path.splitext(fname)[0],
                    "path": os.path.join(d, fname),
                    "source": "path",
                })
        except Exception:
            pass
    return entries


def _merge_learned_fixes(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Merge previously learned fixes from hermes_remediator into the catalog."""
    try:
        from core.hermes_remediator import load_learned_fixes
        fixes = load_learned_fixes()
        existing_names = {e["name"].lower() for e in entries}
        for app_key, fix in fixes.items():
            if not isinstance(fix, dict):
                continue
            app_name = fix.get("app", app_key)
            target = fix.get("target", "")
            if app_name.lower() not in existing_names and target:
                entries.append({
                    "name": app_name,
                    "path": target,
                    "source": "learned",
                })
    except Exception:
        pass
    return entries


def _deduplicate(entries: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Deduplicate by normalized name. Prefer entries with a real path."""
    seen: Dict[str, Dict[str, str]] = {}
    for e in entries:
        key = e["name"].lower().strip()
        if not key:
            continue
        if key not in seen or (e.get("path") and not seen[key].get("path")):
            seen[key] = e
    return sorted(seen.values(), key=lambda x: x["name"].lower())


def _full_scan() -> List[Dict[str, str]]:
    """Run all scanners and return a deduplicated catalog."""
    entries: List[Dict[str, str]] = []
    entries.extend(_scan_start_menu())
    entries.extend(_scan_registry_uninstall())
    entries.extend(_scan_path_executables())
    entries = _deduplicate(entries)
    entries = _merge_learned_fixes(entries)
    return entries


# ═══════════════════════════════════════════════════════════════════════════════
#  CACHE — persist catalog to disk with 24h TTL
# ═══════════════════════════════════════════════════════════════════════════════

def _load_cache() -> Optional[Dict[str, Any]]:
    """Load cache if it exists and is fresh. Returns None if stale/missing."""
    try:
        if CACHE_FILE.exists():
            data = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
            ts = data.get("timestamp", 0)
            if time.time() - ts < CACHE_TTL:
                return data
    except Exception:
        pass
    return None


def _save_cache(entries: List[Dict[str, str]]) -> None:
    """Persist catalog to cache file."""
    try:
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "timestamp": time.time(),
            "count": len(entries),
            "apps": entries,
        }
        CACHE_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"[installed_apps] Cache save failed: {e}")


def _get_catalog(force_refresh: bool = False) -> List[Dict[str, str]]:
    """Return the app catalog — from cache if fresh, else full scan."""
    if not force_refresh:
        cached = _load_cache()
        if cached:
            return cached.get("apps", [])
    entries = _full_scan()
    _save_cache(entries)
    return entries


# ═══════════════════════════════════════════════════════════════════════════════
#  SEARCH — fuzzy matching by name
# ═══════════════════════════════════════════════════════════════════════════════

def _search_apps(catalog: List[Dict[str, str]], query: str) -> List[Dict[str, str]]:
    """Fuzzy search: exact match first, then substring, then word overlap."""
    q = query.lower().strip()
    if not q:
        return catalog
    words = [w for w in q.replace("-", " ").replace("_", " ").split() if len(w) >= 2]

    exact = []
    substr = []
    word_match = []
    for e in catalog:
        name_lower = e["name"].lower()
        if q == name_lower:
            exact.append(e)
        elif q in name_lower or name_lower in q:
            substr.append(e)
        elif words and all(w in name_lower for w in words):
            word_match.append(e)
        elif words and any(w == name_lower for w in words):
            word_match.append(e)
    return exact + substr + word_match


# ═══════════════════════════════════════════════════════════════════════════════
#  LAUNCH — start an app from the catalog
# ═══════════════════════════════════════════════════════════════════════════════

def _launch_entry(entry: Dict[str, str]) -> str:
    """Launch an app entry. Try its path first, then fallback to name."""
    path = entry.get("path", "")
    name = entry.get("name", "")

    # If we have a real path, launch it
    if path and os.path.exists(path):
        try:
            from core.hermes_remediator import launch_target_path
            if launch_target_path(path):
                return f"✅ Membuka '{name}' dari {entry.get('source', 'catalog')}: {path}"
        except Exception:
            pass
        # Fallback: ShellExecuteW directly
        try:
            import ctypes
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", path, "", None, 1)
            if ret > 32:
                return f"✅ Membuka '{name}': {path}"
        except Exception:
            pass
        # Fallback: os.startfile
        try:
            os.startfile(path)
            return f"✅ Membuka '{name}': {path}"
        except Exception:
            pass

    # No path or path doesn't exist — try launching by name (Windows shell can resolve)
    if _IS_WINDOWS and name:
        try:
            import ctypes
            ret = ctypes.windll.shell32.ShellExecuteW(None, "open", name, "", None, 1)
            if ret > 32:
                return f"✅ Membuka '{name}' via shell."
        except Exception:
            pass

    return f"❌ Gagal membuka '{name}' — path tidak valid: {path}"


# ═══════════════════════════════════════════════════════════════════════════════
#  FORMATTING — pretty-print the catalog
# ═══════════════════════════════════════════════════════════════════════════════

def _format_catalog(entries: List[Dict[str, str]], query: str = "", max_items: int = 100) -> str:
    if not entries:
        return "Tidak ada aplikasi yang ditemukan."
    label = f" (filter: '{query}')" if query else ""
    lines = [f"📱 {len(entries)} aplikasi terinstal{label}:"]
    source_icons = {"start_menu": "📌", "registry": "📋", "path": "⚙️", "learned": "🧠"}
    for e in entries[:max_items]:
        icon = source_icons.get(e.get("source", ""), "•")
        path_short = e.get("path", "")
        if len(path_short) > 60:
            path_short = "…" + path_short[-57:]
        lines.append(f"  {icon} {e['name']}  →  {path_short}")
    if len(entries) > max_items:
        lines.append(f"  … dan {len(entries) - max_items} lainnya.")
    return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN HANDLER
# ═══════════════════════════════════════════════════════════════════════════════

def installed_apps(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Discover, list, search, or launch all installed applications.

    Parameters:
        cmd:    'list' | 'search' | 'refresh' | 'launch'
        query:  app name to search or launch (required for search/launch)
    """
    p = parameters if isinstance(parameters, dict) else {}
    cmd = str(p.get("cmd", "list")).lower().strip()
    query = str(p.get("query", "")).strip()

    # Policy gate
    if _policy_decide:
        try:
            decision = _policy_decide(
                action="installed_apps",
                target=query or cmd,
                context=f"cmd={cmd}",
            )
            if isinstance(decision, dict) and decision.get("deny"):
                return f"⛔ Ditolak: {decision.get('reason', 'policy')}"
        except Exception:
            pass

    try:
        # ── list ──
        if cmd == "list":
            catalog = _get_catalog()
            return _format_catalog(catalog)

        # ── search ──
        elif cmd == "search":
            if not query:
                return "⚠️ Berikan nama aplikasi untuk dicari: cmd=search, query=\"nama_app\""
            catalog = _get_catalog()
            results = _search_apps(catalog, query)
            return _format_catalog(results, query=query)

        # ── refresh ──
        elif cmd == "refresh":
            t0 = time.time()
            catalog = _get_catalog(force_refresh=True)
            elapsed = time.time() - t0
            return (
                f"🔄 Cache aplikasi diperbarui dalam {elapsed:.1f}s.\n"
                f"   Total: {len(catalog)} aplikasi ditemukan.\n\n"
                + _format_catalog(catalog, max_items=30)
            )

        # ── launch ──
        elif cmd == "launch":
            if not query:
                return "⚠️ Berikan nama aplikasi untuk dibuka: cmd=launch, query=\"nama_app\""
            catalog = _get_catalog()
            results = _search_apps(catalog, query)
            if not results:
                return f"❌ Aplikasi '{query}' tidak ditemukan di katalog. Coba: cmd=search, query=\"{query}\""
            best = results[0]
            return _launch_entry(best)

        else:
            return (
                f"⚠️ Perintah tidak dikenal: '{cmd}'.\n"
                "Gunakan: cmd=list | search | refresh | launch"
            )

    except Exception as e:
        return f"[installed_apps] Error: {e}"
    finally:
        if _audit_log:
            try:
                _audit_log({"event": "installed_apps", "action": cmd,
                            "target": query or cmd})
            except Exception:
                pass


# ── alias for SkillHub / action_loader discovery ─────────────────────────────
def run(parameters=None, **kwargs):
    """Alias handler agar ter-discover SkillHub & action_loader."""
    return installed_apps(parameters, **kwargs)


TOOL = {
    "name": "installed_apps",
    "description": (
        "[ADMIN] Cari, daftar, dan buka SEMUA aplikasi terinstal di laptop — "
        "tidak terbatas pada daftar alias hardcode. "
        "cmd=list semua aplikasi | search cari nama | refresh perbarui cache | "
        "launch buka aplikasi dari katalog."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {
                "type": "STRING",
                "description": "list | search | refresh | launch",
            },
            "query": {
                "type": "STRING",
                "description": "Nama aplikasi yang dicari atau dibuka (wajib untuk search & launch)",
            },
        },
        "required": ["cmd"],
    },
    "handler": installed_apps,
}
