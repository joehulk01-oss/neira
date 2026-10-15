"""Neira Gateway — hub koneksi WebSocket (adaptasi brahma_connect/gateway/websocket.py).

Bedanya dengan aslinya: koneksi punya ROLE — "pc" (otak, satu) atau "client"
(HP/browser, bisa banyak). Relay memakai `send_to_role()` dan `broadcast()`.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from fastapi import WebSocket

from .protocol import ROLE_CLIENT


@dataclass(slots=True)
class ConnectionState:
    websocket: WebSocket
    device_id: str = ""
    role: str = ROLE_CLIENT
    authenticated: bool = False
    pending: dict[str, asyncio.Future] = field(default_factory=dict)


class ConnectionHub:
    def __init__(self) -> None:
        self._connections: dict[str, ConnectionState] = {}
        self._socket_index: dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def attach(self, websocket: WebSocket, *, role: str = ROLE_CLIENT) -> ConnectionState:
        state = ConnectionState(websocket=websocket, role=role)
        async with self._lock:
            self._socket_index[id(websocket)] = ""
        return state

    async def register(
        self, websocket: WebSocket, device_id: str, *, role: str = ROLE_CLIENT
    ) -> ConnectionState:
        state = ConnectionState(
            websocket=websocket, device_id=device_id, role=role, authenticated=True
        )
        async with self._lock:
            old = self._connections.get(device_id)
            if old is not None:
                # Koneksi lama dengan device_id sama digantikan — lepaskan indeksnya
                # supaya unregister() lama tidak menghapus state yang baru.
                self._socket_index.pop(id(old.websocket), None)
            self._connections[device_id] = state
            self._socket_index[id(websocket)] = device_id
        return state

    async def unregister(self, websocket: WebSocket) -> str:
        async with self._lock:
            device_id = self._socket_index.pop(id(websocket), "")
            if device_id:
                current = self._connections.get(device_id)
                if current is not None and current.websocket is websocket:
                    self._connections.pop(device_id, None)
                    return device_id
            return ""

    async def get(self, device_id: str) -> ConnectionState | None:
        async with self._lock:
            return self._connections.get(str(device_id))

    async def list_ids(self) -> list[str]:
        async with self._lock:
            return list(self._connections.keys())

    async def send_to_device(self, device_id: str, message: dict[str, Any]) -> bool:
        state = await self.get(device_id)
        if state is None:
            return False
        try:
            await state.websocket.send_json(message)
        except Exception:
            return False
        return True

    async def send_to_role(
        self, role: str, message: dict[str, Any], *, exclude: str = ""
    ) -> int:
        """Kirim ke semua device ber-role tertentu. Balikan: jumlah yang terkirim."""
        async with self._lock:
            states = [
                s for s in self._connections.values()
                if s.role == role and s.device_id != exclude
            ]
        sent = 0
        for state in states:
            try:
                await state.websocket.send_json(message)
                sent += 1
            except Exception:
                pass
        return sent

    async def broadcast(self, message: dict[str, Any], *, exclude: str = "") -> int:
        async with self._lock:
            states = [s for s in self._connections.values() if s.device_id != exclude]
        sent = 0
        for state in states:
            try:
                await state.websocket.send_json(message)
                sent += 1
            except Exception:
                pass
        return sent

    async def close_device(self, device_id: str, code: int = 1000, reason: str = "") -> bool:
        state = await self.get(device_id)
        if state is None:
            return False
        try:
            await state.websocket.close(code=code, reason=reason)
        except Exception:
            return False
        return True
