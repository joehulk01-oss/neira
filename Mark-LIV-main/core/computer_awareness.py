# computer_awareness.py
"""Tahap 3 — Computer Awareness: snapshot kondisi PC (READ-ONLY).

Filosofi blueprint file.txt: agen tidak boleh menebak kondisi PC — ia
harus MELIHAT fakta dulu sebelum bertindak. Modul ini 100% baca:
jendela aktif, daftar jendela, CPU/RAM/baterai, layar, uptime, top RAM.

Tidak ada satu pun aksi tulis di sini. Kendali jendela (focus/min/max/
restore/close) ada di skills/admin/window_manager.py yang melewati
policy gate + audit + emergency stop.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path


def _base_dir() -> Path:
    try:
        from core.paths import BASE_DIR  # type: ignore
        return Path(BASE_DIR)
    except Exception:
        return Path(__file__).resolve().parent.parent


BASE_DIR = _base_dir()
IS_WINDOWS = os.name == "nt"

# Kode ShowWindow — dipakai juga oleh skills/admin/window_manager.py
SW_MINIMIZE, SW_MAXIMIZE, SW_RESTORE = 6, 3, 9


def platform_name() -> str:
    try:
        import platform
        return platform.release() or platform.system()
    except Exception:
        return ""


def proc_name(pid: int) -> str:
    """Nama proses (lowercase). String kosong bila tidak ketemu."""
    try:
        import psutil
        return (psutil.Process(int(pid)).name() or "").strip().lower()
    except Exception:
        return ""


def window_entries() -> list:
    """Semua jendela top-level TERLIHAT yang punya judul: hwnd, pid, title."""
    if not IS_WINDOWS:
        return []
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    out: list = []
    EnumProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lp):
        try:
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                if n > 0:
                    buf = ctypes.create_unicode_buffer(n + 1)
                    user32.GetWindowTextW(hwnd, buf, n + 1)
                    pid = wintypes.DWORD(0)
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                    title = buf.value.strip()
                    if title:
                        out.append({"hwnd": int(hwnd),
                                    "pid": int(pid.value or 0),
                                    "title": title})
        except Exception:
            pass
        return True

    try:
        user32.EnumWindows(EnumProc(_cb), 0)
    except Exception:
        pass
    return out


def active_window() -> dict:
    """Jendela yang sedang fokus (foreground) saat ini."""
    if not IS_WINDOWS:
        return {"hwnd": 0, "pid": 0, "title": "", "process": ""}
    import ctypes
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return {"hwnd": 0, "pid": 0, "title": "", "process": ""}
    n = user32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(max(n, 1) + 1)
    if n > 0:
        user32.GetWindowTextW(hwnd, buf, n + 1)
    pid = ctypes.c_ulong(0)
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return {"hwnd": int(hwnd), "pid": int(pid.value or 0),
            "title": buf.value.strip(), "process": proc_name(pid.value)}


def screen_size() -> dict:
    if not IS_WINDOWS:
        return {"width": 0, "height": 0}
    import ctypes
    user32 = ctypes.windll.user32
    try:
        return {"width": int(user32.GetSystemMetrics(0)),
                "height": int(user32.GetSystemMetrics(1))}
    except Exception:
        return {"width": 0, "height": 0}


def _battery():
    try:
        import psutil
        b = psutil.sensors_battery()
        if not b:
            return None
        return {"percent": round(float(b.percent), 1),
                "plugged": bool(b.power_plugged)}
    except Exception:
        return None


def _top_memory(limit: int = 5) -> list:
    try:
        import psutil
        rows = []
        for p in psutil.process_iter(["pid", "name", "memory_percent"]):
            try:
                mp = p.info.get("memory_percent") or 0
                if mp > 0:
                    rows.append({"pid": p.info["pid"],
                                 "name": (p.info.get("name") or "").lower(),
                                 "mem_pct": round(float(mp), 1)})
            except Exception:
                continue
        rows.sort(key=lambda r: r["mem_pct"], reverse=True)
        return rows[:limit]
    except Exception:
        return []


def _human_uptime(sec) -> str:
    try:
        sec = int(sec)
    except Exception:
        return "?"
    if sec < 0:
        return "?"
    m, s = divmod(sec, 60)
    h, m = divmod(m, 60)
    d, h = divmod(h, 24)
    if d:
        return f"{d}h {h}j {m}m"
    if h:
        return f"{h}j {m}m"
    return f"{m}m {s}d"


def snapshot() -> dict:
    """Snapshot lengkap kondisi PC (read-only) — fakta untuk otak."""
    cpu = mem = -1.0
    uptime_s = -1
    try:
        import psutil
        cpu = psutil.cpu_percent(interval=0.15)
        mem = psutil.virtual_memory().percent
        uptime_s = int(time.time() - psutil.boot_time())
    except Exception:
        pass
    wins = window_entries()
    act = active_window()
    return {
        "taken_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "os": f"Windows {platform_name()}" if IS_WINDOWS else os.name,
        "cpu_percent": cpu,
        "mem_percent": mem,
        "battery": _battery(),
        "uptime_s": uptime_s,
        "screen": screen_size(),
        "active_window": act,
        "windows": wins,
        "window_count": len(wins),
        "top_memory": _top_memory(),
    }


def format_snapshot(snap: dict) -> str:
    """Snapshot → teks ringkas siap dikonsumsi LLM/user."""
    b = snap.get("battery")
    if b:
        bat = f"{b.get('percent', 0)}% ({'charger' if b.get('plugged') else 'baterai'})"
    else:
        bat = "n/a"
    scr = snap.get("screen") or {}
    act = snap.get("active_window") or {}
    lines = [
        "🖥️ KONDISI PC (snapshot read-only)",
        f"OS     : {snap.get('os', '?')} | uptime {_human_uptime(snap.get('uptime_s', -1))}",
        f"CPU    : {snap.get('cpu_percent', -1)}% | RAM: {snap.get('mem_percent', -1)}% | Baterai: {bat}",
        f"Layar  : {scr.get('width', 0)}x{scr.get('height', 0)}",
        f"AKTIF  : [{act.get('pid', 0)}] {act.get('process') or '?'} — {act.get('title') or '(tanpa judul)'}",
        f"JENDELA TERLIHAT: {snap.get('window_count', 0)}",
    ]
    for w in (snap.get("windows") or [])[:12]:
        lines.append(f"  • pid {w['pid']} | {proc_name(w['pid']) or '?'} | {w['title'][:60]}")
    top = snap.get("top_memory") or []
    if top:
        lines.append("TOP RAM  : " + ", ".join(f"{r['name']} {r['mem_pct']}%" for r in top))
    return "\n".join(lines)


def awareness_text() -> str:
    """Shortcut: snapshot sekarang → teks siap pakai."""
    return format_snapshot(snapshot())
