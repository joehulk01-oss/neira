"""
core/reactor3d.py — Mesin visual reaktor HUD multi-mode (Neira).

Tiga gaya reaktor modern + satu gaya klasik yang tetap di ui.py:

  * "classic" — reaktor QPainter 2D lama (ui.HudCanvas._paint_core). Tidak
    disentuh modul ini; dicatat hanya untuk konfigurasi.
  * "quantum" — Konsep A: faux-3D di QPainter murni. Cincin elips bertumpuk
    (proyeksi cincin 3D yang dimiringkan), 260 partikel orbital dengan
    perspektif + jejak cahaya, inti plasma volumetrik, dan ring sonar yang
    memuai mengikuti suara. Tanpa dependensi tambahan — jalan di mana saja.
  * "glsl"    — Konsep B: true-3D di GPU via QOpenGLWidget + fragment shader
    raymarch (bola plasma + 3 torus orbit + glow akumulatif). Butuh
    PyQt6.QtOpenGLWidgets (sudah bawaan PyQt6).
  * "web3d"   — Konsep C: three.js + UnrealBloomPass di QWebEngineView
    (assets/web_background/reactor.html). Butuh paket PyQt6-WebEngine.

Semua gaya berbagi ReactorContext (state audio/viseme/status + progres animasi
boot & shutdown) sehingga pergantian gaya tidak mengubah logika ui.py.

Kontrak untuk widget (glsl/web3d):
    widget.set_state(dict)   — dipanggil tiap frame dari HudCanvas._step()
    widget.set_name(str)     — label nama asisten (opsional)

Uji: scratch/test_reactor3d.py
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from PyQt6.QtCore import QLineF, QPointF, QRectF, Qt, QTimer, QUrl
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient,
    QVector3D,
)
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget

# ── Deteksi dependensi opsional (gagal = gaya tidak tersedia, bukan crash) ──
try:
    from PyQt6.QtOpenGLWidgets import QOpenGLWidget
    _HAVE_GL = True
except Exception:                                   # pragma: no cover
    QOpenGLWidget = QWidget                          # placeholder agar class def valid
    _HAVE_GL = False

REACTOR_STYLES: Tuple[str, ...] = ("classic", "quantum", "glsl", "web3d")

STYLE_LABELS: Dict[str, str] = {
    "classic": "CLASSIC 2D",
    "quantum": "QUANTUM 3D",
    "glsl":    "GLSL 3D (GPU)",
    "web3d":   "WEB 3D (three.js)",
}

_HTML_PATH = Path(__file__).resolve().parent.parent / "assets" / "web_background" / "reactor.html"


# ═══════════════════════════════════════════════════════════════════════════
#  State bersama
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class ReactorContext:
    """Satu frame state untuk engine reaktor mana pun.

    Semua nilai sudah halus (smoothed) — engine cukup menggambar apa adanya.
    `boot` 0→1 saat start (spark → spin-up → shockwave → idle),
    `shutdown` 0→1 saat aplikasi ditutup (implosi → padam).
    """
    name: str = ""
    amp: float = 0.0            # level audio 0..1 (sudah dihaluskan)
    speaking: bool = False
    muted: bool = False
    state: str = "INITIALISING"
    v_open: float = 0.0         # viseme: keterbukaan mulut 0..1
    v_wide: float = 0.0         # viseme: lebar mulut 0..1
    t: float = 0.0              # fase global (detik, terintegrasi)
    boot: float = 1.0           # 0..1 progres animasi boot
    shutdown: float = 0.0       # 0..1 progres animasi shutdown
    main: QColor = field(default_factory=lambda: QColor("#22d3ee"))
    acc: QColor = field(default_factory=lambda: QColor("#a78bfa"))
    bg: QColor = field(default_factory=lambda: QColor("#04070d"))
    white: QColor = field(default_factory=lambda: QColor("#eef4ff"))

    def state_dict(self) -> Dict[str, Any]:
        """Ringkasan JSON-safe untuk engine berbasis web."""
        return {
            "name": self.name, "amp": round(self.amp, 3),
            "speaking": bool(self.speaking), "muted": bool(self.muted),
            "state": self.state, "open": round(self.v_open, 3),
            "wide": round(self.v_wide, 3), "t": round(self.t, 2),
            "boot": round(self.boot, 3), "shut": round(self.shutdown, 3),
            "main": self.main.name(), "acc": self.acc.name(),
            "bg": self.bg.name(), "white": self.white.name(),
        }


def style_available(style: str) -> Tuple[bool, str]:
    """(tersedia, pesan) — pesan menjelaskan cara mengaktifkan bila tidak."""
    if style in ("classic", "quantum"):
        return True, ""
    if style == "glsl":
        if _HAVE_GL:
            return True, ""
        return False, "PyQt6.QtOpenGLWidgets tidak tersedia di lingkungan ini"
    if style == "web3d":
        try:
            import importlib.util as _ilu
            if _ilu.find_spec("PyQt6.QtWebEngineWidgets") is not None:
                return True, ""
        except Exception:
            pass
        return False, "PyQt6-WebEngine belum terpasang — jalankan: pip install PyQt6-WebEngine"
    return False, "gaya reaktor tidak dikenal"


def make_reactor_widget(style: str, parent: Optional[QWidget] = None) -> Optional[QWidget]:
    """Bangun widget engine untuk gaya berbasis widget, atau None bila tidak
    tersedia / gaya painter-based (classic & quantum)."""
    ok, _ = style_available(style)
    if not ok:
        return None
    if style == "glsl":
        return GlslReactorWidget(parent)
    if style == "web3d":
        return WebReactorWidget(parent)
    return None


# ═══════════════════════════════════════════════════════════════════════════
#  Konsep A — QuantumReactor: faux-3D di QPainter
# ═══════════════════════════════════════════════════════════════════════════

def _ease_out_back(x: float) -> float:
    c1, c3 = 1.70158, 2.70158
    x = max(0.0, min(1.0, x))
    return 1.0 + c3 * (x - 1.0) ** 3 + c1 * (x - 1.0) ** 2


def _ease_out_cubic(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1.0 - (1.0 - x) ** 3


class QuantumReactor:
    """Reaktor faux-3D: cincin elips bertumpuk + partikel orbital + plasma.

    Prinsip yang sama dengan _paint_core lama — setiap gerakan berarti:
    kecepatan cincin = state, ukuran partikel = kedalaman, sonar = suara.
    Kedalaman datang dari proyeksi perspektif (f/(f+z)) pada partikel dan
    dari elips yang dimiringkan pada cincin, digambar back-to-front.
    """

    # (radius frac, tilt derajat, spin derajat/detik, tebal, alpha, slot warna)
    RINGS: Tuple[Tuple[float, float, float, float, float, str], ...] = (
        (0.960, 62,  13.0, 2.2, 0.80, "acc"),
        (0.855, 38, -18.0, 1.6, 0.60, "main"),
        (0.760, 71,  23.0, 2.0, 0.70, "acc"),
        (0.640, 29, -10.0, 1.4, 0.50, "main"),
        (0.520, 55,  28.0, 1.8, 0.65, "acc"),
        (0.410, 45, -21.0, 1.3, 0.45, "main"),
    )

    def __init__(self, n_particles: int = 260, seed: int = 7):
        self._rnd = random.Random(seed)
        self._parts: List[List[float]] = []
        for _ in range(n_particles):
            self._parts.append([
                self._rnd.uniform(0, math.tau),     # [0] theta orbit
                self._rnd.uniform(0.30, 1.25),      # [1] radius faktor
                self._rnd.uniform(0, math.pi),      # [2] inklinasi orbit
                self._rnd.uniform(0.10, 0.55)       # [3] laju orbit
                * (1 if self._rnd.random() < 0.7 else -1),
                self._rnd.uniform(0.5, 1.6),        # [4] ukuran dasar
                0.0, 0.0,                           # [5..6] posisi layar sebelumnya (trail)
            ])
        self._sonars: List[List[float]] = []        # [usia, r_max]
        self._prev_amp = 0.0

    # ── simulasi ────────────────────────────────────────────────────────────
    def step(self, dt: float, ctx: ReactorContext) -> None:
        dt = max(0.0, min(0.1, float(dt)))
        live = (ctx.speaking or ctx.amp > 0.04) and not ctx.muted
        speed = 1.0 + (1.9 if ctx.state in ("THINKING", "PROCESSING") else 0.0) \
                   + (1.2 if ctx.speaking else 0.0) + ctx.amp * 1.5
        speed *= max(0.0, 1.0 - ctx.shutdown * 0.9)

        for pt in self._parts:
            pt[0] += pt[3] * dt * speed
            if ctx.shutdown > 0.0:
                # implosi: orbit merapat ke inti sambil melambat
                pt[1] *= (1.0 - 0.9 * dt * ctx.shutdown)

        # Sonar: satu ring memuai tiap ledakan energi suara (naik tajam).
        if live and ctx.amp > self._prev_amp + 0.045 and ctx.amp > 0.12:
            if len(self._sonars) < 8:
                self._sonars.append([0.0, 1.25 + 0.9 * ctx.amp])
        self._prev_amp = max(self._prev_amp - dt * 0.8, 0.0) \
            if ctx.amp <= self._prev_amp else ctx.amp

        for s in self._sonars:
            s[0] += dt
        self._sonars = [s for s in self._sonars if s[0] < 1.1]

    # ── gambar ──────────────────────────────────────────────────────────────
    def paint(self, p: QPainter, rect: QRectF, ctx: ReactorContext) -> None:
        cx, cy = rect.center().x(), rect.center().y()
        r = min(rect.width(), rect.height()) / 2.0

        # Fase animasi: boot membesar dari 0 dengan overshoot, shutdown
        # menyusutkan segalanya ke titik.
        boot = _ease_out_back(min(1.0, ctx.boot / 0.80)) if ctx.boot < 1.0 else 1.0
        bright = _ease_out_cubic(min(1.0, ctx.boot / 0.55)) if ctx.boot < 1.0 else 1.0
        sh = ctx.shutdown
        grow = boot * (1.0 - 0.85 * sh * sh)
        amp = ctx.amp
        live = (ctx.speaking or amp > 0.04) and not ctx.muted

        def blend(col: QColor, a: float) -> QColor:
            k = max(0.0, min(1.0, a * bright))
            bg = ctx.bg
            return QColor(int(bg.red()   + (col.red()   - bg.red())   * k),
                          int(bg.green() + (col.green() - bg.green()) * k),
                          int(bg.blue()  + (col.blue()  - bg.blue())  * k))

        p.setBrush(Qt.BrushStyle.NoBrush)

        # 1. Atmosfer: dua gradasi radial lembut — kehadiran sebelum detail.
        lift = (1.0 + 0.6 * amp + (0.22 if ctx.speaking else 0.0)) * grow
        p.setPen(Qt.PenStyle.NoPen)
        for gr, a0 in ((r * 0.92, 0.26), (r * 0.46, 0.32)):
            gr *= grow
            if gr < 1:
                continue
            g = QRadialGradient(cx, cy, gr)
            g.setColorAt(0.00, blend(ctx.main, min(0.95, a0 * lift)))
            g.setColorAt(0.42, blend(ctx.main, min(0.95, a0 * lift * 0.5)))
            g.setColorAt(0.80, blend(ctx.main, min(0.95, a0 * lift * 0.15)))
            g.setColorAt(1.00, blend(ctx.main, 0.0))
            p.setBrush(QBrush(g))
            p.drawEllipse(QRectF(cx - gr, cy - gr, gr * 2, gr * 2))
        p.setBrush(Qt.BrushStyle.NoBrush)

        # 2. Cincin 3D bertumpuk — setiap cincin = elips proyeksi orbit yang
        #    dimiringkan, dirotasi pada sumbu 2D-nya. Sisi depan (bawah)
        #    digambar lebih terang dari sisi belakang → kedalaman.
        spin_rate = 1.0 + (1.7 if ctx.state in ("THINKING", "PROCESSING") else 0.0) \
                       + (1.1 if ctx.speaking else 0.0) + amp * 1.2
        spin_rate *= max(0.0, 1.0 - sh)
        for k, (frac, tilt, spin, wid, alp, slot) in enumerate(self.RINGS):
            rx = r * frac * grow
            ry = max(2.0, rx * math.sin(math.radians(tilt)))
            # v_open "membuka" cincin: mulut terbuka = reaktor menguap lebar
            ry *= (1.0 + 0.35 * ctx.v_open * (1 if ctx.speaking else 0))
            rot = ctx.t * spin * spin_rate + k * 37.0
            col = ctx.acc if slot == "acc" else ctx.main
            p.save()
            p.translate(cx, cy)
            p.rotate(rot)
            box = QRectF(-rx, -ry, rx * 2, ry * 2)
            # sisi belakang (atas) — redup
            p.setPen(QPen(blend(col, alp * 0.30), wid))
            p.drawArc(box, 0, 180 * 16)
            # sisi depan (bawah) — terang
            p.setPen(QPen(blend(col, alp), wid))
            p.drawArc(box, 180 * 16, 180 * 16)
            # kilau pendek di sisi depan
            p.setPen(QPen(blend(ctx.white, alp * 0.85), wid * 0.7))
            p.drawArc(box, 180 * 16 + int(rot * 7) % (120 * 16), 34 * 16)
            p.restore()

        # 3. Partikel orbital — perspektif f/(f+z): partikel jauh mengecil &
        #    meredup, partikel dekat membesar, plus jejak gerak.
        f_persp = 2.4
        for pt in self._parts:
            x = math.cos(pt[0]) * pt[1]
            y = math.sin(pt[0]) * pt[1] * math.sin(pt[2])
            z = math.sin(pt[0]) * pt[1] * math.cos(pt[2])
            persp = f_persp / (f_persp + z)
            sx = cx + x * r * 0.92 * grow * persp
            sy = cy + y * r * 0.92 * grow * persp
            depth = max(0.0, min(1.0, (z + 1.3) / 2.6))   # 0 = jauh, 1 = dekat
            size = max(0.6, pt[4] * persp * (1.1 + amp * 1.6))
            alpha = (0.10 + 0.55 * depth) * bright * (1.0 - sh * 0.85)
            if alpha <= 0.01:
                pt[5], pt[6] = sx, sy
                continue
            col = ctx.acc if pt[4] > 1.1 else ctx.main
            if pt[5] or pt[6]:
                p.setPen(QPen(blend(col, alpha * 0.5), max(0.8, size * 0.6)))
                p.drawLine(QLineF(pt[5], pt[6], sx, sy))
            p.setPen(QPen(blend(col, alpha), max(0.8, size)))
            p.drawPoint(QPointF(sx, sy))
            pt[5], pt[6] = sx, sy

        # 4. Inti plasma: gradasi berlapis + denyut mengikuti suara.
        core_r = r * (0.30 + 0.10 * ctx.v_open + 0.07 * amp) * grow * (1.0 - 0.9 * sh)
        if core_r > 2:
            g = QRadialGradient(cx, cy, core_r)
            g.setColorAt(0.00, blend(ctx.white, min(1.0, 0.85 + amp * 0.5)))
            g.setColorAt(0.30, blend(ctx.acc if ctx.speaking else ctx.main, 0.80))
            g.setColorAt(0.72, blend(ctx.main, 0.32))
            g.setColorAt(1.00, blend(ctx.main, 0.0))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(g))
            p.drawEllipse(QRectF(cx - core_r, cy - core_r, core_r * 2, core_r * 2))
            p.setBrush(Qt.BrushStyle.NoBrush)

        # 5. Sonar ring — setiap ledakan suara memancarkan satu ring memuai.
        for s in self._sonars:
            age, r_max = s
            prog = _ease_out_cubic(age / 1.1)
            rad = r * (0.35 + prog * r_max * 0.75)
            a = (1.0 - age / 1.1) * 0.55 * bright
            p.setPen(QPen(blend(ctx.acc if ctx.speaking else ctx.main, a),
                          1.2 + 2.4 * (1.0 - prog)))
            p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))

        # 6. Shockwave boot — satu ring memuai lalu pudar di akhir boot.
        if 0.0 < ctx.boot < 1.0:
            w = abs(ctx.boot - 0.88)
            if w < 0.12:
                rad = r * (0.3 + ctx.boot * 1.5)
                a = (1.0 - w / 0.12) * 0.8
                p.setPen(QPen(blend(ctx.white, a), 2.4))
                p.drawEllipse(QRectF(cx - rad, cy - rad, rad * 2, rad * 2))

        # 7. Garis patah (bolt) menuju inti selama boot — energi menyalakan
        #    reaktor.
        if 0.05 < ctx.boot < 0.65:
            n_bolt = 6
            a = (1.0 - abs(ctx.boot - 0.35) / 0.30) * 0.9
            for i in range(n_bolt):
                ang = math.radians(i * (360.0 / n_bolt) + ctx.t * 40)
                x0, y0 = cx + math.cos(ang) * r * 1.15, cy + math.sin(ang) * r * 1.15
                mx = cx + math.cos(ang + 0.35) * r * 0.62
                my = cy + math.sin(ang + 0.35) * r * 0.62
                p.setPen(QPen(blend(ctx.white, a * 0.8), 1.4))
                p.drawLine(QLineF(x0, y0, mx, my))
                p.drawLine(QLineF(mx, my, cx, cy))

        # 8. Nama di inti.
        name = ctx.name or ""
        if name and core_r > 8:
            inner = core_r
            space = max(1.0, r * 0.018)
            fsz = max(8, int(min(r * 0.105,
                                 (inner * 1.75) / max(1, len(name)) * 1.6 - space)))
            fnt = QFont("Courier New", fsz, QFont.Weight.Bold)
            fnt.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, space)
            p.setFont(fnt)
            p.setPen(QPen(blend(ctx.white, 0.6 + 0.4 * min(1.0, amp * 2)), 1))
            p.drawText(QRectF(cx - r, cy - fsz, r * 2, fsz * 2),
                       Qt.AlignmentFlag.AlignCenter, name)


# ═══════════════════════════════════════════════════════════════════════════
#  Konsep B — GlslReactorWidget: raymarch plasma + torus orbit di GPU
# ═══════════════════════════════════════════════════════════════════════════

_VERT = """
attribute vec2 pos;
varying vec2 vUv;
void main() {
    vUv = pos * 0.5 + 0.5;
    gl_Position = vec4(pos, 0.0, 1.0);
}
"""

_FRAG = """
#ifdef GL_ES
precision mediump float;
#endif
varying vec2 vUv;
uniform float uTime, uAmp, uBoot, uShut, uOpen, uSpeaking, uRate;
uniform vec3 uMain, uAcc, uBg;

