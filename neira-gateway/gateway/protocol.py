"""Neira Gateway — protokol pesan (adaptasi brahma_connect/gateway/protocol.py).

Setiap pesan = JSON object:
    {"type": "...", "request_id": "...", "timestamp": "...", "payload": {...}}

Alur hidup koneksi:
    1. PAIR_REQUEST  (klien→gateway, bawa pairing_token sekali-pakai dari QR)
       → PAIR_APPROVED (gateway→klien, berisi DEVICE_KEY permanen)
    2. AUTHENTICATE (klien→gateway, bawa device_id + device_key)
       → DEVICE_ONLINE
    3. PING (klien) → PONG (gateway) — heartbeat tiap ~15 detik
    4. Relay: COMMAND/IMAGE (klien→PC), LOG/STATUS (PC→klien), AUDIO (HP↔PC)
    5. LOGOUT (klien, opsional) — user minta keluar: kredensial device dicabut
       permanen (self-revoke) + koneksi ditutup dengan kode 4400 "Logged out".
       Pairing berikutnya butuh kode 6 digit baru dari PC.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4


class ProtocolTypes:
    HELLO = "hello"
    PAIR_REQUEST = "pair_request"
    PAIR_APPROVED = "pair_approved"
    AUTHENTICATE = "authenticate"
    DEVICE_ONLINE = "device_online"
    DEVICE_OFFLINE = "device_offline"
    PING = "ping"
    PONG = "pong"
    COMMAND = "command"   # klien → PC (diproses _process_dashboard_commands di main.py)
    LOG = "log"           # PC → klien (teks log HUD)
    STATUS = "status"     # PC → klien (state reaktor, metrik, dsb.)
    AUDIO = "audio"       # HP → PC (mic) dan PC → HP (TTS)
    IMAGE = "image"       # klien → PC (payload: mime_type + data base64 + caption) → vision
    LOGOUT = "logout"     # klien → gateway: user minta logout — hapus kredensial device
    ERROR = "error"


# Role device di gateway.
ROLE_PC = "pc"         # otak Neira (Neira.exe) — penerima COMMAND/AUDIO
ROLE_CLIENT = "client"  # klien remote (HP Android / browser) — penerima LOG/STATUS


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_request_id() -> str:
    return uuid4().hex


def build_message(
    message_type: str,
    payload: dict | None = None,
    request_id: str | None = None,
    timestamp: str | None = None,
) -> dict:
    """Susun pesan standar gateway."""
    return {
        "type": message_type,
        "request_id": request_id or new_request_id(),
        "timestamp": timestamp or now_iso(),
        "payload": payload or {},
    }


def validate_message(message: dict) -> tuple[bool, str]:
    """Validasi struktur minimum pesan. Balikan: (valid, pesan_error)."""
    if not isinstance(message, dict):
        return False, "Message must be a JSON object."
    for key in ("type", "request_id", "timestamp"):
        if not str(message.get(key, "")).strip():
            return False, f"Missing required field: {key}"
    return True, ""
