"""
Skill Manager for Neira.
Allows checking available skills, categorizing them, and reloading the skill registry on the fly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

def manage_skills(action: str = "list", category: str = "", query: str = "") -> str:
    """
    Manages and inspects the assistant's active skills.
    action: 'list' (list all skills), 'reload' (refresh catalog from disk), 'info' (details of a skill).
    category: optional filter ('admin', 'konten', 'dev', 'asisten', 'custom').
    query: search keyword or specific skill name.
    """
    try:
        from core.skill_hub import skill_hub
    except Exception as e:
        return f"Gagal mengakses SkillHub: {e}"

    action_clean = (action or "list").strip().lower()

    if action_clean in ("reload", "refresh", "scan"):
        skill_hub.discover(force_reload=True)
        total = len(skill_hub._skills)
        return f"Katalog skill berhasil dimuat ulang dari disk. Total {total} skill aktif siap digunakan."

    if action_clean in ("info", "detail"):
        target_name = (query or category).strip().lower()
        rec = skill_hub.get(target_name)
        if not rec:
            return f"Skill '{target_name}' tidak ditemukan di sistem."
        props = rec.parameters.get("properties", {})
        props_str = ", ".join(props.keys()) if props else "tanpa parameter"
        return (
            f"Informasi Skill '{rec.name}':\n"
            f"- Kategori: {rec.category.upper()}\n"
            f"- Deskripsi: {rec.description}\n"
            f"- Parameter: {props_str}\n"
            f"- File: {rec.file_path}"
        )

    # Default: list skills grouped by category
    grouped = skill_hub.list_by_category()
    lines = ["Daftar Skill Aktif Asisten:"]
    target_cat = category.strip().lower()

    for cat, skills in sorted(grouped.items()):
        if target_cat and cat.lower() != target_cat:
            continue
        skill_names = [s.name for s in skills if s.valid]
        lines.append(f"• [{cat.upper()}] ({len(skill_names)}): {', '.join(skill_names)}")

    total_active = len(skill_hub._skills)
    lines.append(f"\nTotal: {total_active} skill aktif. Kamu bisa minta saya menjalankan skill di atas.")
    return "\n".join(lines)


TOOL = {
    "name": "manage_skills",
    "description": (
        "Inspects, lists, or reloads available skills and tools installed in the system. "
        "Use this whenever the user asks what capabilities, tools, or skills you have, "
        "or asks to refresh the skills catalog after adding new files."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform: 'list' (show all skills), 'reload' (refresh from disk), or 'info' (detail of a skill).",
            },
            "category": {
                "type": "STRING",
                "description": "Optional category filter: 'admin', 'konten', 'dev', 'asisten', 'custom'.",
            },
            "query": {
                "type": "STRING",
                "description": "Specific skill name or keyword if action='info'.",
            },
        },
        "required": [],
    },
    "handler": manage_skills,
}