mat3 rotX(float a){ float c=cos(a), s=sin(a); return mat3(1.,0.,0., 0.,c,-s, 0.,s,c); }
mat3 rotY(float a){ float c=cos(a), s=sin(a); return mat3(c,0.,s, 0.,1.,0., -s,0.,c); }
mat3 rotZ(float a){ float c=cos(a), s=sin(a); return mat3(c,-s,0., s,c,0., 0.,0.,1.); }

float hash3(vec3 p){ return fract(sin(dot(p, vec3(12.9898,78.233,45.164))) * 43758.5453); }
float noise3(vec3 p){
    vec3 i = floor(p), f = fract(p);
    f = f*f*(3.0-2.0*f);
    float n000=hash3(i), n100=hash3(i+vec3(1,0,0)), n010=hash3(i+vec3(0,1,0)), n110=hash3(i+vec3(1,1,0));
    float n001=hash3(i+vec3(0,0,1)), n101=hash3(i+vec3(1,0,1)), n011=hash3(i+vec3(0,1,1)), n111=hash3(i+vec3(1,1,1));
    return mix(mix(mix(n000,n100,f.x), mix(n010,n110,f.x), f.y),
               mix(mix(n001,n101,f.x), mix(n011,n111,f.x), f.y), f.z);
}
float fbm(vec3 p){
    float v = 0.0, a = 0.5;
    for (int i = 0; i < 4; i++) { v += a * noise3(p); p *= 2.03; a *= 0.5; }
    return v;
}

