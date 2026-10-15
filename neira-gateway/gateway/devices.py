"""Neira Gateway — registry device + token pairing.

Adaptasi gabungan `brahma_connect/gateway/device_manager.py` + `pairing.py`
+ `authentication.py`, disederhanakan untuk 2 role saja: "pc" dan "client".

- PairingManager : token sekali-pakai (dari QR di PC) + kode 6 digit, TTL 5 menit.
- DeviceRegistry : simpan device + hash DEVICE_KEY permanen ke data/devices.json.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .protocol import ROLE_CLIENT, now_iso


# ---------------------------------------------------------------------------
# Util autentikasi (diadaptasi dari brahma_connect/gateway/authentication.py)
# ---------------------------------------------------------------------------

def hash_secret(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


def generate_pairing_token() -> str:
    return secrets.token_urlsafe(32)


def generate_device_key() -> str:
    return secrets.token_urlsafe(48)


def generate_device_id(platform: str, name: str) -> str:
    prefix = "".join(ch for ch in (platform or "device").lower() if ch.isalnum())[:8] or "device"
    return f"{prefix}_{secrets.token_hex(3)}"


def constant_time_equals(left: str, right: str) -> bool:
    return hmac.compare_digest(left.encode("utf-8"), right.encode("utf-8"))


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------

@dataclass(slots=True)
class PairingOffer:
    pairing_token: str
    pairing_code: str
    expires_at: float
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pairing_token": self.pairing_token,
            "pairing_code": self.pairing_code,
            "expires": int(max(0, self.expires_at - time.time())),
            "created_at": self.created_at,
        }


@dataclass(slots=True)
class DeviceRecord:
    device_id: str
    name: str
    role: str = ROLE_CLIENT
    platform: str = "unknown"
    ip: str = ""
    online: bool = False
    last_seen: str = ""
    paired_at: str = ""
    key_hash: str = ""          # hash DEVICE_KEY — aslinya TIDAK disimpan
    revoked: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "name": self.name,
            "role": self.role,
            "platform": self.platform,
            "ip": self.ip,
            "online": self.online,
            "last_seen": self.last_seen,
            "paired_at": self.paired_at,
            "revoked": self.revoked,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DeviceRecord":
        return cls(
            device_id=str(data.get("device_id", "")),
            name=str(data.get("name", "Unknown Device")),
            role=str(data.get("role", ROLE_CLIENT)),
            platform=str(data.get("platform", "unknown")),
            ip=str(data.get("ip", "")),
            online=bool(data.get("online", False)),
            last_seen=str(data.get("last_seen", "")),
            paired_at=str(data.get("paired_at", "")),
            key_hash=str(data.get("key_hash", "")),
            revoked=bool(data.get("revoked", False)),
            metadata=dict(data.get("metadata") or {}),
        )


# ---------------------------------------------------------------------------
# PairingManager — token sekali-pakai (diadaptasi dari brahma_connect/gateway/pairing.py)
# ---------------------------------------------------------------------------

class PairingManager:
    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = max(60, int(ttl_seconds))
        self._offers: dict[str, PairingOffer] = {}
        self._code_index: dict[str, str] = {}

    def _prune(self) -> None:
        now = time.time()
        for token in [t for t, o in self._offers.items() if o.expires_at <= now]:
            offer = self._offers.pop(token, None)
            if offer is not None:
                self._code_index.pop(offer.pairing_code, None)

    def create_offer(self) -> PairingOffer:
        self._prune()
        token = generate_pairing_token()
        code = f"{secrets.randbelow(1_000_000):06d}"
        offer = PairingOffer(
            pairing_token=token,
            pairing_code=code,
            expires_at=time.time() + self.ttl_seconds,
        )
        self._offers[token] = offer
        self._code_index[code] = token
        return offer

    def get_offer(self, pairing_token: str) -> PairingOffer | None:
        self._prune()
        return self._offers.get(str(pairing_token or "").strip())

    def get_offer_by_code(self, pairing_code: str) -> PairingOffer | None:
        self._prune()
        token = self._code_index.get(str(pairing_code or "").strip())
        return self._offers.get(token) if token else None

    def approve(self, pairing_token: str) -> PairingOffer | None:
        """Konsumsi token (sekali pakai). None bila token tidak valid/kedaluwarsa."""
        self._prune()
        offer = self._offers.pop(str(pairing_token or "").strip(), None)
        if offer is None:
            return None
        self._code_index.pop(offer.pairing_code, None)
        return offer


# ---------------------------------------------------------------------------
# DeviceRegistry — persistensi device (adaptasi brahma_connect/gateway/device_manager.py)
# ---------------------------------------------------------------------------

class DeviceRegistry:
    def __init__(self, registry_path: Path):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._devices: dict[str, DeviceRecord] = {}
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self.registry_path.exists():
                self._devices = {}
                return
            try:
                raw = json.loads(self.registry_path.read_text(encoding="utf-8"))
            except Exception:
                raw = {}
            devices = raw.get("devices", raw) if isinstance(raw, dict) else {}
            self._devices = {
                device_id: DeviceRecord.from_dict(item)
                for device_id, item in (devices or {}).items()
                if isinstance(item, dict)
            }

    def save(self) -> None:
        with self._lock:
            payload = {
                "devices": {
                    device_id: {**record.to_dict(), "key_hash": record.key_hash}
                    for device_id, record in self._devices.items()
                }
            }
            self.registry_path.write_text(
                json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    def list_devices(self) -> list[dict[str, Any]]:
        with self._lock:
            records = sorted(
                self._devices.values(),
                key=lambda r: (r.role != "pc", not r.online, r.name.lower()),
            )
            return [record.to_dict() for record in records]

    def get(self, device_id: str) -> DeviceRecord | None:
        with self._lock:
            return self._devices.get(str(device_id))

    def remove(self, device_id: str) -> bool:
        with self._lock:
            removed = self._devices.pop(str(device_id), None)
            if removed is None:
                return False
            self.save()
            return True

    def revoke(self, device_id: str) -> bool:
        with self._lock:
            record = self._devices.get(str(device_id))
            if record is None:
                return False
            record.revoked = True
            record.online = False
            record.last_seen = now_iso()
            self.save()
            return True

    def create_from_pairing(
        self,
        *,
        name: str,
        role: str = ROLE_CLIENT,
        platform: str = "unknown",
        ip: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> tuple[DeviceRecord, str]:
        """Buat device baru dari pairing. Balikan: (record, device_key asli).

        Sekalian buang rekam client yang sudah revoked (logout / dicabut) —
        rekam itu tidak bisa autentikasi lagi, jadi cuma jadi sampah yang
        bikin daftar device menumpuk tiap kali user pair ulang.
        """
        with self._lock:
            stale = [
                device_id
                for device_id, rec in self._devices.items()
                if rec.role != "pc" and rec.revoked
            ]
            for device_id in stale:
                self._devices.pop(device_id, None)
            device_key = generate_device_key()
            record = DeviceRecord(
                device_id=generate_device_id(platform, name),
                name=name or "Unknown Device",
                role=role if role in ("pc", ROLE_CLIENT) else ROLE_CLIENT,
                platform=(platform or "unknown").lower(),
                ip=ip,
                online=True,
                last_seen=now_iso(),
                paired_at=now_iso(),
                key_hash=hash_secret(device_key),
                revoked=False,
                metadata=dict(metadata or {}),
            )
            self._devices[record.device_id] = record
            self.save()
            return record, device_key

    def authenticate(self, device_id: str, device_key: str, *, ip: str = "") -> DeviceRecord | None:
        with self._lock:
            record = self._devices.get(str(device_id))
            if record is None or record.revoked:
                return None
            if not constant_time_equals(record.key_hash, hash_secret(device_key)):
                return None
            record.online = True
            record.last_seen = now_iso()
            record.ip = ip or record.ip
            self.save()
            return record

    def mark_offline(self, device_id: str) -> None:
        with self._lock:
            record = self._devices.get(str(device_id))
            if record is None:
                return
            record.online = False
            record.last_seen = now_iso()
            self.save()

    def touch(self, device_id: str, *, ip: str = "") -> None:
        with self._lock:
            record = self._devices.get(str(device_id))
            if record is None:
                return
            record.last_seen = now_iso()
            record.online = True
            if ip:
                record.ip = ip
            self.save()
