"""
Image Remove BG — hapus latar belakang gambar secara lokal (offline, tanpa upload).

Engine: `rembg` (pip, model ISNet/U2-Net) — kualitas setara toolkit browser
removerized (github.com/yossdotpro/removerized) tapi jalan sebagai Python
murni di .venv Neira, plus upscale cepat via OpenCV (sudah ada di requirements).

Aksi:
  remove   : 1 gambar → PNG transparan (atau ganti latar warna).
  batch    : seluruh folder gambar → folder output PNG transparan.
  upscale  : perbesar resolusi (factor 2/4) — INTER_CUBIC / INTER_LANCZOS4.

Auto-discovered oleh core/action_loader.py dan core/skill_hub.py via TOOL dict.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_IMG_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff"}
_MAX_BODY = 4000


def _resolve(path_str: str) -> Path:
    p = Path(str(path_str or "").strip().strip('"'))
    if not p.is_absolute():
        p = Path.cwd() / p
    return p


def _new_session(model: str):
    """Session rembg (import di dalam fungsi agar skill tetap valid tanpa paket)."""
    from rembg import new_session

    return new_session(model or "isnet-general-use")


def _remove_one(src: Path, dst: Path, model: str, alpha_matting: bool) -> str:
    from PIL import Image
    from rembg import remove

    with Image.open(src) as im:
        im = im.convert("RGBA")
        out = remove(
            im,
            session=_new_session(model),
            alpha_matting=alpha_matting,
            alpha_matting_foreground_threshold=240,
            alpha_matting_background_threshold=10,
            alpha_matting_erode_size=10,
        )
        dst.parent.mkdir(parents=True, exist_ok=True)
        out.save(dst, "PNG")
    return f"{src.name} → {dst} ({dst.stat().st_size // 1024} KB)"


def _hex_rgba(color: str) -> tuple:
    c = (color or "").strip().lstrip("#")
    if len(c) == 6:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), 255)
    if len(c) == 8:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16), int(c[6:8], 16))
    raise ValueError(f"warna '{color}' tidak dikenal (pakai hex #RRGGBB)")


def _do_remove(params: Dict[str, Any]) -> str:
    src = _resolve(params.get("source", ""))
    if not src.exists():
        return f"File tidak ditemukan: {src}"
    if src.suffix.lower() not in _IMG_EXT:
        return f"Bukan gambar ({src.suffix}): {src}"
    model = str(params.get("model", "") or "").strip() or "isnet-general-use"
    alpha_matting = bool(params.get("alpha_matting", False))
    out_str = str(params.get("output", "") or "").strip()
    dst = _resolve(out_str) if out_str else src.with_name(f"{src.stem}_nobg.png")

    line = _remove_one(src, dst, model, alpha_matting)

    bg = str(params.get("background", "") or "").strip()
    if bg:
        from PIL import Image

        rgba = _hex_rgba(bg)
        with Image.open(dst) as fg:
            base = Image.new("RGBA", fg.size, rgba)
            base.alpha_composite(fg)
            base.save(dst, "PNG")
        line += f" + latar {bg}"

    return line


def _do_batch(params: Dict[str, Any]) -> str:
    folder = _resolve(params.get("source", ""))
    if not folder.is_dir():
        return f"Bukan folder: {folder}"
    out_dir = _resolve(params.get("output", "")) if params.get("output") else folder.parent / f"{folder.name}_nobg"
    model = str(params.get("model", "") or "").strip() or "isnet-general-use"
    files: List[Path] = [p for p in sorted(folder.iterdir()) if p.suffix.lower() in _IMG_EXT]
    if not files:
        return f"Tidak ada gambar di {folder}"
    out_dir.mkdir(parents=True, exist_ok=True)
    done, fail = [], []
    for f in files:
        try:
            _remove_one(f, out_dir / f"{f.stem}.png", model, False)
            done.append(f.name)
        except Exception as e:
            fail.append(f"{f.name} ({e})")
    msg = f"[batch rembg] {len(done)}/{len(files)} → {out_dir}"
    if fail:
        msg += "\ngagal: " + "; ".join(fail[:5])
    return msg


def _do_upscale(params: Dict[str, Any]) -> str:
    src = _resolve(params.get("source", ""))
    if not src.exists():
        return f"File tidak ditemukan: {src}"
    try:
        import cv2
        import numpy as np
    except Exception as e:
        return f"OpenCV/numpy tidak tersedia: {e}"
    factor = int(params.get("factor", 2) or 2)
    if factor not in (2, 3, 4):
        return "factor hanya boleh 2, 3, atau 4."
    interp = cv2.INTER_CUBIC if factor <= 2 else cv2.INTER_LANCZOS4
    img = cv2.imread(str(src), cv2.IMREAD_UNCHANGED)
    if img is None:
        return f"Gagal membaca gambar: {src}"
    big = cv2.resize(img, None, fx=factor, fy=factor, interpolation=interp)
    out_str = str(params.get("output", "") or "").strip()
    dst = _resolve(out_str) if out_str else src.with_name(f"{src.stem}_x{factor}{src.suffix or '.png'}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    if not cv2.imwrite(str(dst), big):
        return f"Gagal menulis: {dst}"
    h, w = img.shape[:2]
    return f"{src.name}: {w}x{h} → {w * factor}x{h * factor} → {dst} ({dst.stat().st_size // 1024} KB)"


def image_remove_bg(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Hapus latar / upscale gambar lokal via rembg + OpenCV."""
    p = parameters or {}
    action = str(p.get("action", "remove")).strip().lower()
    try:
        if action == "remove":
            return _do_remove(p)
        if action == "batch":
            return _do_batch(p)
        if action == "upscale":
            return _do_upscale(p)
        return "Aksi tidak dikenal. Pilihan action: remove | batch | upscale."
    except Exception as e:
        return f"image_remove_bg error: {e}"


TOOL: Dict[str, Any] = {
    "name": "image_remove_bg",
    "description": (
        "Remove image background locally (offline, rembg AI models) or upscale it. "
        "Fully local: no upload, no API key. Produces transparent PNG (or colored "
        "background) and supports folder batch processing."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "remove = hapus latar 1 gambar; batch = folder; upscale = perbesar resolusi.",
                "enum": ["remove", "batch", "upscale"],
            },
            "source": {
                "type": "STRING",
                "description": "Path gambar (remove/upscale) atau path folder (batch). Relatif = dari cwd.",
            },
            "output": {
                "type": "STRING",
                "description": "Path hasil (opsional). Default: <nama>_nobg.png di sumber; batch → <folder>_nobg/.",
            },
            "model": {
                "type": "STRING",
                "description": "Model rembg (opsional): isnet-general-use (default, akurat), u2net, u2netp (cepat), silueta, isnet_human_seg (manusia).",
            },
            "background": {
                "type": "STRING",
                "description": "Ganti latar dengan warna hex (opsional, mis. #FFFFFF) alih-alih transparan.",
            },
            "alpha_matting": {
                "type": "BOOLEAN",
                "description": "Detail tepi halus utk rambut/rambut tipis (lebih lambat). Default false.",
            },
            "factor": {"type": "INTEGER", "description": "Perbesaran upscale: 2 | 3 | 4 (default 2)."},
        },
        "required": ["action", "source"],
    },
    "handler": image_remove_bg,
    "behavior": "NON_BLOCKING",
}
