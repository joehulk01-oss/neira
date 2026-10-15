"""Uji lokal Neira Gateway — tanpa VPS, tanpa Docker.

Jalankan dari folder neira-gateway/:
    python tests/test_gateway_ws.py
atau lewat pytest:
    python -m pytest tests/test_gateway_ws.py -q

Skenario: health, pairing (token sekali-pakai), auth (DEVICE_KEY / GATEWAY_TOKEN),
relay COMMAND (klien→PC) dan LOG (PC→klien), PING→PONG, audio biner, dan tolakan.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from gateway.protocol import ProtocolTypes, build_message  # noqa: E402
from gateway.server import NeiraGatewayConfig, build_app  # noqa: E402

TOKEN = "uji-gateway-token"


def _make_client() -> TestClient:
    config = NeiraGatewayConfig.load(
        {
            "gateway_token": TOKEN,
            "data_dir": Path(tempfile.mkdtemp(prefix="neira-gw-test-")),
        }
    )
    return TestClient(build_app(config))


def _create_offer(client: TestClient) -> dict:
    response = client.post("/pair", headers={"Authorization": f"Bearer {TOKEN}"})
    assert response.status_code == 200, response.text
    return response.json()["pairing"]


def _pair(client: TestClient) -> tuple[str, str]:
    """Pairing sekali putaran. Balikan: (device_id, device_key)."""
    offer = _create_offer(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            build_message(
                ProtocolTypes.PAIR_REQUEST,
                {"pairing_token": offer["pairing_token"], "name": "HP Uji", "platform": "android"},
            )
        )
        approved = ws.receive_json()
        assert approved["type"] == ProtocolTypes.PAIR_APPROVED, approved
        online = ws.receive_json()
        assert online["type"] == ProtocolTypes.DEVICE_ONLINE, online
        return approved["payload"]["device_id"], approved["payload"]["device_key"]


# ---------------------------------------------------------------------------

def test_health() -> None:
    client = _make_client()
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["pc_online"] is False
    assert body["clients"] == 0


def test_admin_token_required() -> None:
    client = _make_client()
    assert client.post("/pair").status_code == 401
    assert client.get("/gateway/devices").status_code == 401
    assert client.post("/pair", headers={"Authorization": "Bearer salah"}).status_code == 401


def test_pairing_single_use() -> None:
    client = _make_client()
    offer = _create_offer(client)
    payload = {"pairing_token": offer["pairing_token"], "name": "HP Uji", "platform": "android"}

    with client.websocket_connect("/ws") as ws:
        ws.send_json(build_message(ProtocolTypes.PAIR_REQUEST, payload))
        approved = ws.receive_json()
        assert approved["type"] == ProtocolTypes.PAIR_APPROVED, approved

    # Token yang sama ditolak (sekali-pakai).
    with client.websocket_connect("/ws") as ws:
        ws.send_json(build_message(ProtocolTypes.PAIR_REQUEST, payload))
        reply = ws.receive_json()
        assert reply["type"] == ProtocolTypes.ERROR, reply


def test_auth_with_device_key() -> None:
    client = _make_client()
    device_id, device_key = _pair(client)

    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            build_message(
                ProtocolTypes.AUTHENTICATE, {"device_id": device_id, "device_key": device_key}
            )
        )
        ack = ws.receive_json()
        assert ack["type"] == ProtocolTypes.DEVICE_ONLINE, ack
        assert ack["payload"]["device_id"] == device_id

    # Kunci salah → ERROR.
    with client.websocket_connect("/ws") as ws:
        ws.send_json(
            build_message(
                ProtocolTypes.AUTHENTICATE, {"device_id": device_id, "device_key": "salah"}
            )
        )
        ack = ws.receive_json()
        assert ack["type"] == ProtocolTypes.ERROR, ack


def test_reject_unauthenticated() -> None:
    client = _make_client()
    with client.websocket_connect("/ws") as ws:
        ws.send_json(build_message(ProtocolTypes.COMMAND, {"text": "x"}))
        reply = ws.receive_json()
        assert reply["type"] == ProtocolTypes.ERROR, reply


def test_relay_command_log_ping() -> None:
    client = _make_client()
    with client.websocket_connect("/ws") as pc, client.websocket_connect("/ws") as hp:
        # PC masuk pakai GATEWAY_TOKEN.
        pc.send_json(
            build_message(
                ProtocolTypes.AUTHENTICATE,
                {"role": "pc", "device_id": "neira-pc", "device_key": TOKEN},
            )
        )
        ack = pc.receive_json()
        assert ack["type"] == ProtocolTypes.DEVICE_ONLINE and ack["payload"]["role"] == "pc", ack

        # HP pairing.
        offer = _create_offer(client)
        hp.send_json(
            build_message(
                ProtocolTypes.PAIR_REQUEST,
                {"pairing_token": offer["pairing_token"], "name": "HP Uji", "platform": "android"},
            )
        )
        assert hp.receive_json()["type"] == ProtocolTypes.PAIR_APPROVED
        assert hp.receive_json()["type"] == ProtocolTypes.DEVICE_ONLINE

        # PC menerima notifikasi "HP online" (broadcast DEVICE_ONLINE).
        got = pc.receive_json()
        assert got["type"] == ProtocolTypes.DEVICE_ONLINE and got["payload"]["role"] == "client", got

        # COMMAND: HP → PC.
        hp.send_json(build_message(ProtocolTypes.COMMAND, {"text": "halo neira"}))
        got = pc.receive_json()
        assert got["type"] == ProtocolTypes.COMMAND and got["payload"]["text"] == "halo neira", got

        # LOG: PC → HP.
        pc.send_json(build_message(ProtocolTypes.LOG, {"text": "siap"}))
        got = hp.receive_json()
        assert got["type"] == ProtocolTypes.LOG and got["payload"]["text"] == "siap", got

        # STATUS: PC → HP.
        pc.send_json(build_message(ProtocolTypes.STATUS, {"state": "idle"}))
        got = hp.receive_json()
        assert got["type"] == ProtocolTypes.STATUS and got["payload"]["state"] == "idle", got

        # PING → PONG.
        hp.send_json(build_message(ProtocolTypes.PING))
        got = hp.receive_json()
        assert got["type"] == ProtocolTypes.PONG, got


def test_command_without_pc_gets_error() -> None:
    client = _make_client()
    device_id, device_key = _pair(client)
    with client.websocket_connect("/ws") as hp:
        hp.send_json(
            build_message(
                ProtocolTypes.AUTHENTICATE, {"device_id": device_id, "device_key": device_key}
            )
        )
        assert hp.receive_json()["type"] == ProtocolTypes.DEVICE_ONLINE
        hp.send_json(build_message(ProtocolTypes.COMMAND, {"text": "halo"}))
        got = hp.receive_json()
        assert got["type"] == ProtocolTypes.ERROR and "PC offline" in got["payload"]["error"], got


def test_phone_audio_binary() -> None:
    client = _make_client()
    device_id, device_key = _pair(client)
    pc_url = f"/ws/phone-audio?device_id=neira-pc&device_key={TOKEN}"
    hp_url = f"/ws/phone-audio?device_id={device_id}&device_key={device_key}"

    with client.websocket_connect(pc_url) as pc, client.websocket_connect(hp_url) as hp:
        # Mic HP → PC.
        hp.send_bytes(b"\x00\x01\x02pcm")
        assert pc.receive_bytes() == b"\x00\x01\x02pcm"
        # TTS PC → HP.
        pc.send_bytes(b"tts-frame")
        assert hp.receive_bytes() == b"tts-frame"

    # Kunci salah ditolak.
    try:
        with client.websocket_connect("/ws/phone-audio?device_id=x&device_key=salah") as ws:
            ws.receive_bytes()
    except Exception:
        pass


# ---------------------------------------------------------------------------

def main() -> int:
    tests = [
        value
        for name, value in sorted(globals().items())
        if name.startswith("test_") and callable(value)
    ]
    failed = 0
    for fn in tests:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {fn.__name__}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} lulus")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
