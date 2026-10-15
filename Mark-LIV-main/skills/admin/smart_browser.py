"""
Neira Smart Browser Skill (OpenMuse-style Web Automation).

Allows Neira, Gemini Live, and Hermes to autonomously browse the web,
fill forms, click buttons using simple element IDs (#1, #2), and inspect
interactive web elements without complex CSS selectors.

Features:
- persistent session (cookies & login preserved)
- element ID tagging for LLM ease
- takeover mode for CAPTCHA/OTP
- screenshot trace capability
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent

BASE_DIR = _base_dir()
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

try:
    from core.smart_browser_engine import get_browser
except ImportError:
    get_browser = None


def smart_browser(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """
    Main handler for smart_browser skill.
    Supported actions:
      - navigate (url)
      - snapshot ()
      - click (element_id)
      - type (element_id, text, clear, press_enter)
      - select (element_id, value)
      - screenshot (filename)
      - take_control ()
    """
    parameters = parameters or {}
    action = str(parameters.get("action") or "snapshot").strip().lower()

    if get_browser is None:
        return "Modul core.smart_browser_engine belum tersedia."

    try:
        browser = get_browser()
    except Exception as e:
        return f"Gagal menginisialisasi browser engine: {str(e)}"

    if action == "navigate":
        url = str(parameters.get("url") or "").strip()
        if not url:
            return "Mohon berikan 'url' untuk dituju."
        res = browser.navigate(url)
        return (
            f"Berhasil membuka halaman: {res['url']}\n"
            f"Judul: {res['title']}\n\n"
            f"{res['text_summary']}"
        )

    elif action == "snapshot":
        res = browser.snapshot()
        return (
            f"Halaman Aktif: {res['url']}\n"
            f"Judul: {res['title']}\n\n"
            f"{res['text_summary']}"
        )

    elif action == "click":
        elem_id = parameters.get("element_id")
        if elem_id is None:
            return "Mohon berikan 'element_id' (#nomor) yang ingin diklik."
        try:
            elem_id = int(elem_id)
        except ValueError:
            return f"element_id harus berupa angka bulat, didapat: {elem_id}"

        res = browser.click(elem_id)
        report = f"Hasil Aksi: {res['action']} ({res['status']})\n\n"
        if "new_snapshot" in res:
            report += res["new_snapshot"]["text_summary"]
        return report

    elif action in ("type", "fill"):
        elem_id = parameters.get("element_id")
        text = str(parameters.get("text") or "")
        clear = bool(parameters.get("clear", True))
        press_enter = bool(parameters.get("press_enter", False))

        if elem_id is None:
            return "Mohon berikan 'element_id' (#nomor) input field."
        try:
            elem_id = int(elem_id)
        except ValueError:
            return f"element_id harus berupa angka bulat, didapat: {elem_id}"

        res = browser.type_text(elem_id, text, clear=clear, press_enter=press_enter)
        report = f"Hasil Aksi: {res['action']} ({res['status']})\n\n"
        if "new_snapshot" in res:
            report += res["new_snapshot"]["text_summary"]
        return report

    elif action == "select":
        elem_id = parameters.get("element_id")
        val = str(parameters.get("value") or "")
        if elem_id is None or not val:
            return "Mohon berikan 'element_id' dan 'value' opsi dropdown."
        try:
            elem_id = int(elem_id)
        except ValueError:
            return f"element_id harus berupa angka bulat, didapat: {elem_id}"

        res = browser.select_option(elem_id, val)
        report = f"Hasil Aksi: {res['action']} ({res['status']})\n\n"
        if "new_snapshot" in res:
            report += res["new_snapshot"]["text_summary"]
        return report

    elif action == "screenshot":
        filename = str(parameters.get("filename") or "")
        path = browser.screenshot(filename)
        return f"Tangkapan layar browser berhasil disimpan di: {path}"

    elif action in ("take_control", "takeover"):
        return browser.take_control()

    else:
        return (
            f"Aksi '{action}' tidak dikenal. "
            f"Aksi yang tersedia: navigate | snapshot | click | type | select | screenshot | take_control."
        )


TOOL = {
    "name": "smart_browser",
    "description": (
        "Autonomous interactive web browser (OpenMuse style). Navigates websites, reads "
        "interactive accessibility elements labeled with clean numeric IDs (#1, #2), fills form inputs, "
        "clicks buttons, and supports user takeover for Captcha or OTP. Use this for complex web forms, "
        "searching sites, and interactive web tasks."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Aksi yang ingin dilakukan: navigate | snapshot | click | type | select | screenshot | take_control",
                "enum": ["navigate", "snapshot", "click", "type", "select", "screenshot", "take_control"]
            },
            "url": {
                "type": "STRING",
                "description": "URL website yang ingin dibuka (untuk action=navigate)."
            },
            "element_id": {
                "type": "INTEGER",
                "description": "Nomor ID elemen (#1, #2, dst) dari hasil snapshot yang ingin diklik atau diisi."
            },
            "text": {
                "type": "STRING",
                "description": "Teks yang ingin diisikan ke kolom input (untuk action=type)."
            },
            "value": {
                "type": "STRING",
                "description": "Value opsi dropdown yang ingin dipilih (untuk action=select)."
            },
            "press_enter": {
                "type": "BOOLEAN",
                "description": "Apakah perlu menekan Enter setelah mengetik (opsional, default: false)."
            },
            "filename": {
                "type": "STRING",
                "description": "Nama file screenshot (opsional)."
            }
        },
        "required": ["action"]
    },
    "handler": smart_browser,
    "behavior": "BLOCKING",
    "scheduling": "WHEN_IDLE",
    "category": "admin"
}
