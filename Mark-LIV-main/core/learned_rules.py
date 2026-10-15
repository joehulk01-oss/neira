"""
LEARNED RULES — mesin aturan perilaku yang dipelajari dari user.

Adopsi pola Brahma-Echo (core/learned_rules.py): koreksi/preferensi/habit user
disimpan permanen di `shared/memory/learned_rules.json`, lalu DIINJEKSI ke
system prompt saat runtime — Neira berubah perilaku TANPA mengedit kode.

Pemakaian:
    from core.learned_rules import learned_rules
    learned_rules.add_rule("jawab selalu singkat dan to the point", category="habit")
    ...
    injections = learned_rules.get_prompt_injections()   # ditambahkan ke prompt

Aturan bisa dimatikan (`toggle_rule`) atau dihapus (`delete_rule`) per id.
"""
from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

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


SHARED_MEM_DIR = _base_dir() / "shared" / "memory"
SHARED_MEM_DIR.mkdir(parents=True, exist_ok=True)
RULES_FILE = SHARED_MEM_DIR / "learned_rules.json"


class LearnedRulesEngine:
    """Penyimpanan aturan perilaku hasil belajar dari user."""

    # ---- penyimpanan ------------------------------------------------------ #
    @staticmethod
    def _load_raw() -> List[Dict[str, Any]]:
        if not RULES_FILE.exists():
            return []
        try:
            data = json.loads(RULES_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception as e:
            print(f"[LearnedRules] gagal baca aturan: {e}")
            return []

    @staticmethod
    def _save_raw(rules: List[Dict[str, Any]]) -> bool:
        try:
            RULES_FILE.write_text(
                json.dumps(rules, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            return True
        except Exception as e:
            print(f"[LearnedRules] gagal simpan aturan: {e}")
            return False

    # ---- operasi ---------------------------------------------------------- #
    @classmethod
    def add_rule(
        cls,
        rule_text: str,
        category: str = "general",
        origin: str = "user_correction",
    ) -> Dict[str, Any]:
        """Tambah aturan baru (dedup otomatis — aturan ganda diaktifkan ulang)."""
        clean_text = (rule_text or "").strip()
        if not clean_text:
            return {"success": False, "message": "Teks aturan kosong."}

        rules = cls._load_raw()
        for r in rules:
            if r.get("rule", "").lower() == clean_text.lower():
                r["active"] = True
                r["updated_at"] = time.time()
                cls._save_raw(rules)
                return {"success": True, "rule": r, "message": "Aturan sudah ada dan aktif."}

        new_rule = {
            "id": uuid.uuid4().hex[:8],
            "rule": clean_text,
            "category": category,
            "origin": origin,
            "active": True,
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        rules.append(new_rule)
        cls._save_raw(rules)
        return {"success": True, "rule": new_rule, "message": f"Aturan baru dipelajari: '{clean_text}'"}

    @classmethod
    def list_rules(cls, active_only: bool = False) -> List[Dict[str, Any]]:
        rules = cls._load_raw()
        if active_only:
            return [r for r in rules if r.get("active", True)]
        return rules

    @classmethod
    def toggle_rule(cls, rule_id: str) -> Dict[str, Any]:
        rules = cls._load_raw()
        for r in rules:
            if r.get("id") == rule_id:
                r["active"] = not r.get("active", True)
                r["updated_at"] = time.time()
                cls._save_raw(rules)
                status = "diaktifkan" if r.get("active", True) else "dinonaktifkan"
                return {"success": True, "message": f"Aturan {rule_id} {status}."}
        return {"success": False, "message": f"Aturan '{rule_id}' tidak ditemukan."}

    @classmethod
    def delete_rule(cls, rule_id: str) -> Dict[str, Any]:
        rules = cls._load_raw()
        before = len(rules)
        rules = [r for r in rules if r.get("id") != rule_id]
        if len(rules) < before:
            cls._save_raw(rules)
            return {"success": True, "message": f"Aturan {rule_id} dihapus."}
        return {"success": False, "message": f"Aturan '{rule_id}' tidak ditemukan."}

    # ---- injeksi prompt --------------------------------------------------- #
    @classmethod
    def get_prompt_injections(cls) -> str:
        """Format semua aturan aktif untuk disuntikkan ke system prompt runtime."""
        active = [
            r.get("rule", "").strip()
            for r in cls.list_rules(active_only=True)
            if r.get("rule")
        ]
        if not active:
            return ""
        lines = ["\nPREFERENSI USER & ATURAN PERILAKU YANG DIPELAJARI:"]
        for i, rule in enumerate(active, 1):
            lines.append(f"{i}. {rule}")
        return "\n".join(lines) + "\n"


# Global instance
learned_rules = LearnedRulesEngine()
