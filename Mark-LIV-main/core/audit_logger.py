# audit_logger.py
"""
audit_logger.py — Jejak audit JSONL untuk Neira (Blueprint Tahap 1).

Blueprint: "setiap aksi mencatat timestamp, actor, brain, skill, target,
risk_level, decision, result, verification, duration_ms". File:

    audit/events.jsonl   — satu event per baris (JSON Lines, append-only)

Append-only + threading.Lock + atomic-ish (satu write per baris). Tidak pernah
melempar exception ke pemanggil — audit gagal TIDAK boleh membuat aksi gagal,
tapi kegagalan audit dicetak ke stderr agar terlihat.

Pemakaian:
    from core.audit_logger import log_event, log_command
    log_command(skill="app_manager", target="chrome", decision="allow",
                risk="medium", result="closed", duration_ms=820)
"""
from __future__ import annotations

import json
import sys
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path


def _base_dir() -> Path:
    try:
        from core.paths import BASE_DIR  # type: ignore
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
AUDIT_DIR = BASE_DIR / "audit"
EVENTS_PATH = AUDIT_DIR / "events.jsonl"

_lock = threading.Lock()


def new_correlation_id() -> str:
    """ID rantai untuk satu permintaan user (bisa merangkai banyak skill call)."""
    return f"corr-{uuid.uuid4().hex[:10]}"


def log_event(event: dict) -> bool:
    """Append satu event ke audit/events.jsonl. Return True jika berhasil."""
    try:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "correlation_id": event.get("correlation_id", ""),
            "actor": event.get("actor", "model"),
            "brain": event.get("brain", ""),
            "skill": event.get("skill", ""),
            "action": event.get("action", ""),
            "target": event.get("target", ""),
            "risk_level": event.get("risk_level", ""),
            "decision": event.get("decision", ""),
            "result": event.get("result", ""),
            "verification": event.get("verification", ""),
            "duration_ms": event.get("duration_ms"),
            "note": event.get("note", ""),
        }
        record = {k: v for k, v in record.items() if v not in ("", None)}
        line = json.dumps(record, ensure_ascii=False)
        with _lock:
            AUDIT_DIR.mkdir(parents=True, exist_ok=True)
            with open(EVENTS_PATH, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return True
    except Exception as e:
        print(f"[audit_logger] GAGAL mencatat event: {e}", file=sys.stderr)
        return False


def log_command(skill: str, action: str = "", target: str = "",
                decision: str = "", risk_level: str = "", result: str = "",
                duration_ms: int | None = None, brain: str = "",
                correlation_id: str = "", actor: str = "model",
                note: str = "") -> bool:
    """Helper khusus aksi skill/OS — field paling umum, sisanya default."""
    return log_event({
        "skill": skill, "action": action, "target": target,
        "decision": decision, "risk_level": risk_level, "result": result,
        "duration_ms": duration_ms, "brain": brain,
        "correlation_id": correlation_id, "actor": actor, "note": note,
    })


class Timer:
    """context manager pengukur durasi untuk duration_ms."""

    def __init__(self) -> None:
        self.t0 = time.perf_counter()
        self.ms = 0

    def __enter__(self) -> "Timer":
        self.t0 = time.perf_counter()
        return self

    def __exit__(self, *_exc) -> None:
        self.ms = int((time.perf_counter() - self.t0) * 1000)


def tail(n: int = 20) -> list[dict]:
    """Baca n event terakhir (untuk manage_skills / debug)."""
    try:
        with open(EVENTS_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [json.loads(l) for l in lines if l.strip()]
    except OSError:
        return []
