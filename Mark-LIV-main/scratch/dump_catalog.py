"""Dump katalog skill aktif dari skill_hub ke format Markdown.
Dipakai untuk menyusun NEIRA_ANALYSIS.md. Run dari Mark-LIV-main:
python scratch\\dump_catalog.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.skill_hub import skill_hub  # noqa: E402

skill_hub.discover(force_reload=True)
cats = skill_hub.list_by_category()
total = 0
for cat, skills in cats.items():
    print(f"\n### {cat} ({len(skills)} skill)")
    for s in sorted(skills, key=lambda x: x.name.lower()):
        desc = (s.description or "").strip().replace("\n", " ").replace("|", "/")
        print(f"- **`{s.name}`** — {desc[:160]}")
        total += 1
print(f"\nTOTAL AKTIF: {total}")
