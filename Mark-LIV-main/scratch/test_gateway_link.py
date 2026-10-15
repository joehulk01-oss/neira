"""Uji integrasi GatewayLink ↔ Neira Gateway (mode GATEWAY_URL).

Jalankan dari d:/hack/Neira/Mark-LIV-main:
    .venv\\Scripts\\python.exe scratch\\test_gateway_link.py

Skenario: gateway in-process (uvicorn) + GatewayLink (role=pc) + klien HP palsu —
QR pairing 6 digit, COMMAND HP→PC masuk _command_queue, broadcast log PC→HP
sampai, dan audio HP→PC masuk _phone_audio_queue.
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))                            # dashboard.gateway_link
sys.path.insert(0, str(BASE.parent / "neira-gateway"))   # gateway.server (in-process)

TOKEN = "uji-link-token"
PORT = 8788


def _msg(mtype: str, payload: dict | None = None) -> dict:
    return {
        "type": mtype,
        "request_id": uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }


async def _scenario() -> None:
    import uvicorn
    import websockets

    from dashboard.gateway_link import GatewayLink
    from gateway.server import NeiraGatewayConfig, build_app

    config = NeiraGatewayConfig.load({
        "gateway_token": TOKEN,
        "data_dir": Path(tempfile.mkdtemp(prefix="neira-link-test-")),
    })
    server = uvicorn.Server(
        uvicorn.Config(build_app(config), host="127.0.0.1", port=PORT, log_level="error")
    )
    server_task = asyncio.create_task(server.serve())
    await asyncio.sleep(0.5)

    link = GatewayLink(f"http://127.0.0.1:{PORT}", TOKEN)
    link_task = asyncio.create_task(link.serve())
    await asyncio.sleep(0.5)

    # ── QR pairing: kode 6 digit + token sekali-pakai ─────────────────────
    # new_key() blocking (urllib) — dipanggil dari thread terpisah seperti di
    # produksi (Qt thread), supaya event loop tidak terblokir (deadlock uji).
    code = await asyncio.to_thread(link.new_key)
    assert len(code) == 6 and code.isdigit(), code
    auto = link.get_auto_url()
    assert auto.startswith("http://127.0.0.1:") and "token=" in auto, auto

    # ── HP palsu: pairing → COMMAND → terima broadcast → kirim audio ──────
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws") as hp:
        offer = link._last_offer
        await hp.send(json.dumps(_msg("pair_request", {
            "pairing_token": offer["pairing_token"], "name": "HP Palsu", "platform": "android",
        })))
        approved = json.loads(await hp.recv())
        assert approved["type"] == "pair_approved", approved
        device_id = approved["payload"]["device_id"]
        device_key = approved["payload"]["device_key"]
        assert json.loads(await hp.recv())["type"] == "device_online"

        # COMMAND HP → PC (GatewayLink) → _command_queue (dipakai main.py).
        await hp.send(json.dumps(_msg("command", {"text": "halo dari hp"})))
        text = await asyncio.wait_for(link._command_queue.get(), timeout=5)
        assert text == "halo dari hp", text

        # broadcast() PC → HP (gaya dashboard lama: {"type": "log", ...}).
        await link.broadcast({"type": "log", "speaker": "jarvis", "text": "siap"})
        got = json.loads(await asyncio.wait_for(hp.recv(), timeout=5))
        assert got["type"] == "log" and got["payload"]["text"] == "siap", got

        # Audio HP → PC: /ws/phone-audio → _phone_audio_queue (bentuk dashboard lama).
        url = (
            f"ws://127.0.0.1:{PORT}/ws/phone-audio"
            f"?device_id={device_id}&device_key={device_key}"
        )
        async with websockets.connect(url) as hp_audio:
            await hp_audio.send(b"\x01\x02pcm")
            chunk = await asyncio.wait_for(link._phone_audio_queue.get(), timeout=5)
            assert chunk["data"] == b"\x01\x02pcm" and chunk["mime_type"] == "audio/pcm", chunk

    link_task.cancel()
    server.should_exit = True
    await asyncio.wait_for(server_task, timeout=5)


def main() -> int:
    try:
        asyncio.run(_scenario())
    except Exception as exc:  # noqa: BLE001
        print(f"FAIL test_gateway_link: {exc!r}")
        return 1
    print("PASS test_gateway_link (QR pairing, COMMAND, broadcast, audio)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
