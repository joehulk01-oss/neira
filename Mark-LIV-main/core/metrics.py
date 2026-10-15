# metrics.py
"""Tahap 4 — Metrik Anti-Bohong: false_success_rate + rekam verifikasi.

Blueprint file.txt §17: metrik terpenting adalah false_success_rate —
berapa persen eksekusi yang MENGAKUI "sukses" padahal FAKTANYA gagal.
Agen PC yang bohong pada dirinya sendiri adalah agen yang berbahaya.

Alur:
  1. record_claim(...)  — saat skill mengklaim sukses
  2. record_verification(aid, verified, method) — saat fakta dicek
     (psutil, awareness, expect-substring, dll.)
  3. false_success_rate() — klaim-sukses-tapi-faktanya-gagal / total terverifikasi

Persisten di memory/metrics.json (atomic save + retry WinError 5 Windows).
"""
from __future__ import annotations

import json
import os
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
METRICS_PATH = BASE_DIR / "memory" / "metrics.json"
_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> dict:
    try:
        with open(METRICS_PATH, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(data: dict) -> None:
    """Atomic save; Windows os.replace bisa kena WinError 5 sesaat → retry."""
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = METRICS_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    last: Exception | None = None
    for attempt in range(5):
        try:
            os.replace(tmp, METRICS_PATH)
            return
        except PermissionError as e:
            last = e
            time.sleep(0.05 * (attempt + 1))
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    raise last if last else RuntimeError("gagal menyimpan metrics.json")


# ── API inti ─────────────────────────────────────────────────────────────────

def record_claim(skill: str, action: str, target: str = "",
                 claim_success: bool = True, result: str = "",
                 correlation_id: str = "") -> str:
    """Catat KLAIM sukses dari sebuah eksekusi. Return attempt_id."""
    aid = f"att-{uuid.uuid4().hex[:10]}"
    with _lock:
        data = _load()
        atts = data.setdefault("attempts", [])
        atts.append({
            "attempt_id": aid,
            "skill": (skill or "?")[:60],
            "action": (action or "")[:60],
            "target": str(target)[:120],
            "claimed_success": bool(claim_success),
            "verified": None,          # None = belum dicek ke realita
            "verify_method": "",
            "result": str(result)[:200],
            "at": _now(),
            "correlation_id": correlation_id or "",
        })
        data["updated_at"] = _now()
        _save(data)
    return aid


def record_verification(attempt_id: str, verified: bool, method: str = "") -> dict:
    """Lengkapi verifikasi fakta atas satu attempt.
    verified=True → realita cocok dengan klaim; False → BOHONG."""
    with _lock:
        data = _load()
        att = next((a for a in data.get("attempts", [])
                    if a.get("attempt_id") == attempt_id), None)
        if att is None:
            return {}
        att["verified"] = bool(verified)
        att["verify_method"] = (method or "")[:80]
        data["updated_at"] = _now()
        _save(data)
        return dict(att)


def false_success_rate() -> float:
    """(klaim sukses tapi faktanya gagal) / (total terverifikasi). 0.0 bila kosong."""
    with _lock:
        atts = list(_load().get("attempts", []))
    verified = [a for a in atts if a.get("verified") is not None]
    if not verified:
        return 0.0
    bad = [a for a in verified
           if a.get("claimed_success") and not a.get("verified")]
    return round(len(bad) / len(verified), 4)


def stats() -> dict:
    with _lock:
        data = _load()
        atts = list(data.get("attempts", []))
    verified = [a for a in atts if a.get("verified") is not None]
    bad = [a for a in verified
           if a.get("claimed_success") and not a.get("verified")]
    by_skill: dict = {}
    for a in atts:
        b = by_skill.setdefault(a.get("skill", "?"),
                                {"attempts": 0, "verified": 0, "false_success": 0})
        b["attempts"] += 1
        if a.get("verified") is not None:
            b["verified"] += 1
            if a.get("claimed_success") and not a.get("verified"):
                b["false_success"] += 1
    return {
        "attempts": len(atts),
        "claimed_success": sum(1 for a in atts if a.get("claimed_success")),
        "verified": len(verified),
        "false_success": len(bad),
        "false_success_rate": false_success_rate(),
        "pending_verification": sum(1 for a in atts if a.get("verified") is None),
        "by_skill": by_skill,
        "updated_at": data.get("updated_at", ""),
    }


def pending(limit: int = 10) -> list:
    """Klaim sukses yang BELUM diverifikasi (target verifikasi berikutnya)."""
    with _lock:
        atts = list(_load().get("attempts", []))
    rows = [a for a in atts if a.get("verified") is None]
    return rows[-limit:]


def recent(limit: int = 10) -> list:
    with _lock:
        atts = list(_load().get("attempts", []))
    return atts[-limit:]


def format_stats() -> str:
    s = stats()
    rate = s["false_success_rate"]
    health = "✅ SEHAT" if rate <= 0.05 else ("⚠️ WASPADA" if rate <= 0.15 else "⛔ KRITIS")
    lines = [
        "📊 METRIK ANTI-BOHONG (blueprint §17)",
        f"Attempt           : {s['attempts']} (klaim sukses {s['claimed_success']})",
        f"Terverifikasi     : {s['verified']} | pending: {s['pending_verification']}",
        f"False success     : {s['false_success']}",
        f"FALSE SUCCESS RATE: {rate * 100:.1f}%  → {health}",
        f"Target blueprint  : ≤ 5% (0.05)",
    ]
    if s["by_skill"]:
        lines.append("Per skill:")
        for name, b in sorted(s["by_skill"].items()):
            lines.append(f"  • {name}: {b['attempts']} attempt, "
                         f"{b['verified']} verif, {b['false_success']} bohong")
    return "\n".join(lines)