float sdSphere(vec3 p, float r){ return length(p) - r; }
float sdTorus(vec3 p, vec2 t){ vec2 q = vec2(length(p.xz) - t.x, p.y); return length(q) - t.y; }

float map(vec3 p){
    float scale = uBoot * (1.0 - 0.85 * uShut);
    float pulse = 1.0 + 0.09 * uAmp + 0.03 * uOpen + 0.02 * sin(uTime * 1.7);
    float d = sdSphere(p, 0.52 * pulse * scale);
    vec3 q1 = rotX(1.05 + 0.22 * sin(uTime * 0.23)) * rotY(uTime * 0.31 * uRate) * p;
    d = min(d, sdTorus(q1, vec2(0.86 * scale, 0.016)));
    vec3 q2 = rotX(-0.62 + 0.18 * sin(uTime * 0.17)) * rotY(-uTime * 0.22 * uRate) * p;
    d = min(d, sdTorus(q2, vec2(1.02 * scale, 0.012)));
    vec3 q3 = rotY(uTime * 0.12 * uRate) * rotX(1.45) * p;
    d = min(d, sdTorus(q3, vec2(0.70 * scale, 0.011)));
    return d;
}

void main(){
    vec2 uv = vUv * 2.0 - 1.0;
    vec3 ro = vec3(0.0, 0.0, -2.6);
    vec3 rd = normalize(vec3(uv * 0.95, 1.6));
    vec3 col = uBg;
    float glow = 0.0, t = 0.0;
    for (int i = 0; i < 56; i++){
        vec3 p = ro + rd * t;
        float d = map(p);
        glow += 0.013 / (0.02 + abs(d) * 8.0);
        if (d < 0.002) {
            float n = fbm(p * 3.2 + vec3(0.0, uTime * 0.35, uTime * 0.21));
            float fres = pow(1.0 - abs(dot(normalize(p), rd)), 2.2);
            vec3 plasma = mix(uMain, uAcc, n);
            col = plasma * (0.55 + 1.35 * n) + uAcc * fres * 1.5;
            break;
        }
        t += d;
        if (t > 7.0) break;
    }
    col += uAcc * min(glow, 1.7) * (0.45 + 0.65 * uSpeaking + 0.35 * uAmp);
    // shockwave boot: ring memuai dan pudar
    float w = abs(length(uv) - uBoot * 1.45);
    col += uMain * exp(-w * w * 90.0) * (1.0 - uBoot) * step(0.001, uBoot);
    // shutdown: padam perlahan
    col = mix(col, uBg, uShut * 0.9);
    gl_FragColor = vec4(col, 1.0);
}
"""


class GlslReactorWidget(QOpenGLWidget):
    """Konsep B — reaktor true-3D: satu quad fullscreen + fragment shader
    raymarch (bola plasma fbm + 3 torus orbit + glow akumulatif).

    State (amp/viseme/boot/shutdown) masuk sebagai uniform — animasi penuh
    60 FPS di GPU, CPU hanya mengisi dict. Bila konteks GL gagal dibuat,
    widget diam dan HudCanvas otomatis jatuh ke quantum (lihat ui.py).
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        from PyQt6.QtGui import QSurfaceFormat
        fmt = QSurfaceFormat()
        fmt.setSamples(4)
        self.setFormat(fmt)
        self._prog = None
        self._ok = False
        self._glf = None
        self._st: Dict[str, Any] = {"amp": 0.0, "speaking": 0.0, "open": 0.0,
                                    "boot": 0.0, "shut": 0.0, "rate": 1.0,
                                    "main": "#22d3ee", "acc": "#a78bfa",
                                    "bg": "#04070d", "t": 0.0}
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, False)

    # ── kontrak state ───────────────────────────────────────────────────────
    def set_state(self, st: Dict[str, Any]) -> None:
        self._st.update(st)
        self.update()

    def set_name(self, _name: str) -> None:
        pass                       # nama digambar QLabel overlay oleh ui.py

    # ── GL ──────────────────────────────────────────────────────────────────
    def initializeGL(self):
        try:
            from PyQt6.QtGui import QOpenGLShaderProgram
            prog = QOpenGLShaderProgram(self)
            prog.addShaderFromSourceCode(QOpenGLShaderProgram.ShaderTypeBit.Vertex, _VERT)
            prog.addShaderFromSourceCode(QOpenGLShaderProgram.ShaderTypeBit.Fragment, _FRAG)
            self._ok = prog.link()
            self._prog = prog if self._ok else None
        except Exception:
            self._ok = False
            self._prog = None
        try:
            self._glf = self.context().functions()
            if self._glf is not None:
                self._glf.initializeOpenGLFunctions()
        except Exception:
            self._glf = None

    def resizeGL(self, w: int, h: int) -> None:
        try:
            if self._glf is not None:
                self._glf.glViewport(0, 0, int(w), int(h))
        except Exception:
            pass

    def paintGL(self):
        if not self._ok or self._prog is None or self._glf is None:
            return
        try:
            st = self._st
            gl = self._glf

            def vec3(hex_str: str) -> QVector3D:
                c = QColor(str(hex_str))
                return QVector3D(c.redF(), c.greenF(), c.blueF())

            bg = QColor(str(st.get("bg", "#04070d")))
            gl.glClearColor(bg.redF(), bg.greenF(), bg.blueF(), 1.0)
            gl.glClear(0x00004000)                    # GL_COLOR_BUFFER_BIT
            self._prog.bind()
            self._prog.setUniformValue("uTime", float(st.get("t", 0.0)))
            self._prog.setUniformValue("uAmp", float(st.get("amp", 0.0)))
            self._prog.setUniformValue("uBoot", float(st.get("boot", 0.0)))
            self._prog.setUniformValue("uShut", float(st.get("shut", 0.0)))
            self._prog.setUniformValue("uOpen", float(st.get("open", 0.0)))
            self._prog.setUniformValue("uSpeaking",
                                       1.0 if st.get("speaking") else 0.0)
            self._prog.setUniformValue("uRate", float(st.get("rate", 1.0)))
            self._prog.setUniformValue("uMain", vec3(st.get("main", "#22d3ee")))
            self._prog.setUniformValue("uAcc", vec3(st.get("acc", "#a78bfa")))
            self._prog.setUniformValue("uBg", vec3(st.get("bg", "#04070d")))
            self._prog.enableAttributeArray("pos")
            self._prog.setAttributeArray("pos", [-1.0, -1.0, 1.0, -1.0,
                                                 -1.0, 1.0, 1.0, 1.0])
            gl.glDrawArrays(0x0005, 0, 4)             # GL_TRIANGLE_STRIP
            self._prog.disableAttributeArray("pos")
            self._prog.release()
        except Exception:
            self._ok = False


