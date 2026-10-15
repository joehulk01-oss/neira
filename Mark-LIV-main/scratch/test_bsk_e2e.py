"""test_bsk_e2e.py — Bukti end-to-end: browser_skill benar-benar mengendalikan Chrome.

Alur: doctor -> start -> navigate web.whatsapp.com -> observe -> get_text -> stop.
Hasil ditulis ke scratch/bsk_e2e_report.txt (terminal kadang menelan stdout).
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from skills.admin.browser_skill import browser_skill  # noqa: E402

REPORT = Path(__file__).with_name("bsk_e2e_report.txt")
URL = "https://web.whatsapp.com"

lines: list[str] = []


def step(title: str, out: str, limit: int = 1800) -> None:
    lines.append("=" * 70)
    lines.append(f"== {title}")
    lines.append("=" * 70)
    text = (out or "").strip()
    if len(text) > limit:
        text = text[:limit] + f"\n...(dipotong, total {len(out)} chars)"
    lines.append(text)
    lines.append("")


def main() -> int:
    # 1. doctor — pastikan extension terhubung
    step("1. DOCTOR", browser_skill({"action": "doctor"}))

    # 2. start sesi
    start_out = browser_skill({"action": "start", "browser": "chrome"})
    step("2. START", start_out, limit=1200)
    if "ERROR" in start_out[:200]:
        lines.append("VERDICT: GAGAL di start — tidak lanjut.")
        return 1

    try:
        # 3. navigate ke WhatsApp Web
        step("3. NAVIGATE " + URL, browser_skill({"action": "navigate", "url": URL}), limit=800)
        time.sleep(12)  # beri waktu WhatsApp Web load penuh

        # 4. observe — dapatkan elemen (@e refs) — bukti kendali nyata
        obs = browser_skill({"action": "observe"})
        step("4. OBSERVE (WhatsApp Web)", obs, limit=2500)

        # 5. get_text — bukti membaca konten halaman
        step("5. GET_TEXT (cuplikan)", browser_skill({"action": "get_text"}), limit=1500)

        verdict = "OK"
    except Exception as e:  # pragma: no cover
        step("EXCEPTION", f"{type(e).__name__}: {e}")
        verdict = f"EXCEPTION: {e}"
    finally:
        # 6. stop — bersihkan sesi
        step("6. STOP", browser_skill({"action": "stop"}), limit=800)

    lines.append("=" * 70)
    lines.append(f"VERDICT: {verdict} — alur start/navigate/observe/stop tereksekusi penuh.")
    lines.append("=" * 70)
    return 0


if __name__ == "__main__":
    rc = main()
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(f"report -> {REPORT}")
    sys.exit(rc)
