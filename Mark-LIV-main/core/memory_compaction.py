# memory_compaction.py
"""Tahap 5 — Memory Compaction (blueprint §13): long-term memory tidak boleh
membengkak tanpa kontrol, tapi JUGA tidak boleh menghapus tanpa jejak.

Prinsip anti-bohong:
  - ANALYZE  read-only  → fakta ukuran & duplikat
  - COMPACT  selalu backup long_term.json dulu, lalu:
      dedupe  : duplikat exact-value dalam satu kategori digabung (nilai terbaru menang)
      archive : entri tua dipindah ke memory/archive.json (BUKAN dihapus)
  - Tidak menyentuh kategori non-dict (mis. 'sessions' dikelola memory_manager).

Fungsi transformasi PURE (dedupe_memory, archive_old) → mudah dites tanpa
menyentuh memory asli user.
"""
from __future__ import annotations

import json
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _base_dir() -> Path:
    try:
        from core.paths import BASE_DIR  # type: ignore
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
MEMORY_PATH = BASE_DIR / "memory" / "long_term.json"
ARCHIVE_PATH = BASE_DIR / "memory" / "archive.json"
_lock = threading.RLock()


def _entry_value(entry) -> str:
    """Nilai teks dari entri (entry bisa dict {value, updated} atau string)."""
    if isinstance(entry, dict):
        v = entry.get("value", "")
        return v if isinstance(v, str) else json.dumps(v, ensure_ascii=False)
    return str(entry)


def _entry_updated(entry) -> str:
    if isinstance(entry, dict):
        u = entry.get("updated", "")
        return u if isinstance(u, str) else ""
    return ""


def _iter_categories(memory: dict):
    """Yield (cat, dict-entries) hanya untuk kategori berbentuk dict."""
    for cat, val in (memory or {}).items():
        if isinstance(val, dict) and val and all(isinstance(k, str) for k in val):
            yield cat, val


def find_duplicates(memory: dict) -> list:
    """Kelompok kunci dalam satu kategori yang nilainya SAMA persis."""
    groups = []
    for cat, entries in _iter_categories(memory):
        by_val: dict = {}
        for key, entry in entries.items():
            by_val.setdefault(_entry_value(entry).strip().lower(), []).append(key)
        for val, keys in by_val.items():
            if len(keys) > 1:
                groups.append({"category": cat, "keys": keys, "value": val[:60]})
    return groups


def dedupe_memory(memory: dict) -> tuple:
    """Gabung duplikat: pertahankan kunci dengan 'updated' terbaru.
    Return (memory_baru, kunci_yang_digabung)."""
    merged = []
    for cat, entries in list(_iter_categories(memory)):
        groups: dict = {}
        for key, entry in entries.items():
            groups.setdefault(_entry_value(entry).strip().lower(), []).append(key)
        for _val, keys in groups.items():
            if len(keys) < 2:
                continue
            keys.sort(key=lambda k: _entry_updated(entries.get(k, "")))
            keep = keys[-1]
            for k in keys[:-1]:
                del memory[cat][k]
                merged.append(f"{cat}/{k} → {keep}")
    return memory, merged


def archive_old(memory: dict, max_age_days: int = 90) -> tuple:
    """Pindahkan entri dengan 'updated' lebih tua dari max_age_days ke arsip.
    Entri tanpa tanggal TIDAK disentuh (aman by default).
    Return (memory_baru, list_arsip)."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=max_age_days)) \
        .strftime("%Y-%m-%dT%H:%M")
    archived = []
    for cat, entries in list(_iter_categories(memory)):
        for key in list(entries.keys()):
            entry = entries.get(key)
            upd = _entry_updated(entry)
            if not upd or upd[:16] >= cutoff:
                continue
            archived.append({
                "category": cat, "key": key,
                "entry": entry, "archived_at": datetime.now(timezone.utc)
                    .isoformat(timespec="seconds"),
            })
            del memory[cat][key]
    return memory, archived


def backup_memory() -> str:
    """Salin long_term.json → long_term.backup-<stamp>.json. Return path."""
    if not MEMORY_PATH.exists():
        return ""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dst = MEMORY_PATH.with_name(f"long_term.backup-{stamp}.json")
    shutil.copy2(MEMORY_PATH, dst)
    return str(dst)


def analyze(memory: dict | None = None) -> dict:
    """Fakta kesehatan memory (read-only)."""
    if memory is None:
        try:
            from memory.memory_manager import load_memory
            memory = load_memory()
        except Exception:
            memory = {}
    n_entries = sum(len(v) for _c, v in _iter_categories(memory))
    size = len(json.dumps(memory, ensure_ascii=False))
    dups = find_duplicates(memory)
    oldest = ""
    for _cat, entries in _iter_categories(memory):
        for e in entries.values():
            u = _entry_updated(e)
            if u and (not oldest or u < oldest):
                oldest = u
    arch_n = 0
    try:
        if ARCHIVE_PATH.exists():
            with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
                arch_n = len(json.load(f))
    except Exception:
        arch_n = -1
    return {"size_chars": size, "categories": len(list(_iter_categories(memory))),
            "entries": n_entries, "dup_groups": len(dups),
            "dup_sample": dups[:5], "oldest_updated": oldest,
            "archived_entries": arch_n}


def compact(dry_run: bool = True, max_age_days: int = 90) -> str:
    """Kompaksi penuh. dry_run=True → hanya rencana, TANPA menulis apa pun."""
    try:
        from memory.memory_manager import load_memory, save_memory
    except Exception as e:
        return f"❌ memory_manager tidak tersedia: {e}"
    memory = load_memory()
    before = len(json.dumps(memory, ensure_ascii=False))
    memory, merged = dedupe_memory(memory)
    memory, archived = archive_old(memory, max_age_days)
    after = len(json.dumps(memory, ensure_ascii=False))
    lines = [f"🧹 RENCANA KOMPAKSI (dry_run={dry_run})",
             f"Ukuran : {before:,} → {after:,} karakter (hemat {before - after:,})",
             f"Dedup  : {len(merged)} entri digabung",
             f"Arsip  : {len(archived)} entri tua (>{max_age_days} hari)"]
    for m in merged[:5]:
        lines.append(f"  ⛓ {m}")
    if not dry_run and (merged or archived):
        bak = backup_memory()
        save_memory(memory)
        if archived:
            old = []
            try:
                if ARCHIVE_PATH.exists():
                    with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
                        old = json.load(f)
            except Exception:
                old = []
            with _lock:
                ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
                ARCHIVE_PATH.write_text(
                    json.dumps(old + archived, indent=1, ensure_ascii=False),
                    encoding="utf-8")
        lines.append(f"✅ Kompaksi diterapkan. Backup: {bak or '(memory kosong)'}")
    elif not dry_run:
        lines.append("✅ Tidak ada yang perlu diubah — memory sudah ramping.")
    return "\n".join(lines)
