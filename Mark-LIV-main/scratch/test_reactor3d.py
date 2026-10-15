"""Uji core/reactor3d.py — mesin reaktor multi-mode (classic/quantum/glsl/web3d).

Jalankan dari root repo:
    .venv\\Scripts\\python.exe scratch\\test_reactor3d.py
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, fn) -> None:
    global PASS, FAIL
    try:
        fn()
        PASS += 1
        print(f"  [PASS] {name}")
    except Exception:
        FAIL += 1
        print(f"  [FAIL] {name}")
        traceback.print_exc()


def t_module_imports() -> None:
    import core.reactor3d as r3
    assert hasattr(r3, "ReactorContext")
    assert hasattr(r3, "QuantumReactor")
    assert hasattr(r3, "GlslReactorWidget")
    assert hasattr(r3, "WebReactorWidget")
    assert r3.REACTOR_STYLES == ("classic", "quantum", "glsl", "web3d")


def t_styles_tuple_matches_config() -> None:
    from memory.config_manager import REACTOR_STYLES as CFG
    import core.reactor3d as r3
    assert tuple(CFG) == r3.REACTOR_STYLES, (CFG, r3.REACTOR_STYLES)


def t_context_state_dict_json_safe() -> None:
    import json
    from core.reactor3d import ReactorContext
    ctx = ReactorContext(name="Neira", amp=0.4, speaking=True, v_open=0.7,
                         v_wide=0.2, t=1.5, boot=0.5, shutdown=0.1)
    d = ctx.state_dict()
    json.dumps(d)                       # harus JSON-safe
    assert d["name"] == "Neira"
    assert d["speaking"] is True
    assert 0.39 <= d["amp"] <= 0.41
    assert d["boot"] == 0.5 and d["shut"] == 0.1
    assert d["main"].startswith("#")


def t_style_available_known_and_unknown() -> None:
    from core.reactor3d import style_available
    ok, msg = style_available("classic")
    assert ok and msg == ""
    ok, msg = style_available("quantum")
    assert ok and msg == ""
    ok, msg = style_available("nope")
    assert not ok and msg
    # glsl/web3d: boleh tidak tersedia, tapi pesan harus menjelaskan
    for s in ("glsl", "web3d"):
        ok, msg = style_available(s)
        assert isinstance(ok, bool)
        if not ok:
            assert msg


def t_make_reactor_widget_contract() -> None:
    from PyQt6.QtWidgets import QApplication
    from core.reactor3d import make_reactor_widget, style_available
    app = QApplication.instance() or QApplication([])
    # classic/quantum = painter-based → None
    assert make_reactor_widget("classic") is None
    assert make_reactor_widget("quantum") is None
    # glsl/web3d → widget bila tersedia, None bila tidak
    for s in ("glsl", "web3d"):
        w = make_reactor_widget(s)
        ok, _ = style_available(s)
        if ok:
            assert w is not None, s
            assert hasattr(w, "set_state")
            assert hasattr(w, "set_name")
            w.set_state({"amp": 0.5, "t": 1.0, "boot": 1.0, "shut": 0.0})
            w.set_name("Neira")
            w.deleteLater()
        else:
            assert w is None, s
    app.processEvents()


def t_quantum_step_moves_particles() -> None:
    from core.reactor3d import QuantumReactor, ReactorContext
    qr = QuantumReactor(n_particles=50, seed=3)
    ctx = ReactorContext(amp=0.5, speaking=True)
    before = [list(p) for p in qr._parts]
    for _ in range(30):
        qr.step(1 / 60, ctx)
    moved = sum(1 for a, b in zip(before, qr._parts) if a[0] != b[0])
    assert moved == 50, moved        # semua partikel harus bergerak
    # shutdown menyusutkan radius orbit
    ctx.shutdown = 1.0
    r0 = qr._parts[0][1]
    for _ in range(60):
        qr.step(1 / 60, ctx)
    assert qr._parts[0][1] < r0


def t_quantum_sonar_on_voice_burst() -> None:
    from core.reactor3d import QuantumReactor, ReactorContext
    qr = QuantumReactor(n_particles=10, seed=1)
    ctx = ReactorContext(amp=0.0)
    qr.step(0.016, ctx)
    assert not qr._sonars
    ctx.amp = 0.5                       # ledakan suara tajam
    qr.step(0.016, ctx)
    assert qr._sonars, "burst suara harus memunculkan sonar ring"
    # sonar menua dan dibuang
    for _ in range(100):
        qr.step(0.016, ReactorContext(amp=0.0))
    assert not qr._sonars


def t_quantum_paint_offscreen() -> None:
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QApplication
    from core.reactor3d import QuantumReactor, ReactorContext
    app = QApplication.instance() or QApplication([])
    img = QImage(320, 240, QImage.Format.Format_RGB32)
    img.fill(0)
    qr = QuantumReactor(n_particles=60, seed=2)
    ctx = ReactorContext(name="Neira", amp=0.3, speaking=True, boot=0.4)
    p = QPainter(img)
    assert p.isActive()
    qr.step(0.016, ctx)
    qr.paint(p, __import__("PyQt6.QtCore", fromlist=["QRectF"]).QRectF(0, 0, 320, 240), ctx)
    p.end()
    # pastikan ada piksel non-background yang tergambar
    from PyQt6.QtGui import QColor
    bg = QColor(ctx.bg).rgb()
    changed = 0
    for y in range(0, 240, 8):
        for x in range(0, 320, 8):
            if img.pixel(x, y) != bg:
                changed += 1
    assert changed > 20, f"hanya {changed} piksel berubah"


def t_quantum_paint_full_lifecycle() -> None:
    """Paint pada tiap fase boot/shutdown tidak boleh melempar error."""
    from PyQt6.QtCore import QRectF
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QApplication
    from core.reactor3d import QuantumReactor, ReactorContext
    app = QApplication.instance() or QApplication([])
    img = QImage(200, 200, QImage.Format.Format_RGB32)
    qr = QuantumReactor(n_particles=40, seed=5)
    rect = QRectF(0, 0, 200, 200)
    for boot in (0.0, 0.3, 0.88, 1.0):
        for shut in (0.0, 0.5, 1.0):
            ctx = ReactorContext(amp=0.4, speaking=True, boot=boot, shutdown=shut)
            p = QPainter(img)
            qr.step(0.016, ctx)
            qr.paint(p, rect, ctx)
            p.end()


def t_ease_functions() -> None:
    from core.reactor3d import _ease_out_back, _ease_out_cubic
    assert abs(_ease_out_cubic(0.0)) < 1e-9
    assert abs(_ease_out_cubic(1.0) - 1.0) < 1e-9
    assert _ease_out_back(1.0) > 0.99      # overshoot sebelum settle di 1
    assert _ease_out_back(0.5) > 0.5


def t_config_roundtrip() -> None:
    import json
    from memory.config_manager import (get_reactor_style, save_reactor_style,
                                       load_api_keys)
    prev = load_api_keys().get("reactor_style", None)
    try:
        save_reactor_style("glsl")
        assert get_reactor_style() == "glsl"
        save_reactor_style("web3d")
        assert get_reactor_style() == "web3d"
        save_reactor_style("bogus")            # jatuh ke default
        assert get_reactor_style() == "quantum"
    finally:
        save_reactor_style(prev if prev in ("classic", "quantum", "glsl", "web3d")
                           else "quantum")
        json.dumps(load_api_keys())            # config tetap valid


def t_html_asset_exists() -> None:
    import core.reactor3d as r3
    assert r3._HTML_PATH.exists(), f"{r3._HTML_PATH} hilang"
    html = r3._HTML_PATH.read_text(encoding="utf-8")
    for token in ("three.min.js", "UnrealBloomPass.js", "__reactorState",
                  "IcosahedronGeometry", "TorusGeometry"):
        assert token in html, token


def t_ui_wiring_exists() -> None:
    """Kontrak antara ui.py dan reactor3d harus tetap utuh."""
    src = (ROOT / "ui.py").read_text(encoding="utf-8")
    for token in ("set_reactor_style", "begin_shutdown", "_reactor_ctx",
                  "_cycle_reactor_style", "_refresh_reactor_btn"):
        assert token in src, token
    msrc = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "self.ui.begin_shutdown()" in msrc


def main() -> int:
    print("== reactor3d: mesin reaktor multi-mode ==")
    check("modul mengimpor bersih", t_module_imports)
    check("REACTOR_STYLES cocok dengan config_manager", t_styles_tuple_matches_config)
    check("ReactorContext.state_dict JSON-safe", t_context_state_dict_json_safe)
    check("style_available menangani gaya dikenal/tidak", t_style_available_known_and_unknown)
    check("make_reactor_widget memenuhi kontrak", t_make_reactor_widget_contract)
    check("QuantumReactor.step menggerakkan partikel", t_quantum_step_moves_particles)
    check("sonar muncul pada ledakan suara", t_quantum_sonar_on_voice_burst)
    check("QuantumReactor.paint offscreen", t_quantum_paint_offscreen)
    check("paint aman di semua fase boot/shutdown", t_quantum_paint_full_lifecycle)
    check("fungsi easing konsisten", t_ease_functions)
    check("config reactor_style round-trip", t_config_roundtrip)
    check("asset reactor.html lengkap", t_html_asset_exists)
    check("wiring ui.py/main.py utuh", t_ui_wiring_exists)

    print(f"\nTOTAL: {PASS} PASS / {FAIL} FAIL")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
