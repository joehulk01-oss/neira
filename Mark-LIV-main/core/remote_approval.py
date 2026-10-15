# remote_approval.py — Blueprint Tahap 14
"""
Remote Approval via HP (blueprint §12 — approval loop dari ponsel).

Alur:
    job WAITING_CONFIRMATION (orchestrator) → register() → main loop mendorong
    notifikasi ke HP (notifications_new + mark_notified) → user balas
    "setujui job-xxx" / "tolak job-xxx" dari HP → _process_dashboard_commands
    menangkap teks itu (try_handle_text) → resolve():
        approve → orchestrator.run(job_id=..., confirm=True)   (SATU pintu)
        deny    → job_manager.cancel()

Aturan blueprint yang dijaga:
    - TIDAK ada shortcut eksekusi: approve HANYA meneruskan confirm=True ke
      job yang memang sedang menunggu; langkah tetap lewat orchestrator.
    - Keputusan dicatat audit (approval.request / approval.decision).
    - Jujur (anti-bohong): id tak dikenal, job tidak lagi waiting, sudah
      diputuskan, atau orchestrator gagal → pesan error eksplisit, TANPA
      klaim sukses palsu.
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path

try:
    from core.audit_logger import log_event as _audit
except Exception:
    _audit = None
try:
    from core import job_manager as _jm
except Exception:
    _jm = None
try:
    from core import jarvis_orchestrator as _orch
except Exception:
    _orch = None


def _base_dir() -> Path:
    try:
        from core.paths import BASE_DIR  # type: ignore
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
APPROVAL_PATH = BASE_DIR / "memory" / "approvals.json"
TTL_HOURS = 48                      # permintaan tanpa keputusan → expired

_lock = threading.RLock()
_AID = re.compile(r"job-\d{6}-[0-9a-fA-F]{6,12}")
_RE_APPROVE = re.compile(r"^(setujui|setuju|approve|acc)\s*(job-\S+)?\s*$")
_RE_DENY = re.compile(r"^(tolak|deny|reject|batalkan|batal)\s*(job-\S+)?\s*$")
_RE_LIST = re.compile(r"^(approval|persetujuan)(\s+list)?\s*$")


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _load() -> list[dict]:
    try:
        with open(APPROVAL_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception:
        return []


def _save(rows: list[dict]) -> None:
    """Atomic save (tmp + replace) dengan retry — Windows os.replace bisa
    kena WinError 5 sesaat (antivirus/indexer memegang file target)."""
    APPROVAL_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = APPROVAL_PATH.with_suffix(".tmp")
    last: Exception | None = None
    for _ in range(3):
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(rows, f, ensure_ascii=False, indent=1)
            os.replace(tmp, APPROVAL_PATH)
            return
        except Exception as e:                       # pragma: no cover - retry path
            last = e
            time.sleep(0.05)
    if last:
        raise last


def _age_minutes(created_at: str) -> int:
    try:
        t0 = time.mktime(time.strptime(created_at, "%Y-%m-%dT%H:%M:%S"))
        return int(max(0, time.time() - t0) // 60)
    except Exception:
        return 0


def _age_str(created_at: str) -> str:
    m = _age_minutes(created_at)
    return f"{m // 60}j{m % 60}m" if m >= 60 else f"{m}m"


# ── Register ────────────────────────────────────────────────────────────────

def register(job_id: str, source: str = "manual") -> tuple[dict | None, str]:
    """Daftarkan job yang WAITING_CONFIRMATION sebagai permintaan approval.
    Return (approval, error)."""
    if _jm is None:
        return None, "remote_approval: job_manager tidak tersedia"
    jid = str(job_id or "").strip()
    if not jid:
        return None, "job_id kosong."
    job = _jm.get_job(jid)
    if job is None:
        return None, f"Job '{jid}' tidak ditemukan."
    if job.get("status") != _jm.WAITING_CONFIRMATION:
        return None, (f"Job '{jid}' status '{job.get('status')}' — "
                      f"bukan menunggu konfirmasi, tidak ada yang perlu "
                      f"disetujui.")

    with _lock:
        rows = _load()
        for r in rows:
            if r.get("approval_id") == jid and r.get("status") == "pending":
                return None, f"Permintaan '{jid}' sudah ada (masih terbuka)."

        # Langkah yang menunggu: waiting_step eksplisit, atau langkah pertama
        # berstatus waiting, atau current_step.
        steps = job.get("steps") or []
        idx = job.get("waiting_step")
        if not isinstance(idx, int) or not (0 <= idx < len(steps)):
            idx = next((i for i, s in enumerate(steps)
                        if s.get("status") == "waiting"), None)
            if idx is None:
                idx = min(int(job.get("current_step") or 0), max(0, len(steps) - 1))
        s = steps[idx] if steps else {}
        step_desc = f"{s.get('skill') or s.get('name') or '?'}: " \
                    f"{json.dumps(s.get('params') or {}, ensure_ascii=False)[:110]}"

        entry = {
            "approval_id": jid,
            "job_id": jid,
            "goal": job.get("goal", ""),
            "step_index": idx,
            "step_desc": step_desc[:150],
            "risk_level": job.get("risk_level", ""),
            "source": source,
            "created_at": _now(),
            "notified": False,
            "status": "pending",
            "decided_at": "",
            "decided_by": "",
        }
        rows.append(entry)
        _save(rows)
    if _audit:
        _audit({"skill": "remote_approval", "action": "approval.request",
                "target": jid, "source": source, "result": "pending"})
    return entry, ""


def register_from_output(out: str, source: str = "scheduler") -> str | None:
    """Pesan orchestrator 'butuh konfirmasi' → registrasi otomatis (best-effort).
    Return approval_id bila berhasil, None bila tidak relevan/gagal."""
    t = str(out or "")
    if "butuh konfirmasi" not in t.lower():
        return None
    m = _AID.search(t)
    if not m:
        return None
    entry, _err = register(m.group(0), source=source)
    return entry["approval_id"] if entry else None


# ── Query ───────────────────────────────────────────────────────────────────

def get(approval_id: str) -> dict | None:
    key = str(approval_id or "").strip().lower()
    with _lock:
        for r in reversed(_load()):
            if str(r.get("approval_id", "")).lower() == key or \
               str(r.get("job_id", "")).lower() == key:
                return r
    return None


def pending() -> list[dict]:
    with _lock:
        return [r for r in _load() if r.get("status") == "pending"]


def fmt_approval(a: dict) -> str:
    aid = a.get("approval_id", "?")
    return (f"🔔 {aid}\n"
            f"   goal: {a.get('goal', '')}\n"
            f"   langkah {int(a.get('step_index', 0)) + 1}: {a.get('step_desc', '')}\n"
            f"   risiko: {a.get('risk_level') or '-'} | sumber: "
            f"{a.get('source', '-')} | umur: {_age_str(a.get('created_at', ''))}\n"
            f"   Balas: setujui {aid} / tolak {aid}")


def fmt_pending() -> str:
    rows = pending()
    if not rows:
        return "Tidak ada permintaan persetujuan terbuka."
    return f"🔔 {len(rows)} permintaan persetujuan:\n" + \
        "\n".join(fmt_approval(r) for r in rows)


def _note_text(a: dict) -> str:
    aid = a.get("approval_id", "?")
    return (f"🔔 Butuh persetujuan (sumber: {a.get('source', 'manual')}):\n"
            f"  goal: {a.get('goal', '')}\n"
            f"  langkah {int(a.get('step_index', 0)) + 1}: {a.get('step_desc', '')}\n"
            f"  risiko: {a.get('risk_level') or '-'}\n"
            f"  Balas: setujui {aid} / tolak {aid}")


def notifications_new() -> list[dict]:
    """Permintaan pending yang belum terkirim ke HP → [{approval_id, text}]."""
    with _lock:
        return [{"approval_id": r["approval_id"], "text": _note_text(r)}
                for r in _load()
                if r.get("status") == "pending" and not r.get("notified")]


def mark_notified(approval_id: str) -> None:
    with _lock:
        rows = _load()
        changed = False
        for r in rows:
            if r.get("approval_id") == approval_id and not r.get("notified"):
                r["notified"] = True
                changed = True
        if changed:
            _save(rows)


def expire_stale() -> int:
    """Permintaan pending > TTL_HOURS → expired. Return jumlah yang kedaluwarsa."""
    with _lock:
        rows = _load()
        n = 0
        for r in rows:
            if r.get("status") == "pending" and \
                    _age_minutes(r.get("created_at", "")) > TTL_HOURS * 60:
                r["status"] = "expired"
                r["decided_at"] = _now()
                r["decided_by"] = "ttl"
                n += 1
                if _audit:
                    _audit({"skill": "remote_approval", "action": "approval.expire",
                            "target": r.get("approval_id", ""), "result": "expired"})
        if n:
            _save(rows)
        return n


# ── Resolve (approve / deny) ────────────────────────────────────────────────

def resolve(approval_id: str, decision: str, by: str = "user") -> str:
    """Putuskan permintaan. approve → orchestrator.run(job_id, confirm=True);
    deny → job_manager.cancel(). Return laporan siap-tampilkan."""
    decision = str(decision or "").strip().lower()
    if decision not in ("approve", "deny"):
        return f"remote_approval: decision '{decision}' tidak dikenal (approve|deny)."
    if _jm is None:
        return "remote_approval gagal: job_manager tidak tersedia"

    expire_stale()
    key = str(approval_id or "").strip().lower()
    with _lock:
        rows = _load()
        entry = next((r for r in reversed(rows)
                      if str(r.get("approval_id", "")).lower() == key or
                      str(r.get("job_id", "")).lower() == key), None)
        if entry is None:
            return f"Permintaan '{approval_id}' tidak ditemukan.\n{fmt_pending()}"
        if entry.get("status") != "pending":
            return (f"⚠️ {entry.get('approval_id')} sudah diputuskan "
                    f"({entry.get('status')} oleh {entry.get('decided_by') or '?'}).")

    jid = entry["job_id"]
    job = _jm.get_job(jid)
    if job is None:
        return f"Job '{jid}' sudah tidak ada — permintaan ditandai kadaluarsa."

    # ── DENY ──
    if decision == "deny":
        _jm.cancel(jid, reason=f"ditolak via {by}")
        with _lock:
            entry["status"] = "denied"
            entry["decided_at"] = _now()
            entry["decided_by"] = by
            _save(rows)
        if _audit:
            _audit({"skill": "remote_approval", "action": "approval.decision",
                    "target": jid, "decision": "deny", "by": by,
                    "result": "cancelled"})
        return f"❌ Ditolak (via {by}). Job {jid} dibatalkan.\n  goal: {entry.get('goal', '')}"

    # ── APPROVE ── (eksekusi tetap SATU pintu: orchestrator)
    if _orch is None:
        return ("remote_approval gagal: orchestrator tidak tersedia — "
                "keputusan TIDAK dicatat, job masih menunggu.")
    if job.get("status") != _jm.WAITING_CONFIRMATION:
        return (f"⚠️ Job '{jid}' status sekarang '{job.get('status')}' — "
                f"bukan waiting_confirmation. Tidak ada yang dieksekusi; "
                f"permintaan TIDAK diubah.")

    with _lock:
        entry["status"] = "approved"
        entry["decided_at"] = _now()
        entry["decided_by"] = by
        _save(rows)
    if _audit:
        _audit({"skill": "remote_approval", "action": "approval.decision",
                "target": jid, "decision": "approve", "by": by,
                "result": "resuming"})
    try:
        # goal/steps kosong: branch job_id di orchestrator mengabaikannya —
        # eksekusi lanjutan tetap SATU pintu lewat orchestrator (confirm=True).
        out = _orch.run(goal="", steps=[], job_id=jid, confirm=True)
    except Exception as e:
        with _lock:                                   # revert agar bisa diulang
            entry["status"] = "pending"
            entry["decided_at"] = ""
            entry["decided_by"] = ""
            _save(rows)
        return f"❌ Approve tercatat tapi eksekusi gagal (job tetap menunggu): {e}"
    return f"✅ Disetujui via {by} — melanjutkan job {jid}:\n{out}"


# ── Jalur teks dari HP (_process_dashboard_commands) ────────────────────────

def try_handle_text(text: str) -> str | None:
    """Teks dari HP → hasil approval, atau None bila bukan perintah approval.
    Hanya teks yang cocok penuh (anchored) yang dianggap perintah."""
    t = str(text or "").strip()
    tl = t.lower()
    if not t:
        return None
    if _RE_LIST.match(tl):
        return fmt_pending()

    m = _RE_APPROVE.match(tl) or _RE_DENY.match(tl)
    if not m:
        return None
    decision = "approve" if _RE_APPROVE.match(tl) else "deny"
    aid = (m.group(2) or "").strip()

    if not aid:
        rows = pending()
        if not rows:
            return "Tidak ada permintaan persetujuan terbuka."
        if len(rows) == 1:
            aid = rows[0]["approval_id"]
            out = resolve(aid, decision, by="hp")
            return "(otomatis: satu-satunya permintaan)\n" + out
        return f"Sebutkan id-nya:\n{fmt_pending()}"
    return resolve(aid, decision, by="hp")


def handle_command(payload: dict) -> str:
    """Jalur terstruktur (mis. tombol web UI): {approval_id|job_id, decision}."""
    p = payload if isinstance(payload, dict) else {}
    aid = str(p.get("approval_id") or p.get("job_id") or p.get("id") or "").strip()
    if not aid:
        return "remote_approval: approval_id kosong."
    return resolve(aid, str(p.get("decision") or ""), by="hp")


# ── Handler TOOL ────────────────────────────────────────────────────────────

def remote_approval(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "list").lower().strip()
    aid = str(p.get("id") or p.get("approval_id") or p.get("job_id") or "").strip()

    try:
        if cmd in ("list", "pending"):
            return fmt_pending()

        if cmd == "show":
            a = get(aid)
            return fmt_approval(a) if a else f"Permintaan '{aid}' tidak ditemukan."

        if cmd == "request":
            entry, err = register(aid, source="skill")
            if err:
                return f"❌ {err}"
            return f"✅ Permintaan terdaftar:\n{fmt_approval(entry)}"

        if cmd in ("approve", "deny"):
            return resolve(aid, cmd, by="skill")

        return ("Remote Approval — cmd: list | show (id) | request (id) | "
                "approve (id) | deny (id). Approve melanjutkan job via "
                "orchestrator (confirm=True) — tanpa pintu eksekusi lain.")
    except Exception as e:
        return f"remote_approval gagal: {e}"


TOOL = {
    "name": "remote_approval",
    "description": (
        "Setujui/tolak job yang menunggu konfirmasi dari jarak jauh: list "
        "permintaan terbuka, approve/deny by id. Approve melanjutkan eksekusi "
        "lewat orchestrator (confirm=True) — policy per langkah tetap jalan."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "list | show | request | approve | deny"},
            "id": {"type": "STRING", "description": "job_id / approval_id"},
        },
        "required": [],
    },
    "handler": remote_approval,
}
