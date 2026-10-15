#app_manager.py
"""
app_manager.py — Jarvis-grade running-app control for Neira.

Melihat aplikasi yang sedang aktif, mematikan aplikasi pilihan, dan
berpindah fokus ke aplikasi yang sudah terbuka — persis seperti Jarvis.

Sub-perintah (parameters["cmd"]):
  list    — daftar aplikasi berjendela yang aktif sekarang (PID + judul);
            jendela yang sedang di depan ditandai '◀ AKTIF DI DEPAN'
  close   — tutup aplikasi secara sopan (WM_CLOSE). Jika menolak (mis. ada
            dialog simpan), panggil lagi dengan force=true untuk paksa matikan
  kill    — langsung force-kill prosesnya
  switch  — fokuskan jendela aplikasi yang SUDAH terbuka (restore + foreground).
            Untuk membuka aplikasi yang belum jalan, pakai skill 'open_app'.

Target bisa berupa nama proses ('chrome'), judul jendela ('Spotify'), atau
PID ('1234'). Proses sistem kritikal (lsass, csrss, wininit, ...) SELALU
ditolak — tidak bisa dimatikan siapa pun.

Implementasi murni Python (ctypes Win32 + psutil) — tanpa PowerShell, jadi
cepat (<100 ms) dan tidak bisa tergantung oleh profil/module PS yang macet.

Auto-discovered by core/action_loader.py and core/skill_hub.py via TOOL dict —
kedua otak (Gemini suara + Hermes eksekutor) bisa memanggilnya:
  {"action": "app_manager", "cmd": "list"}
  {"action": "app_manager", "cmd": "close", "target": "notepad"}
  {"action": "app_manager", "cmd": "switch", "target": "spotify"}
"""
from __future__ import annotations

import ctypes
import platform
import sys
import time
from ctypes import wintypes

try:
    import psutil
except ImportError:
    psutil = None

# Tahap 1 — Fondasi keamanan: policy gate + audit log (blueprint §5/§8)
try:
    from core.policy_engine import (
        decide as _policy_decide,
        protected_processes as _policy_protected,
        deny_message as _policy_deny_msg,
        confirm_message as _policy_confirm_msg,
    )
except Exception:
    _policy_decide = None
try:
    from core.audit_logger import log_event as _audit_log
except Exception:
    def _audit_log(event):                       # type: ignore[misc]
        return False

_OS = platform.system()

# Proses yang TIDAK BOLEH disentuh — mematikannya bisa BSOD / matikan mesin.
_PROTECTED = {
    "system", "idle", "csrss", "wininit", "winlogon", "smss",
    "services", "lsass", "svchost", "registry", "memcompression",
    "memory compression", "dwm", "fontdrvhost", "windeploy",
}

# Nama panggilan umum → nama proses Windows yang sebenarnya.
_ALIASES = {
    "vscode": "code", "vs code": "code", "visual studio code": "code",
    "word": "winword", "powerpoint": "powerpnt", "ppt": "powerpnt",
    "terminal": "windowsterminal", "cmd": "cmd", "command prompt": "cmd",
    "file explorer": "explorer", "file manager": "explorer",
    "google chrome": "chrome", "edge": "msedge", "browser": "chrome",
    "kalkulator": "calculator", "task manager": "taskmgr",
}

# Win32 konstanta
_WM_CLOSE       = 0x0010
_SW_RESTORE     = 9
_VK_MENU        = 0x12          # ALT
_KEYEVENTF_KEYUP = 0x0002
_GWL_STYLE      = -16
_WS_EX_TOOLWINDOW = 0x00000080
_WS_VISIBLE     = 0x10000000


def _user32():
    return ctypes.windll.user32


# ── Enumerasi jendela via ctypes (murni Python, cepat & andal) ────────────────

def _window_entries() -> list[dict]:
    """Semua jendela top-level terlihat yang punya judul: hwnd, pid, title."""
    if _OS != "Windows":
        return []
    u32 = _user32()
    entries: list[dict] = []

    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def _cb(hwnd, _lparam):
        # hanya jendela yang benar-benar terlihat
        if not u32.IsWindowVisible(hwnd):
            return True
        # buang jendela tool/no-title (tooltip, menu shadow, dsb.)
        ex_style = u32.GetWindowLongW(hwnd, _GWL_STYLE) or 0
        if ex_style & _WS_EX_TOOLWINDOW:
            return True
        length = u32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        u32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if not title:
            return True
        pid = wintypes.DWORD(0)
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        entries.append({
            "hwnd":  hwnd,
            "pid":   pid.value,
            "title": title,
            "fg":    hwnd == u32.GetForegroundWindow(),
        })
        return True

    try:
        u32.EnumWindows(EnumWindowsProc(_cb), 0)
    except Exception:
        pass
    return entries


