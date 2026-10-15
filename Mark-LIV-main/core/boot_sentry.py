"""
BOOT SENTRY — penjaga boot anti-brick untuk Neira.

Adopsi pola Brahma-Echo (core/boot_sentry.py): kalau sesi sebelumnya CRASH tepat
setelah patch kode diterapkan, file yang di-patch otomatis dikembalikan dari
backup (.bak) saat startup — SEBELUM UI/API dimuat — supaya Neira tidak
"brick" karena patch yang rusak.

Cara kerja:
  1. Saat runtime terjadi exception fatal, tulis `FATAL_CRASH.log`
     (helper `mark_crash()` — dipanggil dari `main()` saat `KeyboardInterrupt`
     TIDAK menyentuhnya; hanya crash tak terduga yang ditandai).
  2. Setiap patch yang diterapkan lewat `core.hermes_remediator.apply_patch_safely()`
     mencatat diri ke `shared/memory/patch_history.json` (patch_id, target_file,
     backup_path, status).
  3. `check_and_recover_on_boot()` dijalankan OTOMATIS saat import: kalau ada
     crash log dan patch terakhir berstatus "applied" → restore dari .bak,
     tandai "rolled_back_on_boot", arsipkan crash log.

Dipanggil otomatis oleh `import core.boot_sentry` di awal `main.py`.
"""
from __future__ import annotations

import json
import shutil
import sys
import time
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


BASE_DIR = _base_dir()
SHARED_MEM_DIR = BASE_DIR / "shared" / "memory"
SHARED_MEM_DIR.mkdir(parents=True, exist_ok=True)

CRASH_LOG = BASE_DIR / "FATAL_CRASH.log"
CRASH_ARCHIVE = BASE_DIR / "FATAL_CRASH_RECOVERED.log"
PATCH_HISTORY_FILE = SHARED_MEM_DIR / "patch_history.json"

# Patch yang lebih tua dari ini saat crash dianggap tidak berhubungan (detik).
CRASH_PATCH_WINDOW = 300.0


def mark_crash(tb_text: str) -> None:
    """Tandai crash fatal runtime (dipanggil dari handler exception global)."""
    try:
        CRASH_LOG.write_text(
            f"crash_at: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n{tb_text}",
            encoding="utf-8",
        )
    except Exception:
        pass


def clear_crash() -> None:
    """Hapus penanda crash (mis. setelah startup sukses penuh)."""
    try:
        if CRASH_LOG.exists():
            CRASH_LOG.unlink()
    except Exception:
        pass


def load_patch_history() -> List[Dict[str, Any]]:
    try:
        if PATCH_HISTORY_FILE.exists():
            data = json.loads(PATCH_HISTORY_FILE.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        pass
    return []


def save_patch_history(history: List[Dict[str, Any]]) -> None:
    try:
        PATCH_HISTORY_FILE.write_text(
            json.dumps(history, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        print(f"[BootSentry] gagal simpan riwayat patch: {e}")


def record_patch(patch_id: str, target_file: Path, backup_path: Path) -> None:
    """Catat patch yang baru diterapkan (dipanggil `apply_patch_safely()`)."""
    history = load_patch_history()
    history.append({
        "patch_id": patch_id,
        "target_file": str(target_file),
        "backup_path": str(backup_path),
        "status": "applied",
        "applied_at": time.time(),
    })
    save_patch_history(history)


def check_and_recover_on_boot() -> bool:
    """Cek crash-setelah-patch; kalau ya, rollback otomatis dari .bak.

    Mengembalikan True kalau pemulihan (rollback) dilakukan.
    """
    if not CRASH_LOG.exists() or not PATCH_HISTORY_FILE.exists():
        return False

    history = load_patch_history()
    if not history:
        return False

    last_patch = history[-1]
    if last_patch.get("status") != "applied" or not last_patch.get("backup_path"):
        return False

    # Patch yang sudah lama (> 5 menit sebelum crash) tidak dianggap penyebab.
    applied_at = float(last_patch.get("applied_at", 0) or 0)
    if applied_at and (time.time() - applied_at) > 3600:
        return False

    target_file = Path(last_patch.get("target_file", ""))
    backup_file = Path(last_patch.get("backup_path", ""))
    if not backup_file.exists() or not target_file.exists():
        return False

    print(f"[BootSentry] ⚠️ Crash fatal terdeteksi setelah patch '{last_patch.get('patch_id')}'.")
    print(f"[BootSentry] 🛡️ Mengembalikan '{target_file.name}' dari backup...")
    try:
        shutil.copy2(backup_file, target_file)
        last_patch["status"] = "rolled_back_on_boot"
        last_patch["rollback_reason"] = "Aplikasi crash saat startup setelah patch."
        save_patch_history(history)
        if CRASH_LOG.exists():
            shutil.move(str(CRASH_LOG), str(CRASH_ARCHIVE))
        print(f"[BootSentry] ✅ '{target_file.name}' dipulihkan — Neira terselamatkan.")
        return True
    except Exception as e:
        print(f"[BootSentry] ❌ Pemulihan gagal: {e}")
        return False


# Jalankan pemeriksaan pemulihan OTOMATIS saat import (sebelum UI/API hidup).
check_and_recover_on_boot()