# ═══════════════════════════════════════════════════════════════════════════
#  Konsep C — WebReactorWidget: three.js + UnrealBloomPass di QWebEngineView
# ═══════════════════════════════════════════════════════════════════════════

class WebReactorWidget(QWidget):
    """Konsep C — reaktor three.js (assets/web_background/reactor.html).

    State dikirim sebagai JSON ke `window.__reactorState(st)` ~25x per detik.
    Bila PyQt6-WebEngine tidak terpasang, widget menampilkan pesan fallback
    yang jelas (dan HudCanvas otomatis jatuh ke quantum bila widget gagal).
    """

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._view = None
        self._st: Dict[str, Any] = {}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        try:
            import importlib
            _mod = importlib.import_module("PyQt6.QtWebEngineWidgets")
            self._view = _mod.QWebEngineView(self)
            lay.addWidget(self._view)
            self._view.load(QUrl.fromLocalFile(str(_HTML_PATH)))
        except Exception:
            self._view = None
            lab = QLabel(
                "WEB 3D butuh paket PyQt6-WebEngine\n\n"
                "pip install PyQt6-WebEngine", self)
            lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lab.setWordWrap(True)
            lay.addWidget(lab)
        self._push_t = QTimer(self)
        self._push_t.setInterval(40)                  # ~25 FPS ke sisi web
        self._push_t.timeout.connect(self._push)
        self._push_t.start()

    # ── kontrak state ───────────────────────────────────────────────────────
    def set_state(self, st: Dict[str, Any]) -> None:
        self._st.update(st)

    def set_name(self, name: str) -> None:
        self._st["name"] = name

    def _push(self) -> None:
        if self._view is None or not self._st:
            return
        try:
            import json
            self._view.page().runJavaScript(
                "window.__reactorState && window.__reactorState(%s);"
                % json.dumps(self._st))
        except Exception:
            pass
