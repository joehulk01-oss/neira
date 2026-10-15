"""
list_open_windows — Tool untuk Neira melihat aplikasi yang sedang aktif.

Neira bisa panggil ini kapan saja untuk tahu:
- Nama aplikasi yang sedang buka
- Process name-nya

Strategi: psutil list semua proses, filter ke yang "user-facing" (bukan background service).
EnumWindows untuk judul window dijalankan dari dalam proses Neira (bukan subprocess),
sehingga bisa akses desktop session dengan benar.
"""

import ctypes
import platform
import sys

for _s in (sys.stdout, sys.stderr):
    if hasattr(_s, "reconfigure"):
        try:
            _s.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

_SYSTEM = platform.system()

# Process system/background yang tidak perlu dilaporkan
_SKIP_PROCS = {
    "system", "system idle process", "registry", "memcompression",
    "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
    "svchost.exe", "runtimebroker.exe", "taskhostw.exe", "spoolsv.exe",
    "dwm.exe", "winlogon.exe", "fontdrvhost.exe", "wudfhost.exe",
    "searchhost.exe", "searchindexer.exe", "searchprotocolhost.exe",
    "searchfilterhost.exe", "shellexperiencehost.exe",
    "startmenuexperiencehost.exe", "applicationframehost.exe",
    "textinputhost.exe", "securityhealthsystray.exe", "securityhealthservice.exe",
    "msmpseng.exe", "nissrv.exe", "mpdefendercoreservice.exe",
    "sgrmbroker.exe", "wsnapperbroker.exe", "sgrm.exe",
    "wmiregistrationservice.exe", "wmiprvse.exe",
    "nvdisplay.container.exe", "nvtelemetrycontainer.exe",
    "audiodg.exe", "rtkntservice64.exe", "ravbg64.exe", "rtkngui64.exe",
    "conhost.exe", "ctfmon.exe", "dllhost.exe", "sihost.exe",
    "usoclient.exe", "uhssvc.exe", "wstoastnotification.exe",
    "wsnatepushservice.exe", "aggregatorhost.exe", "bingsvc.exe",
    "kinonisvc.exe", "hpprintscandoctorservice.exe",
    "adminservice.exe", "dphost.exe", "eppcmon.exe",
    "python.exe", "pythonw.exe",  # neira sendiri
}

# Nama proses yang jelas user-facing apps
_USER_APP_KEYWORDS = {
    "chrome", "firefox", "msedge", "brave", "opera",
    "spotify", "discord", "telegram", "whatsapp", "signal", "slack",
    "zoom", "msteams", "skype",
    "code", "cursor", "notepad", "notepad++", "sublime",
    "explorer", "winword", "excel", "powerpnt", "onenote", "outlook",
    "vlc", "mpc", "potplayer", "mpv", "wmplayer",
    "steam", "epicgameslauncher", "gog",
    "figma", "blender", "photoshop", "illustrator", "premiere",
    "capcut", "davinci", "obs",
    "wt", "cmd", "powershell", "windowsterminal",
    "postman", "insomnia", "dbeaver",
    "notion", "obsidian",
    "taskmgr", "regedit", "mmc",
    "acrobat", "foxitreader", "sumatrapdf",
    "lineage", "genshin", "valorant",
    "ldplayer", "noxplayer", "bluestacks",
    "ldconsole",
}


def _iter_windows() -> list[tuple[int, str, int]]:
    """Return (hwnd, title, pid) via ctypes EnumWindows.
    
    PENTING: Harus dipanggil dari dalam proses Neira (bukan subprocess) 
    agar bisa akses desktop session yang sama.
    """
    results = []
    if _SYSTEM != "Windows":
        return results
    try:
        user32 = ctypes.windll.user32
        EnumWindows     = user32.EnumWindows
        EnumWindowsProc = ctypes.WINFUNCTYPE(
            ctypes.c_bool,
            ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int),
        )
        GetWindowTextW    = user32.GetWindowTextW
        GetWindowTextLenW = user32.GetWindowTextLengthW
        IsWindowVisible   = user32.IsWindowVisible
        GetWindowLongW    = user32.GetWindowLongW
        GetParent         = user32.GetParent
        GetWindowThreadProcessId = user32.GetWindowThreadProcessId

        GWL_STYLE      = -16
        GWL_EXSTYLE    = -20
        WS_CAPTION     = 0x00C00000  # title bar
        WS_EX_TOOLWINDOW  = 0x00000080  # tool windows = bukan taskbar item
        WS_EX_NOACTIVATE  = 0x08000000

        def _cb(hwnd, _):
            if not IsWindowVisible(hwnd):
                return True
            if GetParent(hwnd) != 0:
                return True

            style   = GetWindowLongW(hwnd, GWL_STYLE)
            exstyle = GetWindowLongW(hwnd, GWL_EXSTYLE)

            # Hanya window dengan title bar (bukan popup/tooltip)
            if not (style & WS_CAPTION):
                return True
            # Skip tool windows (biasanya tray/systray popup)
            if exstyle & WS_EX_TOOLWINDOW:
                return True

            length = GetWindowTextLenW(hwnd)
            if length == 0:
                return True
            buf = ctypes.create_unicode_buffer(length + 1)
            GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value.strip()
            if not title:
                return True

            pid = ctypes.c_ulong(0)
            GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            results.append((hwnd, title, pid.value))
            return True

        EnumWindows(EnumWindowsProc(_cb), 0)
    except Exception as e:
        print(f"[list_open_windows] EnumWindows error: {e}")
    return results


