# -*- coding: utf-8 -*-
"""Smoke test ModelPickerDialog (ui.py) — offscreen, tanpa event loop.

Jalankan dari root repo:
    .venv\\Scripts\\python.exe scratch\\test_model_picker.py
"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PyQt6.QtWidgets import QApplication  # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)

from ui import ModelPickerDialog  # noqa: E402

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        print(f"  FAIL {name}")


IDS = [
    "ag/gemini-3.8-flash-medium",
    "ag/mimo-v2.6-pro",
    "openrouter/claude-sonnet",
    "openrouter/deepseek-v3",
    "local/llama-3.3-70b",
]
CUR = "ag/mimo-v2.6-pro"

print("== 1. konstruksi & isi awal ==")
dlg = ModelPickerDialog(IDS, current=CUR, base="http://127.0.0.1:20128", parent=None)
dlg.show()                    # offscreen: perlu show() agar fokus benar-benar diberikan
app.processEvents()
check("konstruksi dialog ok", dlg is not None)
check("resizable (min 520x420)", dlg.minimumWidth() >= 520 and dlg.minimumHeight() >= 420)
check("daftar awal tampil semua", dlg._list.count() == len(IDS))
check("status menampilkan jumlah", f"{len(IDS)}" in dlg._status.text())
check("selected kosong sebelum pilih", dlg.selected == "")
check("fokus di kolom pencarian",
      dlg._search.hasFocus() or dlg.focusWidget() is dlg._search)

print("== 2. penanda model aktif ==")
texts = [dlg._list.item(i).text() for i in range(dlg._list.count())]
aktif = [t for t in texts if "● AKTIF" in t]
check("model aktif ditandai ● AKTIF", len(aktif) == 1 and CUR in aktif[0])
check("UserRole menyimpan id asli",
      any((dlg._list.item(i).data(0x0100) == CUR) for i in range(dlg._list.count())))

print("== 3. pencarian real-time ==")
dlg._apply_filter("gemini")
check("filter 'gemini' menyaring", dlg._list.count() == 1)
check("filter 'gemini' tepat sasaran", "gemini" in dlg._list.item(0).data(0x0100))
dlg._apply_filter("openrouter")
check("filter 'openrouter' → 2 model", dlg._list.count() == 2)
check("status ikut update", "2 dari 5" in dlg._status.text())
dlg._apply_filter("zzz-tidak-ada")
check("filter kosong → 0 baris", dlg._list.count() == 0)
check("_current_mid aman saat kosong", dlg._current_mid() == "")
dlg._apply_filter("")
check("filter direset → tampil semua lagi", dlg._list.count() == len(IDS))

print("== 4. pemilihan ==")
dlg._apply_filter("deepseek")
check("pilih hasil filter", dlg._current_mid() == "openrouter/deepseek-v3")
dlg._pick_selected()
check("selected terisi setelah _pick_selected", dlg.selected == "openrouter/deepseek-v3")
check("dialog accept setelah pilih", dlg.result() == dlg.DialogCode.Accepted)

dlg2 = ModelPickerDialog(IDS, current=CUR, base="", parent=None)
dlg2._apply_filter("llama")
it = dlg2._list.item(0)
dlg2._on_double_click(it)
check("double-click memilih model", dlg2.selected == "local/llama-3.3-70b")

dlg3 = ModelPickerDialog(IDS, current=CUR, base="", parent=None)
dlg3._apply_filter("flash")
dlg3._pick_selected()
check("Enter/_pick_selected memakai id asli (bukan label AKTIF)",
      dlg3.selected == "ag/gemini-3.8-flash-medium")

print("== 5. aturan role: tanpa nama engine internal ==")
vis = dlg.windowTitle() + dlg._search.placeholderText() + dlg._status.text()
vis += " ".join(dlg._list.item(i).text() for i in range(dlg._list.count()))
check("label dialog bebas 'Hermes'", "Hermes" not in vis and "HERMES" not in vis)

print(f"\nRESULT: {PASS} PASS {FAIL} FAIL")
sys.exit(1 if FAIL else 0)
