"""Test hermes_executor.open_app focus-first behavior."""
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent / "Mark-LIV-main"
sys.path.insert(0, str(BASE))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from core.hermes_executor import open_app  # noqa: E402

print("=== open_app('Chrome') — Chrome jalan, harus fokus ===")
print(open_app("Chrome"))

print("\n=== open_app('notepad') — cek jalur alias/launcher ===")
print(open_app("zzz_nosuch_app_xyz"))
print("\nDONE")
