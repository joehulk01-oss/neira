"""Offscreen smoke test — Neira UI overhaul (A: font settings, B: modern restyle).

Run:  .venv\\Scripts\\python.exe scratch\\test_ui_restyle.py
Covers: module import, QFont shim (family+scale), apply_ui_font colour overlay,
LogWidget chat-row blocks, MetricBar flat paint, CustomizeOverlay font widgets
+ _save() keys, and the border-radius sweep.
"""
import os
import re
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import ui                                    # noqa: E402
from PyQt6.QtWidgets import QApplication     # noqa: E402

app = QApplication.instance() or QApplication(sys.argv)
ok, fail = [], []


def check(name: str, cond: bool, detail: str = ""):
    (ok if cond else fail).append(f"{name}{(' — ' + detail) if detail and not cond else ''}")


# ── 1. QFont shim: family remap + scale ──────────────────────────────────────
ui.apply_ui_font("Courier New", 100, "")
f = ui.QFont("Courier New", 10)
check("shim default family", f.family() == "Courier New", f.family())
check("shim default scale", f.pointSize() == 10, str(f.pointSize()))

ui.apply_ui_font("Consolas", 120, "")
f = ui.QFont("Courier New", 10)
check("shim family remap", f.family() == "Consolas", f.family())
check("shim scale 120%", f.pointSize() == 12, str(f.pointSize()))
f2 = ui.QFont("Consolas", 8)          # base-mono → also remapped
check("shim remaps Consolas too", f2.family() == "Consolas", f2.family())
f3 = ui.QFont("Arial", 9)             # non-mono family untouched
check("shim leaves Arial", f3.family() == "Arial", f3.family())

# ── 2. Font colour overlay + clear roundtrip ─────────────────────────────────
default_text = ui.current_palette()["TEXT"]
ui.apply_ui_font("Consolas", 120, "#ff00ff")
check("font colour override", ui.C.TEXT == "#ff00ff", ui.C.TEXT)
ui.apply_ui_font("Consolas", 120, "")          # clear → accent-derived again
check("font colour cleared", ui.C.TEXT == default_text,
      f"{ui.C.TEXT} != {default_text}")

# ── 3. Accent roundtrip still healthy ────────────────────────────────────────
old = ui.current_palette()
check("accent apply", ui.apply_ui_accent("#ff6b00"))
ui.retheme_all_widgets(old, ui.current_palette())
check("accent restore", ui.apply_ui_accent(ui.DEFAULT_UI_COLOR))
ui.retheme_all_widgets(old, ui.current_palette())

# ── 4. LogWidget: chat rows become blocks ────────────────────────────────────
log = ui.LogWidget()
log.append_log("You: halo neira")
log.append_log("Neira: siap sir")
deadline = time.time() + 2.0
while time.time() < deadline and (log._typing or log._queue):
    app.processEvents()
    time.sleep(0.01)
app.processEvents()
doc = log.document()
txt = doc.toPlainText()
check("log typed both lines", "halo neira" in txt and "siap sir" in txt, txt[:80])
check("log one block per row", doc.blockCount() == 2, str(doc.blockCount()))
check("log radius modern", "border-radius: 10px" in log.styleSheet())

# ── 5. MetricBar flat paint (construct + render offscreen) ───────────────────
bar = ui.MetricBar("CPU", ui.C.PRI)
bar.resize(120, 38)
bar.set_value(42.0, "42%")
check("metricbar renders", not bar.grab().isNull())

# ── 6. CustomizeOverlay font widgets + save keys ─────────────────────────────
ov = ui.CustomizeOverlay(ui_font_family="Consolas", ui_font_color="#00ff88",
                         ui_font_scale=110)
check("overlay combo", ov._font_family.currentText() == "Consolas",
      ov._font_family.currentText())
check("overlay colour", ov._font_color_input.text() == "#00ff88")
check("overlay scale", ov._font_scale.value() == 110, str(ov._font_scale.value()))
saved: dict = {}
ov.saved.connect(saved.update)
ov._save()
for k in ("ui_font_family", "ui_font_color", "ui_font_scale"):
    check(f"save key {k}", k in saved, ",".join(saved))
check("save values", saved.get("ui_font_family") == "Consolas"
      and saved.get("ui_font_scale") == 110, str(saved.get("ui_font_scale")))

# ── 7. Radius sweep: no old small radii left in source ───────────────────────
src = (ROOT / "ui.py").read_text(encoding="utf-8")
old_r = re.findall(r"border-radius:\s*[2345]px", src)
check("old radii gone", not old_r, str(old_r[:5]))
check("6px is the baseline", src.count("border-radius: 6px") >= 50,
      str(src.count("border-radius: 6px")))

# ── verdict ──────────────────────────────────────────────────────────────────
print(f"PASS {len(ok)}  FAIL {len(fail)}")
for m in fail:
    print("  FAIL:", m)
sys.exit(1 if fail else 0)
