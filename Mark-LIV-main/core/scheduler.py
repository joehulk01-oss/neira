# scheduler.py — Blueprint Tahap 11
"""
task_scheduler — jadwal tugas otomatis Neira (Blueprint §4.10-ish).

Kapan tugas jalan BUKAN keputusan otak — ini dimensi baru di atas job_manager:
    add(name, goal, steps, every_minutes=..|at="HH:MM") → disimpan persisten
    tick() → cari jadwal jatuh tempo → eksekusi via orchestrator.run()
             (policy gate + emergency stop + verifikasi tetap aktif per langkah)

Aturan:
- Eksekusi TETAP satu pintu: orchestrator.run() — scheduler hanya MEMICU,
  tidak pernah eksekusi langsung skill (no-shortcut, konsisten planner/workflow).
- Anti re-trigger: last_run/next_run di-MAJUKAN sebelum eksekusi — job panjang
  tidak bikin tick berikutnya menembak ulang jadwal yang sama.
- Anti catch-up spam: jadwal yang terlewat (PC mati) dijadwalkan ulang dari
  SEKARANG, bukan ditembak berkali-kali untuk setiap interval terlewat.
- waiting_confirmation BUKAN kegagalan — job nunggu user, scheduler lanjut.
- Persisten di memory/schedules.json (atomic write, pola job_manager).

Pemakaian:
    from core import scheduler as ts
    ts.add("backup pagi", "backup workspace", [{"skill": "workspace_dev",
          "params": {"cmd": "backup", "target": ""}}], at="07:00")
    ts.tick()   # dipanggil main loop / handler
"""
from __future__ import annotations

import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

try:
    from core.audit_logger import log_event as _audit
except Exception:
    _audit = None
try:
    from core import jarvis_orchestrator as _orch
except Exception:
    _orch = None
try:
    from skills.admin.emergency_stop import is_stopped
except Exception:
    def is_stopped() -> bool:            # type: ignore[misc]
        return False


def _base_dir() -> Path:
    try:
        from core.paths import BASE_DIR  # type: ignore
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
SCHED_PATH = BASE_DIR / "memory" / "schedules.json"
MAX_STEPS = 10

_lock = threading.RLock()
_HHMM = re.compile(r"^(\d{1,2}):(\d{1,2})$")


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())


