# job_manager.py
"""
job_manager.py — Lifecycle task multi-langkah Neira (Blueprint Tahap 2, §4.9).

Status job (persis blueprint):
    queued → planning → waiting_confirmation → running → paused → retrying
        → succeeded | failed | cancelled | reconciliation_required

Setiap job punya: job_id, goal, steps (skill+params+status per langkah),
retry_count, risk_level, correlation_id. Persisten di memory/jobs.json
(atomic write: tulis tmp lalu replace). Anti double-run: goal yang sama
yang masih queued/running TIDAK dibuat dua kali — job lama dikembalikan.

Pemakaian:
    from core.job_manager import create_job, get_job, set_status, update_step
    job = create_job("siapkan meeting", steps=[{"skill": "open_app", "params": {...}}])
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _base_dir() -> Path:
    try:
        from core.paths import BASE_DIR  # type: ignore
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
JOBS_PATH = BASE_DIR / "memory" / "jobs.json"

# Status lifecycle
QUEUED = "queued"
PLANNING = "planning"
WAITING_CONFIRMATION = "waiting_confirmation"
RUNNING = "running"
PAUSED = "paused"
RETRYING = "retrying"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"
RECONCILIATION = "reconciliation_required"

ACTIVE_STATUSES = {QUEUED, PLANNING, WAITING_CONFIRMATION, RUNNING, PAUSED, RETRYING}

_lock = threading.RLock()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _load() -> list[dict]:
    try:
        with open(JOBS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(jobs: list[dict]) -> None:
    """Simpan atomik (tmp + replace). Di Windows os.replace bisa kena
    WinError 5 sesaat (antivirus/indexer memegang file target) → retry
    dengan backoff pendek sebelum menyerah."""
    JOBS_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = JOBS_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(jobs, f, ensure_ascii=False, indent=1)
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            os.replace(tmp, JOBS_PATH)
            return
        except PermissionError as e:
            last_err = e
            time.sleep(0.05 * (attempt + 1))  # 50ms → 250ms
    try:
        tmp.unlink(missing_ok=True)
    except Exception:
        pass
    raise last_err if last_err else RuntimeError("gagal menyimpan jobs.json")


def _mutate(job_id: str, fn) -> dict | None:
    """Ubah satu job secara aman (load → fn(job) → atomic save)."""
    with _lock:
        jobs = _load()
        job = next((j for j in jobs if j.get("job_id") == job_id), None)
        if job is None:
            return None
        fn(job)
        _save(jobs)
        return job


def create_job(goal: str, steps: list[dict], risk_level: str = "low",
               correlation_id: str = "", meta: dict | None = None) -> tuple[dict, bool]:
    """Buat job baru. Return (job, created). Jika goal sama masih aktif →
    (job lama, False) — mencegah eksekusi ganda."""
    goal = (goal or "").strip()
    with _lock:
        jobs = _load()
        for j in jobs:
            if j.get("goal", "").lower() == goal.lower() and j.get("status") in ACTIVE_STATUSES:
                return j, False
        job = {
            "job_id": f"job-{time.strftime('%Y%m')}-{uuid.uuid4().hex[:8]}",
            "goal": goal,
            "intent": (meta or {}).get("intent", ""),
            "status": QUEUED,
            "steps": [
                {
                    "name":    s.get("name") or s.get("skill", f"step-{i+1}"),
                    "skill":   s.get("skill", ""),
                    "params":  s.get("params") or {},
                    "policy_action": s.get("policy_action", ""),
                    "expect":  s.get("expect", ""),
                    "status":  "pending",
                    "result":  "",
                }
                for i, s in enumerate(steps or [])
            ],
            "current_step": 0,
            "total_steps": len(steps or []),
            "retry_count": 0,
            "risk_level": risk_level,
            "correlation_id": correlation_id or f"corr-{uuid.uuid4().hex[:10]}",
            "created_at": _now(),
            "started_at": "",
            "ended_at": "",
            "result_summary": "",
        }
        jobs.append(job)
        _save(jobs)
        return job, True


def get_job(job_id: str) -> dict | None:
    with _lock:
        return next((j for j in _load() if j.get("job_id") == job_id), None)


def find_active_by_goal(goal: str) -> dict | None:
    goal = (goal or "").strip().lower()
    with _lock:
        return next((j for j in _load()
                     if j.get("goal", "").lower() == goal
                     and j.get("status") in ACTIVE_STATUSES), None)


def set_status(job_id: str, status: str, summary: str = "") -> dict | None:
    def _fn(job: dict) -> None:
        job["status"] = status
        if status == RUNNING and not job.get("started_at"):
            job["started_at"] = _now()
        if status in (SUCCEEDED, FAILED, CANCELLED, RECONCILIATION):
            job["ended_at"] = _now()
        if summary:
            job["result_summary"] = summary
    return _mutate(job_id, _fn)


def update_step(job_id: str, idx: int, status: str, result: str = "") -> dict | None:
    def _fn(job: dict) -> None:
        steps = job.get("steps", [])
        if 0 <= idx < len(steps):
            steps[idx]["status"] = status
            steps[idx]["result"] = str(result)[:400]
            job["current_step"] = idx + 1 if status == "done" else idx
    return _mutate(job_id, _fn)


def set_waiting_step(job_id: str, idx: int) -> dict | None:
    """Tandai job menunggu konfirmasi DI langkah ke-idx (di-restart dari sini)."""
    def _fn(job: dict) -> None:
        job["status"] = WAITING_CONFIRMATION
        job["current_step"] = idx
    return _mutate(job_id, _fn)


def cancel(job_id: str, reason: str = "") -> dict | None:
    def _fn(job: dict) -> None:
        job["status"] = CANCELLED
        job["ended_at"] = _now()
        if reason:
            job["result_summary"] = f"cancelled: {reason}"
    return _mutate(job_id, _fn)


def list_jobs(limit: int = 10) -> list[dict]:
    return _load()[-limit:][::-1]          # terbaru dulu


def fmt_job(job: dict) -> str:
    icon = {"succeeded": "✅", "failed": "❌", "cancelled": "🚫",
            "running": "🏃", "waiting_confirmation": "⏸️",
            "queued": "⏳", "paused": "⏸️"}.get(job.get("status", ""), "•")
    lines = [f"{icon} {job['job_id']} — {job['goal']} [{job['status']}] "
             f"({job.get('current_step', 0)}/{job.get('total_steps', 0)} langkah)"]
    for i, s in enumerate(job.get("steps", [])):
        mark = {"done": "✅", "denied": "⛔", "failed": "❌", "running": "🏃",
                "waiting": "⏸️", "pending": "○", "cancelled": "🚫"}.get(s["status"], "•")
        lines.append(f"   {mark} {i+1}. {s['name']} ({s['skill']})"
                     + (f" — {s['result'][:120]}" if s.get("result") else ""))
    if job.get("result_summary"):
        lines.append(f"   ➜ {job['result_summary']}")
    return "\n".join(lines)
