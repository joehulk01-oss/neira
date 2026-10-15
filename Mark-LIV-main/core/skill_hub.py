"""
Universal Shared Skill Hub for Neira, Hermes, and Multi-Brain System.
Enables dynamic discovery, categorization, registration, and execution of skills.
Any skill created by Hermes, Neira, or added from GitHub/external repos is
immediately available to all brains without restarting.
"""

from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _base_dir()
SKILLS_DIR = BASE_DIR / "skills"
PLUGINS_DIR = BASE_DIR / "plugins"

_NAME_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]{0,63}$")
_DEFAULT_PARAMS = {"type": "OBJECT", "properties": {}}


@dataclass
class SkillRecord:
    name: str
    category: str
    description: str = ""
    parameters: dict = field(default_factory=lambda: dict(_DEFAULT_PARAMS))
    handler: Optional[Callable] = None
    file_path: str = ""
    valid: bool = False
    error: str = ""
    source_type: str = "action"  # 'action' (TOOL) or 'plugin' (PLUGIN)
    behavior: Optional[str] = None
    scheduling: Optional[str] = None


class SkillHub:
    """Central registry and dispatch engine for all shared skills."""

    def __init__(self, skills_dir: Optional[Path] = None, logger: Optional[Callable[[str], None]] = None):
        self.skills_dir = skills_dir or SKILLS_DIR
        self._skills: Dict[str, SkillRecord] = {}
        self._all_records: List[SkillRecord] = []
        self._logger = logger or print
        self._last_scan_time: float = 0
        self._last_signature: frozenset = frozenset()
        self.discover()

    def discover(self, force_reload: bool = False) -> None:
        """
        Recursively scans the skills directory and loads all valid skill modules.
        Supports both TOOL dict (Action standard) and PLUGIN dict (Plugin standard).
        """
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        valid: Dict[str, SkillRecord] = {}
        all_records: List[SkillRecord] = []

        # Find all python files recursively in skills/
        py_files = sorted(self.skills_dir.rglob("*.py"), key=lambda p: p.as_posix())

        for path in py_files:
            if path.name.startswith(("_", ".")):
                continue

            # Determine category from parent directory relative to skills_dir
            try:
                rel_parent = path.parent.relative_to(self.skills_dir)
                category = rel_parent.parts[0] if rel_parent.parts else "general"
            except Exception:
                category = "general"

            rec = self._load_single_skill(path, category, force_reload=force_reload)
            all_records.append(rec)
            if rec.valid:
                valid[rec.name] = rec

        # Also optionally scan plugins/ if present
        if PLUGINS_DIR.exists():
            for path in sorted(PLUGINS_DIR.glob("*.py")):
                if path.name.startswith(("_", ".")):
                    continue
                rec = self._load_single_skill(path, category="plugin", force_reload=force_reload)
                all_records.append(rec)
                if rec.valid and rec.name not in valid:
                    valid[rec.name] = rec

        self._skills = valid
        self._all_records = all_records
        self._last_scan_time = time.time()
        self._last_signature = self._tree_signature()
        self._logger(f"[SkillHub] Discovered {len(valid)} active shared skills across all categories.")

    def _tree_signature(self) -> frozenset:
        """(absolute path, mtime_ns) for every skill/plugin file — the change
        detector. Comparing the FULL set catches additions, edits AND deletions:
        a removed file changes the set even though the newest mtime never rises,
        which a max-mtime check would silently miss.
        """
        sig = set()
        for root in (self.skills_dir, PLUGINS_DIR):
            if not root or not root.exists():
                continue
            try:
                for p in root.rglob("*.py"):
                    try:
                        sig.add((str(p), p.stat().st_mtime_ns))
                    except OSError:
                        pass
            except OSError:
                pass
        return frozenset(sig)

    def ensure_fresh(self) -> None:
        """Rescan when any skill file was added, edited or removed since the
        last scan.

        This is the shared skill MEMORY refresh: Neira and Hermes both call
        through the getters below, so any change to the skills tree is visible
        to BOTH brains on their very next call — no restart and no manual reload
        needed. Old and new skills alike.
        """
        try:
            if self._tree_signature() != self._last_signature:
                self.discover(force_reload=True)
        except Exception:
            pass

    def _load_single_skill(self, path: Path, category: str, force_reload: bool = False) -> SkillRecord:
        """Loads and validates a single skill file."""
        module_name = f"skills_dyn_{category}_{path.stem}"
        try:
            if force_reload and module_name in sys.modules:
                del sys.modules[module_name]

            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                return SkillRecord(name=path.stem, category=category, file_path=str(path), error="Cannot build spec")

            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)

            # Check for TOOL dict (Action standard)
            tool_meta = getattr(module, "TOOL", None)
            if isinstance(tool_meta, dict):
                name = tool_meta.get("name") or path.stem
                desc = tool_meta.get("description", "")
                params = tool_meta.get("parameters", _DEFAULT_PARAMS)
                handler = tool_meta.get("handler") or getattr(module, "run", None)
                if callable(handler):
                    return SkillRecord(
                        name=name, category=category, description=desc.strip(),
                        parameters=params, handler=handler, file_path=str(path),
                        valid=True, source_type="action"
                    )

            # Check for PLUGIN dict (Plugin standard)
            plugin_meta = getattr(module, "PLUGIN", None)
            if isinstance(plugin_meta, dict):
                name = plugin_meta.get("name") or path.stem
                desc = plugin_meta.get("description", "")
                params = plugin_meta.get("parameters", _DEFAULT_PARAMS)
                handler = getattr(module, "run", None)
                if callable(handler):
                    return SkillRecord(
                        name=name, category=category, description=desc.strip(),
                        parameters=params, handler=handler, file_path=str(path),
                        valid=True, source_type="plugin"
                    )

            return SkillRecord(name=path.stem, category=category, file_path=str(path),
                               error="No valid TOOL or PLUGIN dict + callable handler found.")
        except Exception as e:
            return SkillRecord(name=path.stem, category=category, file_path=str(path), error=str(e))

    def has(self, name: str) -> bool:
        """Checks if a skill exists in the hub."""
        self.ensure_fresh()
        return name in self._skills

    def get(self, name: str) -> Optional[SkillRecord]:
        """Gets a skill record by name."""
        self.ensure_fresh()
        return self._skills.get(name)

    def list_by_category(self) -> Dict[str, List[SkillRecord]]:
        """Groups active skills by category."""
        self.ensure_fresh()
        grouped: Dict[str, List[SkillRecord]] = {}
        for rec in self._skills.values():
            grouped.setdefault(rec.category, []).append(rec)
        return grouped

    def get_tool_declarations(self) -> List[Dict[str, Any]]:
        """Returns tool declarations for Gemini Live / Neira function calling."""
        self.ensure_fresh()
        decls = []
        for rec in self._skills.values():
            if rec.valid:
                decls.append({
                    "name": rec.name,
                    "description": f"[{rec.category.upper()}] {rec.description}",
                    "parameters": rec.parameters
                })
        return decls

    def get_hermes_catalog(self) -> str:
        """
        Generates a clean, categorized Markdown catalog of all skills
        to be injected into Hermes Agent's system prompt.
        """
        self.ensure_fresh()
        grouped = self.list_by_category()
        lines = ["# SHARED SKILLS CATALOG (shared by every layer of Neira)\n"]
        for cat, skills in sorted(grouped.items()):
            lines.append(f"## Kategori: {cat.upper()}")
            for s in skills:
                props = s.parameters.get("properties", {})
                args_str = ", ".join([f"{k}: {v.get('type', 'any')}" for k, v in props.items()]) if props else "tanpa parameter"
                lines.append(f"- **{s.name}**({args_str})")
                lines.append(f"  *Deskripsi*: {s.description}")
            lines.append("")
        return "\n".join(lines)

    def get_routing_guide(self) -> str:
        """Compact category → skill map injected into BOTH system prompts.

        This is the shared 'memory' of what each skill is FOR: the user asks for
        a kind of work (e.g. "butuh konten"), the brain matches it to a category
        (KONTEN), then calls the best-named skill in that category. Neira and
        Hermes read the same map, so the two brains always agree — old skills and
        newly registered ones alike.
        """
        self.ensure_fresh()
        grouped = self.list_by_category()
        lines = ["[SKILL ROUTING MAP — match the task kind to the category, then pick the skill by name]"]
        for cat, recs in sorted(grouped.items()):
            names = ", ".join(sorted(r.name for r in recs if r.valid))
            if names:
                lines.append(f"- {cat.upper()}: {names}")
        lines.append(
            "Routing rule: KONTEN = content creation & research (video, search, "
            "social, images, weather, YouTube); ADMIN = system, browser, device & "
            "app control; DEV = code, files, automation, deep reasoning; ASISTEN = "
            "personal assistant (reminders, messages, flights, proactive); CUSTOM / "
            "GENERAL / PLUGIN = everything else. Match the user's request to the "
            "category FIRST, then call the skill whose name fits best. Both brains "
            "share this one library — a skill registered anywhere at any time is "
            "visible here."
        )
        return "\n".join(lines)

    def run(self, name: str, parameters: Dict[str, Any], player: Any = None,
            speak: Any = None, response: Any = None, session_memory: Any = None) -> Any:
        """
        Executes any skill seamlessly with signature introspection and safety.
        Works identically whether called by Neira or Hermes.
        """
        rec = self._skills.get(name)
        if not rec or not rec.valid or not rec.handler:
            # Auto-rescan once in case a new skill was recently written
            self.discover()
            rec = self._skills.get(name)
            if not rec or not rec.valid or not rec.handler:
                return f"[SkillHub] Skill '{name}' tidak ditemukan atau tidak aktif."

        try:
            handler = rec.handler
            sig = inspect.signature(handler)
            kwargs = {}
            has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())

            # Pass parameters as first arg or kwargs depending on handler signature
            first_param_name = list(sig.parameters.keys())[0] if sig.parameters else None

            # Prepare context kwargs
            ctx_map = {
                "player": player,
                "speak": speak,
                "response": response,
                "session_memory": session_memory
            }
            for k, v in ctx_map.items():
                if has_var_kw or k in sig.parameters:
                    kwargs[k] = v

            if first_param_name in ("parameters", "params", "args"):
                result = handler(parameters, **kwargs)
            elif first_param_name in parameters and len(sig.parameters) > 1:
                # Direct kwargs handler
                call_args = {k: v for k, v in parameters.items() if k in sig.parameters or has_var_kw}
                call_args.update(kwargs)
                result = handler(**call_args)
            else:
                result = handler(parameters, **kwargs)

            # Log to UI if available
            if player and hasattr(player, "write_log"):
                try:
                    player.write_log(f"[Skill:{name}] Selesai dijalankan.")
                except Exception:
                    pass

            return result
        except Exception as e:
            traceback.print_exc()
            return f"[SkillHub Error] Eksekusi '{name}' gagal: {e}"

    def register_new_skill(self, name: str, code: str, category: str = "custom") -> Dict[str, Any]:
        """
        Allows Hermes or any external brain to programmatically write and register
        a new skill into skills/<category>/<name>.py with immediate availability.
        """
        target_dir = self.skills_dir / category
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{name}.py"

        file_path.write_text(code, encoding="utf-8")
        self._logger(f"[SkillHub] New skill written: {file_path}")

        # Hot reload single skill
        rec = self._load_single_skill(file_path, category=category, force_reload=True)
        if rec.valid:
            self._skills[rec.name] = rec
            return {"success": True, "name": rec.name, "category": category, "file": str(file_path)}
        else:
            return {"success": False, "name": name, "error": rec.error, "file": str(file_path)}


# Global Singleton Hub
skill_hub = SkillHub()
