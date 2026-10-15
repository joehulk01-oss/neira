"""Neira Gateway — server FastAPI (adaptasi brahma_connect/gateway/server.py).

Relay tipis: TIDAK ada otak AI di sini. Tugasnya hanya:
  1. Pairing klien (HP/browser) lewat token sekali-pakai dari QR / kode 6 digit.
  2. Autentikasi device — PC pakai GATEWAY_TOKEN, klien pakai DEVICE_KEY hasil pairing.
  3. Relay pesan — COMMAND (klien→PC), LOG/STATUS (PC→klien), AUDIO (HP↔PC).

Endpoint HTTP:
  GET  /health                  — status gateway (publik)
  GET  /gateway/info            — info ringkas (publik)
  POST /pair                    — buat token pairing sekali-pakai (Bearer GATEWAY_TOKEN)
  GET  /gateway/devices         — daftar device (Bearer GATEWAY_TOKEN)
  POST /gateway/devices/{id}/revoke  — cabut device (Bearer GATEWAY_TOKEN)
  POST /gateway/devices/{id}/forget  — hapus device (Bearer GATEWAY_TOKEN)

Endpoint WebSocket:
  /ws              — kanal utama (pairing, auth, COMMAND/LOG/STATUS/AUDIO JSON)
  /ws/phone-audio  — kanal audio biner (mic HP → PC, TTS PC → HP)

Jalankan lokal :  python -m gateway.server
Jalankan Docker :  uvicorn gateway.server:app --host 0.0.0.0 --port 8765
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect

from .devices import DeviceRegistry, PairingManager, constant_time_equals
from .protocol import (
    ROLE_CLIENT,
    ROLE_PC,
    ProtocolTypes,
    build_message,
    validate_message,
)
from .websocket import ConnectionHub


# ---------------------------------------------------------------------------
# Konfigurasi (adaptasi BrahmaGatewayConfig — sederhana, dari environment)
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class NeiraGatewayConfig:
    host: str = "0.0.0.0"
    port: int = 8000
    gateway_token: str = ""                       # rahasia admin + kredensial PC
    # data_dir TIDAK boleh relatif-CWD: kalau server dijalankan dari folder lain,
    # devices.json "hilang" dan semua device dipaksa pairing ulang. Kuncikan ke
    # folder repo (parents[1] = root proyek neira-gateway).
    data_dir: Path = field(
        default_factory=lambda: Path(__file__).resolve().parents[1] / "data"
    )
    pairing_ttl: int = 300                        # detik, masa berlaku token pairing
    gateway_name: str = "Neira Gateway"

    @classmethod
    def load(cls, override: dict[str, Any] | None = None) -> "NeiraGatewayConfig":
        env = os.environ
        default_data_dir = Path(__file__).resolve().parents[1] / "data"
        config = cls(
            host=env.get("GATEWAY_HOST", "0.0.0.0"),
            port=int(env.get("GATEWAY_PORT", "8000")),
            gateway_token=env.get("GATEWAY_TOKEN", "").strip(),
            data_dir=Path(env.get("GATEWAY_DATA_DIR") or default_data_dir),
            pairing_ttl=int(env.get("PAIRING_TTL", "300")),
            gateway_name=env.get("GATEWAY_NAME", "Neira Gateway"),
        )
        for key, value in (override or {}).items():
            setattr(config, key, value)
        return config


# ---------------------------------------------------------------------------
# AudioHub — socket audio biner terpisah (/ws/phone-audio)
# ---------------------------------------------------------------------------

class AudioHub:
    """Mic HP → PC dan TTS PC → HP, sebagai frame biner mentah (PCM)."""

    def __init__(self) -> None:
        self._pc: WebSocket | None = None
        self._clients: dict[int, WebSocket] = {}
        self._lock = asyncio.Lock()

    async def join(self, websocket: WebSocket, role: str) -> None:
        async with self._lock:
            if role == ROLE_PC:
                self._pc = websocket
            else:
                self._clients[id(websocket)] = websocket

    async def leave(self, websocket: WebSocket) -> None:
        async with self._lock:
            if self._pc is websocket:
                self._pc = None
            self._clients.pop(id(websocket), None)

    async def from_client(self, data: bytes) -> int:
        async with self._lock:
            target = self._pc
        if target is None:
            return 0
        try:
            await target.send_bytes(data)
        except Exception:
            return 0
        return 1

    async def from_pc(self, data: bytes) -> int:
        async with self._lock:
            clients = list(self._clients.values())
        sent = 0
        for client in clients:
            try:
                await client.send_bytes(data)
                sent += 1
            except Exception:
                pass
        return sent


# ---------------------------------------------------------------------------
# NeiraGateway — inti relay
# ---------------------------------------------------------------------------

class NeiraGateway:
    def __init__(self, config: NeiraGatewayConfig | None = None) -> None:
        self.config = config or NeiraGatewayConfig.load()
        self.hub = ConnectionHub()
        self.audio = AudioHub()
        self.pairing = PairingManager(ttl_seconds=self.config.pairing_ttl)
        self.registry = DeviceRegistry(self.config.data_dir / "devices.json")
        self._pc_id: str = ""

    # -- util ---------------------------------------------------------------

    def require_admin(self, request: Request) -> None:
        header = request.headers.get("authorization", "")
        token = header[7:].strip() if header.lower().startswith("bearer ") else ""
        expected = self.config.gateway_token
        if not expected:
            raise HTTPException(status_code=401, detail="GATEWAY_TOKEN not configured.")
        if not token or not constant_time_equals(token, expected):
            raise HTTPException(status_code=401, detail="Invalid gateway token.")

    async def pc_online(self) -> bool:
        if not self._pc_id:
            return False
        return (await self.hub.get(self._pc_id)) is not None

    async def client_count(self) -> int:
        ids = await self.hub.list_ids()
        return sum(1 for device_id in ids if device_id and device_id != self._pc_id)

    @staticmethod
    def _client_ip(websocket: WebSocket) -> str:
        client = getattr(websocket, "client", None)
        return str(client[0]) if client else ""

    @staticmethod
    async def _send_error(websocket: WebSocket, text: str, request_id: str = "") -> None:
        await websocket.send_json(
            build_message(ProtocolTypes.ERROR, {"error": text}, request_id=request_id or None)
        )

    # -- WebSocket utama ----------------------------------------------------

    async def on_websocket(self, websocket: WebSocket) -> None:
        await websocket.accept()
        state = await self.hub.attach(websocket)
        try:
            while True:
                try:
                    message = await websocket.receive_json()
                except (WebSocketDisconnect, RuntimeError, ValueError):
                    break
                ok, err = validate_message(message)
                if not ok:
                    await self._send_error(websocket, err)
                    continue
                mtype = str(message.get("type", ""))
                payload = message.get("payload") or {}
                request_id = str(message.get("request_id", ""))

                if not state.authenticated:
                    if mtype == ProtocolTypes.PAIR_REQUEST:
                        new_state = await self._handle_pair(websocket, message, payload)
                    elif mtype == ProtocolTypes.AUTHENTICATE:
                        new_state = await self._handle_auth(websocket, message, payload)
                    else:
                        await self._send_error(websocket, "Authenticate first.", request_id)
                        continue
                    if new_state is not None:
                        state = new_state
                    continue

                if mtype == ProtocolTypes.LOGOUT:
                    # User minta keluar dari device ini: cabut kredensial permanen
                    # (self-revoke) lalu tutup koneksi. Pairing berikutnya butuh
                    # kode 6 digit baru. Ini SATU-SATUNYA jalur kehilangan login.
                    await self._handle_logout(websocket, state, request_id)
                    return
                elif mtype == ProtocolTypes.PING:
                    await websocket.send_json(
                        build_message(
                            ProtocolTypes.PONG,
                            {"device_id": state.device_id},
                            request_id=request_id,
                        )
                    )
                    self.registry.touch(state.device_id, ip=self._client_ip(websocket))
                elif mtype == ProtocolTypes.PONG:
                    self.registry.touch(state.device_id, ip=self._client_ip(websocket))
                elif mtype in (ProtocolTypes.COMMAND, ProtocolTypes.IMAGE):
                    # IMAGE = gambar dari HP (paste/upload) → diteruskan ke PC untuk
                    # masuk pipeline vision Neira; relay-nya sama seperti COMMAND.
                    await self._relay_command(state, message, payload, request_id)
                elif mtype in (ProtocolTypes.LOG, ProtocolTypes.STATUS):
                    if state.role == ROLE_PC:
                        await self.hub.send_to_role(ROLE_CLIENT, message, exclude=state.device_id)
                    else:
                        await self.hub.send_to_role(ROLE_PC, message, exclude=state.device_id)
                elif mtype == ProtocolTypes.AUDIO:
                    target = str(payload.get("target", "")).strip()
                    if target:
                        await self.hub.send_to_device(target, message)
                    elif state.role == ROLE_PC:
                        await self.hub.send_to_role(ROLE_CLIENT, message, exclude=state.device_id)
                    else:
                        await self.hub.send_to_role(ROLE_PC, message, exclude=state.device_id)
                else:
                    await self._send_error(websocket, f"Unknown message type: {mtype}", request_id)
        finally:
            gone = await self.hub.unregister(websocket)
            await self.audio.leave(websocket)
            if gone:
                self.registry.mark_offline(gone)
                if gone == self._pc_id:
                    self._pc_id = ""
                await self.hub.broadcast(
                    build_message(ProtocolTypes.DEVICE_OFFLINE, {"device_id": gone})
                )

    async def _relay_command(
        self, state, message: dict[str, Any], payload: dict[str, Any], request_id: str
    ) -> None:
        """COMMAND: klien → PC (default), atau PC → klien bila ada target."""
        target = str(payload.get("target", "")).strip()
        if state.role == ROLE_CLIENT:
            if target:
                sent = 1 if await self.hub.send_to_device(target, message) else 0
            else:
                sent = await self.hub.send_to_role(ROLE_PC, message, exclude=state.device_id)
            if not sent:
                await self._send_error(
                    state.websocket, "PC offline — command not delivered.", request_id
                )
        else:
            if target:
                await self.hub.send_to_device(target, message)
            else:
                await self.hub.send_to_role(ROLE_CLIENT, message, exclude=state.device_id)

    async def _handle_pair(self, websocket: WebSocket, message: dict, payload: dict):
        """PAIR_REQUEST → PAIR_APPROVED (+ DEVICE_KEY permanen). Token sekali-pakai."""
        token = str(payload.get("pairing_token", "")).strip()
        code = str(payload.get("pairing_code", "")).strip()
        request_id = str(message.get("request_id", ""))

        offer = self.pairing.approve(token) if token else None
        if offer is None and code:
            by_code = self.pairing.get_offer_by_code(code)
            if by_code is not None:
                offer = self.pairing.approve(by_code.pairing_token)
        if offer is None:
            await self._send_error(websocket, "Pairing token invalid or expired.", request_id)
            return None

        record, device_key = self.registry.create_from_pairing(
            name=str(payload.get("name") or "Unknown Device"),
            role=ROLE_CLIENT,
            platform=str(payload.get("platform") or "unknown"),
            ip=self._client_ip(websocket),
            metadata={"pairing_code": offer.pairing_code},
        )
        state = await self.hub.register(websocket, record.device_id, role=record.role)
        await websocket.send_json(
            build_message(
                ProtocolTypes.PAIR_APPROVED,
                {
                    "device_id": record.device_id,
                    "device_key": device_key,
                    "role": record.role,
                    "name": record.name,
                },
                request_id=request_id,
            )
        )
        await websocket.send_json(
            build_message(
                ProtocolTypes.DEVICE_ONLINE,
                {"device_id": record.device_id, "role": record.role},
            )
        )
        # Beri tahu koneksi lain (PC) bahwa klien baru online.
        await self.hub.broadcast(
            build_message(
                ProtocolTypes.DEVICE_ONLINE,
                {"device_id": record.device_id, "role": record.role, "name": record.name},
            ),
            exclude=record.device_id,
        )
        return state

    async def _handle_auth(self, websocket: WebSocket, message: dict, payload: dict):
        """AUTHENTICATE → DEVICE_ONLINE. PC pakai GATEWAY_TOKEN, klien pakai DEVICE_KEY."""
        request_id = str(message.get("request_id", ""))
        role = str(payload.get("role", "")).strip().lower()
        device_id = str(payload.get("device_id", "")).strip()
        device_key = str(payload.get("device_key", "")).strip()
        ip = self._client_ip(websocket)

        # PC (otak Neira) — kredensialnya GATEWAY_TOKEN, bukan DEVICE_KEY.
        if role == ROLE_PC or (
            self.config.gateway_token and device_key and constant_time_equals(device_key, self.config.gateway_token)
        ):
            if not self.config.gateway_token or not constant_time_equals(device_key, self.config.gateway_token):
                await self._send_error(websocket, "Authentication failed.", request_id)
                return None
            device_id = device_id or "neira-pc"
            state = await self.hub.register(websocket, device_id, role=ROLE_PC)
            self._pc_id = device_id
            await websocket.send_json(
                build_message(
                    ProtocolTypes.DEVICE_ONLINE,
                    {"device_id": device_id, "role": ROLE_PC},
                    request_id=request_id,
                )
            )
            await self.hub.broadcast(
                build_message(
                    ProtocolTypes.DEVICE_ONLINE,
                    {"device_id": device_id, "role": ROLE_PC},
                ),
                exclude=device_id,
            )
            return state

        record = self.registry.authenticate(device_id, device_key, ip=ip)
        if record is None:
            await self._send_error(websocket, "Authentication failed.", request_id)
            return None
        state = await self.hub.register(websocket, record.device_id, role=record.role)
        await websocket.send_json(
            build_message(
                ProtocolTypes.DEVICE_ONLINE,
                {"device_id": record.device_id, "role": record.role},
                request_id=request_id,
            )
        )
        await self.hub.broadcast(
            build_message(
                ProtocolTypes.DEVICE_ONLINE,
                {"device_id": record.device_id, "role": record.role, "name": record.name},
            ),
            exclude=record.device_id,
        )
        return state

    async def _handle_logout(self, websocket: WebSocket, state, request_id: str) -> None:
        """LOGOUT: user eksplisit minta keluar. Kredensial device dicabut
        permanen (revoked), koneksi ditutup 4400 'Logged out'. Client web akan
        menghapus kredensialnya dan menampilkan layar pairing."""
        device_id = state.device_id if state else ""
        role = state.role if state else ""
        if device_id and role == ROLE_CLIENT:
            self.registry.revoke(device_id)
        elif device_id:
            # PC tidak boleh self-revoke via LOGOUT (kredensialnya env var).
            await self._send_error(websocket, "Logout not allowed for this role.", request_id)
            return
        try:
            await websocket.close(code=4400, reason="Logged out")
        except Exception:
            pass

    # -- WebSocket audio biner ----------------------------------------------

    async def on_phone_audio(self, websocket: WebSocket) -> None:
        """Auth lewat query string (?device_id=..&device_key=..), lalu pump frame biner."""
        await websocket.accept()
        params = websocket.query_params
        device_id = str(params.get("device_id", "")).strip()
        device_key = str(params.get("device_key", "")).strip()
        role = ""
        if self.config.gateway_token and device_key and constant_time_equals(device_key, self.config.gateway_token):
            role = ROLE_PC
        elif device_id and self.registry.authenticate(device_id, device_key, ip=self._client_ip(websocket)):
            role = ROLE_CLIENT
        if not role:
            await websocket.close(code=4401, reason="Authentication failed.")
            return

        await self.audio.join(websocket, role)
        try:
            while True:
                try:
                    data = await websocket.receive_bytes()
                except (WebSocketDisconnect, RuntimeError, ValueError):
                    break
                if role == ROLE_PC:
                    await self.audio.from_pc(data)
                else:
                    await self.audio.from_client(data)
        finally:
            await self.audio.leave(websocket)


# ---------------------------------------------------------------------------
# Aplikasi FastAPI
# ---------------------------------------------------------------------------

def build_app(config: NeiraGatewayConfig | None = None) -> FastAPI:
    gw = NeiraGateway(config)
    app = FastAPI(title=gw.config.gateway_name, docs_url=None, redoc_url=None)
    app.state.gateway = gw

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {
            "status": "ok",
            "gateway": gw.config.gateway_name,
            "pc_online": await gw.pc_online(),
            "clients": await gw.client_count(),
        }

    @app.get("/gateway/info")
    async def info() -> dict[str, Any]:
        return {
            "gateway": gw.config.gateway_name,
            "roles": [ROLE_PC, ROLE_CLIENT],
            "pairing_ttl": gw.config.pairing_ttl,
            "pc_online": await gw.pc_online(),
            "clients": await gw.client_count(),
        }

    @app.post("/pair")
    async def create_pair(request: Request) -> dict[str, Any]:
        gw.require_admin(request)
        offer = gw.pairing.create_offer()
        return {"gateway": gw.config.gateway_name, "pairing": offer.to_dict()}

    @app.get("/gateway/devices")
    async def list_devices(request: Request) -> dict[str, Any]:
        gw.require_admin(request)
        return {
            "pc_online": await gw.pc_online(),
            "devices": gw.registry.list_devices(),
        }

    @app.post("/gateway/devices/{device_id}/revoke")
    async def revoke_device(device_id: str, request: Request) -> dict[str, Any]:
        gw.require_admin(request)
        revoked = gw.registry.revoke(device_id)
        if revoked:
            await gw.hub.close_device(device_id, code=4403, reason="Device revoked")
        return {"revoked": revoked}

    @app.post("/gateway/devices/{device_id}/forget")
    async def forget_device(device_id: str, request: Request) -> dict[str, Any]:
        gw.require_admin(request)
        await gw.hub.close_device(device_id, code=4400, reason="Device removed")
        return {"removed": gw.registry.remove(device_id)}

    @app.websocket("/ws")
    async def ws_endpoint(websocket: WebSocket) -> None:
        await gw.on_websocket(websocket)

    @app.websocket("/ws/phone-audio")
    async def ws_phone_audio(websocket: WebSocket) -> None:
        await gw.on_phone_audio(websocket)

    # Halaman web klien (web/index.html) — dipakai HP/browser & app Android
    # fase 1 (WebView). Rute di atas tetap menang lebih dulu.
    web_dir = Path(__file__).resolve().parents[1] / "web"
    if web_dir.is_dir():
        from fastapi.staticfiles import StaticFiles

        app.mount("/", StaticFiles(directory=str(web_dir), html=True), name="web")

    return app


app = build_app()


def main() -> None:
    import uvicorn

    config = NeiraGatewayConfig.load()
    uvicorn.run(build_app(config), host=config.host, port=config.port, log_level="warning")


if __name__ == "__main__":
    main()
