"""Focused test: import only the 3 window tools, call handlers directly."""
import importlib.util
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "Mark-LIV-main"
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


print("=== import list_open_windows ===")
low = load(BASE / "actions" / "list_open_windows.py", "t_low")
print(low.list_open_windows({})[:600])

print("\n=== import window_manager ===")
wm = load(BASE / "skills" / "admin" / "window_manager.py", "t_wm")
print(wm.window_manager({"cmd": "list"}))
print(wm.window_manager({"cmd": "active"}))
print(wm.window_manager({"cmd": "focus", "target": "zzz_nosuch"}))

print("\n=== import app_manager ===")
am = load(BASE / "skills" / "admin" / "app_manager.py", "t_am")
print(am.app_manager({"cmd": "list"})[:600])

print("\nALL OK")
