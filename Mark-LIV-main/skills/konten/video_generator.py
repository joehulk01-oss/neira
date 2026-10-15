"""
AI Video Generator Skill for Neira & Hermes.
Generates short AI video clips (Text-to-Video) via cloud GPU without requiring an API key.
Saves videos to workspace/videos/ and opens them for the user.
"""

from __future__ import annotations

import asyncio
import os
import platform
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent

BASE_DIR = _base_dir()
VIDEOS_DIR = BASE_DIR / "workspace" / "videos"
VIDEOS_DIR.mkdir(parents=True, exist_ok=True)


def generate_video(prompt: str, duration: float = 3.0, filename: str = "") -> str:
    """
    Generates an AI video from a text description.
    prompt: detailed description of the video.
    duration: video length in seconds (default 3.0).
    filename: optional output file name.
    """
    clean_prompt = (prompt or "").strip()
    if not clean_prompt:
        return "Mohon berikan deskripsi/prompt video yang ingin dibuat."

    try:
        from abigail.client import VideoClient
    except ImportError:
        return "Modul 'abigail' belum terpasang. Jalankan pip install abigail."

    # Determine filename
    if not filename:
        slug = re.sub(r'[^a-zA-Z0-9_]+', '_', clean_prompt.lower())[:30].strip('_')
        filename = f"video_{slug}_{int(time.time())}.mp4"
    elif not filename.endswith(".mp4"):
        filename += ".mp4"

    out_file = VIDEOS_DIR / filename

    async def _run_gen():
        async with VideoClient(request_timeout=120.0, max_retries=1) as client:
            res = await client.generate_video(clean_prompt, duration=float(duration))
            if not res.videos:
                raise RuntimeError("Server video tidak mengembalikan file video.")
            video_item = res.videos[0]
            out_file.write_bytes(video_item.video_bytes)
            return out_file

    try:
        # Run async in current thread or new loop
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(lambda: asyncio.run(_run_gen()))
                saved_path = future.result(timeout=150)
        else:
            saved_path = asyncio.run(_run_gen())

        # Open video automatically on user's desktop
        if platform.system() == "Windows":
            try:
                os.startfile(str(saved_path))
            except Exception:
                pass

        file_size_kb = round(saved_path.stat().st_size / 1024, 1)
        return (
            f"Video AI berhasil dibuat ({file_size_kb} KB)!\n"
            f"Disimpan di: {saved_path}\n"
            f"File video telah dibuka di layar untuk Anda."
        )
    except Exception as e:
        return f"Gagal membuat video AI: {e}"


TOOL = {
    "name": "generate_video",
    "description": (
        "Generates short AI video clips (Text-to-Video) based on a descriptive prompt. "
        "Use this whenever the user asks to create, make, or generate a video using AI, "
        "or asks for video animations (e.g. 'buatkan video kucing menari', 'generate video ombak pantai'). "
        "The generated video will be saved to workspace/videos/ and opened on the desktop."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {
                "type": "STRING",
                "description": "Visual description of the video to create (e.g. 'cinematic sunset over ocean waves', 'robot walking in futuristic city').",
            },
            "duration": {
                "type": "NUMBER",
                "description": "Video duration in seconds (typically 3.0 to 5.0).",
            },
            "filename": {
                "type": "STRING",
                "description": "Optional custom filename for the MP4 output.",
            },
        },
        "required": ["prompt"],
    },
    "handler": generate_video,
}