def _proc_name(pid: int) -> str:
    if psutil:
        try:
            return psutil.Process(pid).name().rsplit(".", 1)[0].lower()
        except Exception:
            return "?"
    return "?"


def _list_apps() -> list[dict]:
    """Aplikasi unik (per PID) yang punya jendela terlihat berjudul."""
    if _OS != "Windows":
        return []
    apps: dict[int, dict] = {}
    for w in _window_entries():
        pid = w["pid"]
        if pid <= 0:
            continue
        if pid in apps:
            # simpan judul terpanjang + flag fg dari jendela mana pun milik PID ini
            if len(w["title"]) > len(apps[pid]["title"]):
                apps[pid]["title"] = w["title"]
            apps[pid]["fg"] = apps[pid]["fg"] or w["fg"]
        else:
            apps[pid] = {
                "pid":   pid,
                "name":  _proc_name(pid),
                "title": w["title"],
                "fg":    w["fg"],
            }
    return list(apps.values())


def _norm(target: str) -> str:
    t = (target or "").strip().lower()
    if t.endswith(".exe"):
        t = t[:-4]
    return _ALIASES.get(t, t)


def _find(target: str, apps: list[dict]) -> list[dict]:
    """Cocokkan target (nama / judul / PID) ke daftar aplikasi aktif."""
    t = _norm(target)
    if t.isdigit():
        pid = int(t)
        return [a for a in apps if a["pid"] == pid]
    exact = [a for a in apps if a["name"].lower() == t]
    if exact:
        return exact
    return [a for a in apps if t in a["name"].lower() or t in a["title"].lower()]


def _fmt_list(apps: list[dict]) -> str:
    if not apps:
        return "Tidak ada aplikasi berjendela yang aktif saat ini."
    lines = ["Aplikasi aktif saat ini (PID — Nama — Judul jendela):"]
    for a in sorted(apps, key=lambda x: (not x["fg"], x["name"].lower())):
        mark = " ◀ AKTIF DI DEPAN" if a["fg"] else ""
        lines.append(f"  [{a['pid']}] {a['name']} — {a['title']}{mark}")
    lines.append("Gunakan PID atau nama untuk close/kill/switch.")
    return "\n".join(lines)


# ── Tutup / matikan / fokus ───────────────────────────────────────────────────

def _alive(pid: int) -> bool:
    if psutil:
        return psutil.pid_exists(pid)
    u32 = _user32()
    k32 = ctypes.windll.kernel32
    h = k32.OpenProcess(0x100000, False, pid)   # PROCESS_QUERY_LIMITED_INFORMATION
    if h:
        k32.CloseHandle(h)
        return True
    return False


def _close_one(pid: int, force: bool) -> str:
    """Tutup sopan (WM_CLOSE ke semua jendela proses) → verifikasi mati →
    paksa Stop hanya jika force."""
    u32 = _user32()
    sent = False
    for w in _window_entries():
        if w["pid"] == pid:
            u32.PostMessageW(w["hwnd"], _WM_CLOSE, 0, 0)
            sent = True
    if not sent and not force:
        # proses berjalan tapi tak ada jendela yang bisa dikirimi WM_CLOSE
        return "refused"
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not _alive(pid):
            return "closed"
        time.sleep(0.25)
    if force:
        try:
            if psutil:
                psutil.Process(pid).kill()
            else:
                import subprocess as _sp
                _sp.run(["taskkill", "/F", "/PID", str(pid)],
                        capture_output=True, creationflags=0x08000000)
            time.sleep(0.4)
            return "killed" if not _alive(pid) else "failed: proses masih hidup setelah force"
        except Exception as e:
            return f"failed: {e}"
    return "refused"


def _kill_one(pid: int) -> str:
    try:
        if psutil:
            psutil.Process(pid).kill()
        else:
            import subprocess as _sp
            _sp.run(["taskkill", "/F", "/PID", str(pid)],
                    capture_output=True, creationflags=0x08000000)
        time.sleep(0.4)
        return "killed" if not _alive(pid) else "failed: proses masih hidup"
    except psutil.NoSuchProcess:
        return "closed"                      # sudah mati — anggap berhasil
    except Exception as e:
        return f"failed: {e}"


