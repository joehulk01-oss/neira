# check_bsk_state.py — diagnosis nyata: registry policy + profil browser + daemon
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

IDS = {"hhcmgoofomhgciiibhipgmgkgnoenaoi", "emacgiaaaiojkkpkddmmdfhmokgmnikg"}
out = []

# 1. Registry policy (HKCU + HKLM)
try:
    import winreg
    for hive_name, hive in (("HKCU", winreg.HKEY_CURRENT_USER), ("HKLM", winreg.HKEY_LOCAL_MACHINE)):
        for browser, sub in (
            ("chrome", r"Software\Policies\Google\Chrome\ExtensionInstallForcelist"),
            ("edge", r"Software\Policies\Microsoft\Edge\ExtensionInstallForcelist"),
        ):
            try:
                with winreg.OpenKey(hive, sub) as k:
                    val, _ = winreg.QueryValueEx(k, "1")
                    out.append(f"POLICY {hive_name} {browser}: {val}")
            except FileNotFoundError:
                out.append(f"POLICY {hive_name} {browser}: (tidak ada)")
            except Exception as e:
                out.append(f"POLICY {hive_name} {browser}: ERROR {e}")
except Exception as e:
    out.append(f"winreg gagal: {e}")

# 2. Profil browser — extension terpasang?
loc = Path(os.environ.get("LOCALAPPDATA", ""))
for b in ("Google/Chrome/User Data", "Microsoft/Edge/User Data"):
    root = loc / b
    if not root.exists():
        out.append(f"PROFILE {b}: tidak ada")
        continue
    profs = ["Default"] + [d.name for d in root.glob("Profile *")]
    for pname in profs:
        pref = root / pname / "Preferences"
        if not pref.exists():
            continue
        try:
            data = json.loads(pref.read_text(encoding="utf-8", errors="replace"))
            s = (data.get("extensions") or {}).get("settings") or {}
            hit = sorted(i for i in s if i in IDS)
            out.append(f"PROFILE {b}/{pname}: bsk-ext={'TERPASANG ' + str(hit) if hit else 'belum'} (total ext {len(s)})")
        except Exception as e:
            out.append(f"PROFILE {b}/{pname}: read-error {e}")

# 3. Daemon & koneksi via bsk CLI
import shutil
exe = shutil.which("bsk") or os.path.expandvars(r"%USERPROFILE%\.local\bin\bsk.exe")
if exe and Path(exe).exists():
    import subprocess
    try:
        r = subprocess.run([exe, "status", "--json"], capture_output=True, text=True, timeout=30)
        out.append(f"BSK STATUS: {(r.stdout or r.stderr)[:400]}")
    except Exception as e:
        out.append(f"BSK STATUS ERROR: {e}")
else:
    out.append("BSK CLI: tidak ditemukan")

report = "\n".join(out)
Path(__file__).with_name("bsk_state_report.txt").write_text(report, encoding="utf-8")
print(report)