def _load() -> list[dict]:
    with _lock:
        if not SCHED_PATH.exists():
            return []
        try:
            data = json.loads(SCHED_PATH.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except Exception:
            return []


def _save(rows: list[dict]) -> None:
    with _lock:
        SCHED_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp = SCHED_PATH.with_suffix(".tmp")
        tmp.write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        os.replace(tmp, SCHED_PATH)


# ── Validasi waktu ───────────────────────────────────────────────────────────

def _parse_hhmm(at: str) -> tuple[int, int] | None:
    m = _HHMM.match(str(at or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if 0 <= h <= 23 and 0 <= mi <= 59:
        return h, mi
    return None


def compute_next_run(s: dict, now: float | None = None) -> float:
    """Hitung next_run (epoch) untuk satu jadwal. Jadwal terlewat → dari sekarang."""
    now = float(now if now is not None else time.time())
    ev = s.get("every_minutes")
    if isinstance(ev, (int, float)) and ev >= 1:
        last = float(s.get("last_run") or 0)
        base = last if last > 0 else now
        nxt = base + float(ev) * 60.0
        return nxt if nxt > now else now + float(ev) * 60.0
    hm = _parse_hhmm(s.get("at") or "")
    if hm:
        h, mi = hm
        lt = time.localtime(now)
        cand = time.mktime((lt.tm_year, lt.tm_mon, lt.tm_mday, h, mi, 0, 0, 0, -1))
        if cand <= now:
            cand += 86400.0
        return cand
    return now + 3600.0        # fallback aman (add() sudah menolak spec invalid)


# ── Validasi langkah (pola task_planner) ─────────────────────────────────────

def _validate_steps(steps) -> tuple[list[dict], str]:
    if not isinstance(steps, list) or not steps:
        return [], "steps kosong — minimal 1 langkah"
    if len(steps) > MAX_STEPS:
        return [], f"terlalu banyak langkah (maks {MAX_STEPS})"
    clean: list[dict] = []
    for s in steps:
        if not isinstance(s, dict):
            return [], "setiap langkah harus object {skill, params}"
        skill = str(s.get("skill") or "").strip()
        if not skill:
            return [], "langkah tanpa 'skill'"
        params = s.get("params") if isinstance(s.get("params"), dict) else {}
        clean.append({"skill": skill, "params": params})
    return clean, ""


# ── CRUD jadwal ──────────────────────────────────────────────────────────────

def add(name: str, goal: str, steps: list[dict], every_minutes=None,
        at: str = "", risk_level: str = "medium") -> tuple[dict, bool, str]:
    """Tambah jadwal. Return (schedule, created, error). Nama sama → job lama."""
    name = str(name or "").strip()
    goal = str(goal or "").strip()
    if not name:
        return {}, False, "nama jadwal kosong"
    if not goal:
        return {}, False, "goal kosong"
    clean, err = _validate_steps(steps)
    if err:
        return {}, False, err
    spec_given = False
    ev = None
    if every_minutes is not None and str(every_minutes).strip() != "":
        try:
            ev = float(every_minutes)
        except Exception:
            return {}, False, "every_minutes harus angka (menit)"
        if ev < 1:
            return {}, False, "every_minutes minimal 1 menit"
        spec_given = True
    if str(at or "").strip():
        if _parse_hhmm(at) is None:
            return {}, False, "at harus format HH:MM (contoh 07:30)"
        spec_given = True
    if not spec_given:
        return {}, False, 'butuh every_minutes (interval) atau at "HH:MM"'

    with _lock:
        rows = _load()
        for r in rows:
            if str(r.get("name", "")).lower() == name.lower():
                return r, False, ""
        now = time.time()
        sched = {
            "schedule_id": f"sched-{time.strftime('%Y%m', time.localtime())}-{uuid.uuid4().hex[:6]}",
            "name": name, "goal": goal, "steps": clean,
            "every_minutes": ev, "at": str(at or "").strip(),
            "risk_level": str(risk_level or "medium"),
            "enabled": True, "created_at": _now_iso(),
            "last_run": 0.0, "next_run": 0.0,
            "run_count": 0, "fail_count": 0, "last_result": "",
        }
        sched["next_run"] = compute_next_run(sched, now)
        rows.append(sched)
        _save(rows)
        if _audit:
            _audit({"skill": "task_scheduler", "action": "scheduler.manage",
                    "target": name[:120], "result": "created",
                    "next_run": time.strftime("%Y-%m-%d %H:%M", time.localtime(sched["next_run"]))})
        return sched, True, ""


def get(name_or_id: str) -> dict | None:
    key = str(name_or_id or "").strip().lower()
    with _lock:
        for r in _load():
            if key in (str(r.get("name", "")).lower(), str(r.get("schedule_id", "")).lower()):
                return r
    return None


def remove(name_or_id: str) -> bool:
    key = str(name_or_id or "").strip().lower()
    with _lock:
        rows = _load()
        kept = [r for r in rows
                if key not in (str(r.get("name", "")).lower(),
                               str(r.get("schedule_id", "")).lower())]
        if len(kept) == len(rows):
            return False
        _save(kept)
    if _audit:
        _audit({"skill": "task_scheduler", "action": "scheduler.manage",
                "target": key[:120], "result": "removed"})
    return True


def set_enabled(name_or_id: str, enabled: bool) -> dict | None:
    with _lock:
        rows = _load()
        for r in rows:
            key = str(name_or_id or "").strip().lower()
            if key in (str(r.get("name", "")).lower(), str(r.get("schedule_id", "")).lower()):
                r["enabled"] = bool(enabled)
                if enabled:
                    r["next_run"] = compute_next_run(r)
                _save(rows)
                return r
    return None


def list_schedules() -> list[dict]:
    with _lock:
        return list(_load())


# ── Format ───────────────────────────────────────────────────────────────────

def fmt_schedule(s: dict) -> str:
    if s.get("every_minutes"):
        spec = f"setiap {s['every_minutes']:g} menit"
    else:
        spec = f"harian pukul {s.get('at', '?')}"
    on = "▶️" if s.get("enabled") else "⏸"
    nxt = (time.strftime("%Y-%m-%d %H:%M", time.localtime(float(s["next_run"])))
           if s.get("next_run") else "-")
    return (f"{on} {s['name']} — {spec} | {s['goal'][:60]} | "
            f"next: {nxt} | jalan {s.get('run_count', 0)}x "
            f"(gagal {s.get('fail_count', 0)}x)")


def fmt_all() -> str:
    rows = list_schedules()
    if not rows:
        return "Tidak ada jadwal terdaftar. Tambah dengan cmd=add."
    return f"⏱ {len(rows)} jadwal:\n" + "\n".join(fmt_schedule(r) for r in rows)


# ── Tick: jantung scheduler ──────────────────────────────────────────────────

def _mark_started(sid: str, now: float) -> None:
    """MAJUKAN last_run/next_run SEBELUM eksekusi — anti re-trigger."""
    with _lock:
        rows = _load()
        for r in rows:
            if r.get("schedule_id") == sid:
                r["last_run"] = now
                r["next_run"] = compute_next_run(r, now)
                _save(rows)
                return


def _mark_result(sid: str, result: str, outcome: str) -> None:
    """outcome: ok | fail | awaiting — awaiting BUKAN gagal."""
    with _lock:
        rows = _load()
        for r in rows:
            if r.get("schedule_id") == sid:
                r["last_result"] = str(result)[:200]
                r["run_count"] = int(r.get("run_count", 0)) + 1
                if outcome == "fail":
                    r["fail_count"] = int(r.get("fail_count", 0)) + 1
                _save(rows)
                return


def _classify(out: str, goal: str) -> str:
    """Klasifikasi jujur hasil orchestrator.run untuk ringkasan scheduler."""
    head = str(out)[:400].lower()
    if "butuh konfirmasi" in head or "waiting_confirmation" in head or "⚠️" in str(out)[:200]:
        return "awaiting"
    if head.startswith("failed") or head.startswith("orchestrator failed") \
            or "gagal" in head or "ditolak policy" in head:
        return "fail"
    return "ok"


def tick(now: float | None = None) -> str:
    """Jalankan semua jadwal yang jatuh tempo. Return laporan ringkas."""
    if is_stopped():
        return "⛔ EMERGENCY STOP aktif — scheduler tick diblokir."
    if _orch is None:
        return "scheduler failed: orchestrator tidak tersedia"
    now = float(now if now is not None else time.time())

    due = [s for s in list_schedules()
           if s.get("enabled") and float(s.get("next_run") or 0) <= now]
    total = len(list_schedules())
    if not due:
        return f"⏱ Scheduler tick: 0 jadwal jatuh tempo ({total} terdaftar)."

    lines = [f"⏱ Scheduler tick: {len(due)} jadwal jatuh tempo."]
    for s in due:
        _mark_started(s["schedule_id"], now)   # majukan dulu (anti re-trigger)
        goal = f"[schedule:{s['name']}] {s['goal']}"
        try:
            out = _orch.run(goal=goal, steps=s.get("steps") or [],
                            risk_level=str(s.get("risk_level") or "medium"))
        except Exception as e:
            out = f"failed: {e}"
        outcome = _classify(out, goal)
        _mark_result(s["schedule_id"], out, outcome)
        icon = {"ok": "✅", "fail": "❌", "awaiting": "⚠️"}.get(outcome, "•")
        lines.append(f"  {icon} {s['name']}: {str(out).splitlines()[0][:110]}")
        if _audit:
            _audit({"skill": "task_scheduler", "action": "scheduler.tick",
                    "target": s["name"][:120], "result": outcome})
    return "\n".join(lines)


def due_report(tick_out: str) -> str | None:
    """Output tick() → pesan siap-dikirim ke user oleh main loop.
    None = tidak ada yang jalan (atau diblokir estop) → jangan ganggu user."""
    t = str(tick_out or "").strip()
    if not t or t.startswith("⛔") or "0 jadwal jatuh tempo" in t:
        return None
    return t


# ── Handler TOOL ─────────────────────────────────────────────────────────────

def task_scheduler(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "list").lower().strip()
    name = str(p.get("name") or "").strip()

    try:
        if cmd == "list":
            return fmt_all()

        if cmd == "show":
            s = get(name)
            return fmt_schedule(s) if s else f"Jadwal '{name}' tidak ditemukan."

        if cmd == "add":
            s, created, err = add(name, p.get("goal") or "", p.get("steps") or [],
                                  every_minutes=p.get("every_minutes"),
                                  at=str(p.get("at") or ""),
                                  risk_level=str(p.get("risk_level") or "medium"))
            if err:
                return f"❌ {err}"
            if not created:
                return f"⚠️ Jadwal '{name}' sudah ada (anti duplikat):\n{fmt_schedule(s)}"
            return f"✅ Jadwal dibuat:\n{fmt_schedule(s)}"

        if cmd == "remove":
            return (f"🗑 Jadwal '{name}' dihapus."
                    if remove(name) else f"Jadwal '{name}' tidak ditemukan.")

        if cmd in ("enable", "disable"):
            s = set_enabled(name, cmd == "enable")
            if s is None:
                return f"Jadwal '{name}' tidak ditemukan."
            return f"{'▶️ Diaktifkan' if cmd == 'enable' else '⏸ Dimatikan'}: {fmt_schedule(s)}"

        if cmd in ("tick", "run_due"):
            return tick()

        return ("Task Scheduler — cmd: add (name, goal, steps, every_minutes|at) | "
                "remove | list | show | enable | disable | tick (jalankan yang "
                "jatuh tempo). Eksekusi tetap lewat orchestrator.")
    except Exception as e:
        return f"task_scheduler gagal: {e}"


TOOL = {
    "name": "task_scheduler",
    "description": (
        "Jadwal tugas otomatis: daftarkan goal+steps yang berulang (interval "
        "menit atau jam harian HH:MM), lalu tick mengeksekusi jadwal jatuh "
        "tempo lewat orchestrator (policy + konfirmasi tetap aktif)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "add | remove | list | show | enable | disable | tick"},
            "name": {"type": "STRING", "description": "Nama jadwal"},
            "goal": {"type": "STRING", "description": "Tujuan tugas (untuk add)"},
            "steps": {"type": "ARRAY",
                      "description": "Langkah [{skill, params}] (untuk add)"},
            "every_minutes": {"type": "NUMBER",
                              "description": "Interval menit (untuk add)"},
            "at": {"type": "STRING", "description": "Jam harian HH:MM (untuk add)"},
        },
        "required": [],
    },
    "handler": task_scheduler,
}