def _switch_one(pid: int) -> str:
    """Restore + foreground jendela proses. Trik ALT-tap (keybd_event)
    dulu agar Windows mengizinkan SetForegroundWindow dari proses latar."""
    u32 = _user32()
    hwnds = [w["hwnd"] for w in _window_entries() if w["pid"] == pid]
    if not hwnds:
        return "no_window"
    hwnd = max(hwnds, key=lambda h: (u32.GetForegroundWindow() == h,
                                     u32.GetWindowTextLengthW(h)))
    try:
        # tap ALT lalu lepas — memberi izin transfer fokus
        u32.keybd_event(_VK_MENU, 0, 0, 0)
        u32.keybd_event(_VK_MENU, 0, _KEYEVENTF_KEYUP, 0)
        u32.ShowWindow(hwnd, _SW_RESTORE)
        time.sleep(0.05)
        if u32.SetForegroundWindow(hwnd):
            return "switched"
        # fallback klasik: AttachThreadInput antara thread kita & thread jendela
        k32 = ctypes.windll.kernel32
        my_tid   = k32.GetCurrentThreadId()
        other_tid = u32.GetWindowThreadProcessId(hwnd, None)
        if other_tid and other_tid != my_tid:
            if u32.AttachThreadInput(my_tid, other_tid, True):
                try:
                    u32.BringWindowToTop(hwnd)
                    ok = bool(u32.SetForegroundWindow(hwnd))
                finally:
                    u32.AttachThreadInput(my_tid, other_tid, False)
                if ok:
                    return "switched"
        return u32.GetForegroundWindow() == hwnd and "switched" or "failed: Windows menolak transfer fokus"
    except Exception as e:
        return f"failed: {e}"


# ── Handler utama ─────────────────────────────────────────────────────────────