def _is_user_app(proc_name: str) -> bool:
    """Heuristik: apakah process ini adalah user-facing app?"""
    pn = proc_name.lower().removesuffix(".exe")
    if pn in _SKIP_PROCS:
        return False
    if any(kw in pn for kw in _USER_APP_KEYWORDS):
        return True
    # Process dengan nama yang tidak mengandung kata system/service biasanya app
    skip_words = {"service", "helper", "host", "broker", "handler",
                  "agent", "daemon", "updater", "crash", "monitor"}
    if any(w in pn for w in skip_words):
        return False
    return True


def list_open_windows(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    """Kembalikan daftar aplikasi yang sedang aktif/terbuka."""
    if _SYSTEM != "Windows":
        # Fallback: psutil saja
        if not _PSUTIL:
            return "Tidak dapat mendeteksi aplikasi aktif (psutil tidak tersedia)."

    entries: list[str] = []
    seen_pids: set[int] = set()
    seen_titles: set[str] = set()

    # Method 1: EnumWindows (harus dipanggil dari dalam proses Neira)
    windows = _iter_windows()
    pid_to_proc: dict[int, str] = {}

    if _PSUTIL:
        try:
            for proc in psutil.process_iter(["pid", "name"]):
                pid = proc.info.get("pid")
                name = proc.info.get("name") or ""
                if pid:
                    pid_to_proc[pid] = name
        except Exception:
            pass

    # Bangun daftar dari EnumWindows
    for hwnd, title, pid in windows:
        proc_name = pid_to_proc.get(pid, "")
        proc_lower = proc_name.lower()

        # Skip proses sistem
        if proc_lower in _SKIP_PROCS:
            continue
        if proc_lower.startswith(("antigravity", "neira", "jarvis")):
            continue  # skip diri sendiri

        # Deduplicate
        if pid and pid in seen_pids:
            continue
        title_key = title.lower().strip()
        if title_key in seen_titles:
            continue

        seen_pids.add(pid)
        seen_titles.add(title_key)

        proc_clean = proc_name.lower().removesuffix(".exe") if proc_name else ""
        if proc_clean and proc_clean not in title.lower():
            entries.append(f"• {title}  [{proc_clean}]")
        else:
            entries.append(f"• {title}")

    # Method 2: Fallback psutil jika EnumWindows kosong (subprocess context)
    # Gunakan whitelist keyword — hanya proses yang jelas user-facing
    if not entries and _PSUTIL:
        print("[list_open_windows] EnumWindows kosong, fallback ke psutil whitelist")
        seen_names: set[str] = set()
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = proc.info.get("name") or ""
                stem = pname.lower().removesuffix(".exe")
                # Hanya tampilkan yang ada di whitelist user app keywords
                if not any(kw in stem for kw in _USER_APP_KEYWORDS):
                    continue
                if stem in seen_names:
                    continue
                seen_names.add(stem)
                entries.append(f"• {pname}")
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

    if not entries:
        return "Tidak ada aplikasi aktif yang terdeteksi saat ini."

    result = f"Aplikasi yang sedang aktif ({len(entries)}):\n" + "\n".join(entries)
    print(f"[list_open_windows] {len(entries)} entries found")
    return result


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "list_open_windows",
    "description": (
        "Menampilkan semua aplikasi yang sedang aktif/terbuka di Windows. "
        "WAJIB dipanggil sebelum open_app jika kamu tidak yakin apakah app sudah terbuka. "
        "Panggil juga ketika user bertanya 'aplikasi apa yang sedang buka?', "
        "'apa yang aktif di taskbar?', 'lihat yang sedang terbuka', atau sejenisnya. "
        "Hasil berisi nama window + nama proses untuk identifikasi yang akurat."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {},
        "required": [],
    },
    "handler": list_open_windows,
}