def app_manager(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd    = str(p.get("cmd") or p.get("operation") or "list").lower().strip()
    target = str(p.get("target") or p.get("name") or p.get("app") or "").strip()
    force  = bool(p.get("force") or p.get("force_kill"))

    if _OS != "Windows":
        return f"app_manager: saat ini hanya mendukung Windows (terdeteksi: {_OS})."
    if psutil is None:
        return "app_manager: modul psutil belum terpasang (pip install psutil)."

    try:
        if cmd == "list":
            return _fmt_list(_list_apps())

        if cmd in ("close", "kill", "quit", "tutup", "matikan"):
            if not target:
                return ("Sebutkan target: nama aplikasi, judul jendela, atau PID "
                        "(contoh: {\"cmd\": \"close\", \"target\": \"chrome\"}).")
            # Proteksi proses sistem dicek PALING AWAL — proses kritikal seperti
            # csrss/lsass tidak punya jendela, jadi kalau dicek setelah pencarian
            # aplikasi berjendela mereka akan lolos sebagai "tidak ditemukan".
            # Sumber kebenaran: policies/default_policy.json via policy_engine
            # (fallback: _PROTECTED lokal bila policy_engine tak terpasang).
            norm_name = _norm(target)
            protected_set = _PROTECTED
            if _policy_decide is not None:
                protected_set = _PROTECTED | _policy_protected()
            if norm_name in protected_set:
                _audit_log({"skill": "app_manager", "action": "app.kill",
                            "target": norm_name, "decision": "deny",
                            "risk_level": "critical", "result": "denied",
                            "note": "proses sistem kritikal"})
                return (f"❌ Ditolak oleh policy: '{norm_name}' adalah proses "
                        "sistem kritikal dan tidak boleh dimatikan.")
            apps    = _list_apps()
            matches = _find(target, apps)
            if not matches:
                # Fallback: target = PID proses hidup yang TIDAK punya jendela
                # (proses latar/CLI). Tetap boleh di-close/kill — lewat policy
                # gate di bawah seperti biasa.
                norm_pid = _norm(target)
                if norm_pid.isdigit() and _alive(int(norm_pid)):
                    pid = int(norm_pid)
                    matches = [{"pid": pid, "name": _proc_name(pid),
                                "title": "(tanpa jendela)", "fg": False}]
                else:
                    return (f"Tidak ada aplikasi aktif yang cocok dengan '{target}'. "
                            "Panggil cmd='list' untuk melihat daftar aplikasi yang sedang berjalan.")
            protected = [m for m in matches if m["name"].lower() in protected_set]
            if protected:
                names = ", ".join(m["name"] for m in protected)
                _audit_log({"skill": "app_manager", "action": "app.kill",
                            "target": names, "decision": "deny",
                            "risk_level": "critical", "result": "denied",
                            "note": "proses sistem kritikal"})
                return (f"❌ Ditolak oleh policy: '{names}' adalah proses sistem "
                        "kritikal dan tidak boleh dimatikan.")
            hard    = cmd == "kill" or force
            # ── Policy gate (Tahap 1): kill/force = HIGH → wajib konfirmasi user,
            #    kecuali pemanggil sudah mengirim confirm=true setelah user setuju.
            if _policy_decide is not None:
                action = "app.kill" if hard else "app.close"
                d = _policy_decide(action, target=norm_name)
                if d.get("decision") == "deny":
                    _audit_log({"skill": "app_manager", "action": action,
                                "target": target, "decision": "deny",
                                "risk_level": d.get("risk", ""), "result": "denied",
                                "note": d.get("reason", "")})
                    return _policy_deny_msg(d, "app_manager", target)
                if d.get("decision") == "confirm" and not bool(p.get("confirm")):
                    _audit_log({"skill": "app_manager", "action": action,
                                "target": target, "decision": "confirm",
                                "risk_level": d.get("risk", ""),
                                "result": "awaiting_confirmation"})
                    return _policy_confirm_msg(d, "app_manager", target)
            results = []
            for m in matches:
                if hard:
                    results.append((m, _kill_one(m["pid"])))
                else:
                    results.append((m, _close_one(m["pid"], force)))
            for m, s in results:
                _audit_log({"skill": "app_manager",
                            "action": "app.kill" if hard else "app.close",
                            "target": f"{m['name']}(pid={m['pid']})",
                            "decision": "allow",
                            "risk_level": "high" if hard else "medium",
                            "result": s})
            parts = []
            ok = [m for m, s in results if s in ("closed", "killed")]
            if ok:
                parts.append("✅ " + ", ".join(f"{m['name']} (PID {m['pid']})" for m in ok)
                             + (" dimatikan paksa." if hard else " berhasil ditutup."))
            refused = [m for m, s in results if s == "refused"]
            if refused:
                parts.append("⚠️ " + ", ".join(f"{m['name']} (PID {m['pid']})" for m in refused)
                             + " menolak ditutup (mungkin ada dialog simpan). "
                               "Panggil lagi dengan force=true untuk mematikan paksa.")
            for m, s in results:
                if s.startswith("failed"):
                    parts.append(f"❌ {m['name']} (PID {m['pid']}): {s}")
            return "\n".join(parts)

        if cmd in ("switch", "focus", "activate", "pindah", "fokus"):
            if not target:
                return "Sebutkan target: nama aplikasi, judul jendela, atau PID."
            matches = _find(target, _list_apps())
            if not matches:
                return (f"Aplikasi '{target}' tidak sedang berjalan. "
                        "Gunakan skill open_app untuk membukanya, atau cmd='list' "
                        "untuk melihat aplikasi yang aktif.")
            m = matches[0]
            status = _switch_one(m["pid"])
            if status == "switched":
                return f"✅ Fokus dipindahkan ke {m['name']} — '{m['title']}'."
            if status == "no_window":
                return f"⚠️ {m['name']} berjalan tapi tidak punya jendela yang bisa difokuskan."
            return f"❌ Gagal memfokuskan {m['name']} (PID {m['pid']}): {status}"

        return ("cmd '" + cmd + "' tidak dikenal. Gunakan: list | close | kill | switch "
                "(contoh: {\"cmd\": \"close\", \"target\": \"chrome\"}).")
    except Exception as e:
        return f"app_manager gagal: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "app_manager",
    "description": (
        "Kelola aplikasi yang sedang berjalan di laptop: lihat daftar aplikasi "
        "aktif beserta PID dan judul jendelanya, tutup/paksa matikan aplikasi "
        "tertentu, dan pindahkan fokus ke aplikasi yang sudah terbuka."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {
                "type": "STRING",
                "description": "list | close | kill | switch (default: list)"
            },
            "target": {
                "type": "STRING",
                "description": "Nama proses, judul jendela, atau PID — wajib untuk close/kill/switch"
            },
            "force": {
                "type": "BOOLEAN",
                "description": "Untuk close: paksa matikan jika tutup normal ditolak (default: false)"
            },
        },
        "required": [],
    },
    "handler": app_manager,
}
