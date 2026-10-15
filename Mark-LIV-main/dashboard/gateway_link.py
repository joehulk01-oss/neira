"""dashboard/gateway_link.py — klien "Neira Gateway" untuk mode remote (GATEWAY_URL).

Dipakai main.py saat shared/config.env (atau environment) berisi GATEWAY_URL —
Neira.exe di PC tersambung KELUAR (outbound wss://) ke gateway di VPS, lalu
klien (HP/browser) menerima LOG/STATUS dan mengirim COMMAND lewat gateway itu.

Antarmuka sengaja disamakan dengan DashboardServer supaya main.py cukup menukar
objek:
    ._command_queue       asyncio.Queue[str]  — perintah teks dari klien (HP)
    ._image_queue         asyncio.Queue[dict] — gambar dari HP {"data": bytes, "mime_type", "caption"}
    ._phone_audio_queue   asyncio.Queue[dict] — {"data": bytes, "mime_type": "audio/pcm"}
    .broadcast(dict)      — {"type": "log"/"status", ...} → semua klien
    .new_key() / .get_url() / .get_manual_url() / .get_auto_url() — QR pairing
    .set_connect_callback(fn) / .serve()

GATEWAY_URL kosong → mode LAN lama (dashboard.server.DashboardServer); modul ini
tidak dipakai sama sekali.
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
from uuid import uuid4

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_ENV = BASE_DIR / "shared" / "config.env"


def detect_lan_ip() -> str:
    """IP LAN aktif yang dideteksi otomatis — TANPA hardcode.
    IP PC sering ganti (WiFi tetangga / hotspot HP / tether HP), jadi trik
    UDP-connect dipakai untuk tahu interface default yang benar saat ini."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass
    return "127.0.0.1"


def load_gateway_config() -> tuple[str, str]:
    """Balikan (GATEWAY_URL, GATEWAY_TOKEN). Environment menang, fallback shared/config.env."""
    url = token = ""
    try:
        for line in CONFIG_ENV.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip('"').strip("'")
            if key == "GATEWAY_URL":
                url = value
            elif key == "GATEWAY_TOKEN":
                token = value
    except Exception:
        pass
    url = os.environ.get("GATEWAY_URL", url).strip()
    token = os.environ.get("GATEWAY_TOKEN", token).strip()
    # Placeholder dinamis — IP boleh berubah kapan saja, jangan pernah hardcode:
    #   GATEWAY_URL=https://{LAN_IP}:8000   (atau cukup "auto")
    if url and ("{LAN_IP}" in url or url.lower() in ("auto", "https://auto", "https://auto:8000")):
        lan_ip = detect_lan_ip()
        url = url.replace("{LAN_IP}", lan_ip) if "{LAN_IP}" in url else f"https://{lan_ip}:8000"
        print(f"[Gateway] GATEWAY_URL dinamis → {url} (IP LAN terdeteksi: {lan_ip})")
    # Gateway lokal (:8000) sekarang selalu TLS (cert di neira-gateway/certs,
    # di-generate otomatis oleh certs/gen_certs.py). http:// ke port itu ditolak
    # mentah-tulang oleh uvicorn ("Remote end closed connection") — paksa https://.
    if url.startswith("http://") and ":8000" in url:
        url = "https://" + url[len("http://"):]
        print("[Gateway] GATEWAY_URL dipaksa https (gateway lokal pakai TLS): " + url)
    return url, token


def _msg(mtype: str, payload: dict | None = None) -> dict:
    """Susun pesan protokol gateway (format sama dengan gateway/protocol.py)."""
    return {
        "type": mtype,
        "request_id": uuid4().hex,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }


class GatewayLink:
    def __init__(self, gateway_url: str, gateway_token: str, device_id: str = "neira-pc"):
        self.gateway_url = (gateway_url or "").rstrip("/")
        self.gateway_token = gateway_token
        self.device_id = device_id
        self._command_queue: asyncio.Queue = asyncio.Queue()
        self._image_queue: asyncio.Queue = asyncio.Queue(maxsize=8)
        self._phone_audio_queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._connect_callback = None
        self._ws = None            # koneksi /ws (perintah + log/status)
        self._audio = None         # koneksi /ws/phone-audio (PCM biner)
        self._last_offer: dict = {}
        self._running = False

    # ── URL / QR pairing (antarmuka sama dengan DashboardServer) ──────────

    def _ws_base(self) -> str:
        base = self.gateway_url
        if base.startswith("https://"):
            return "wss://" + base[len("https://"):]
        if base.startswith("http://"):
            return "ws://" + base[len("http://"):]
        return base  # sudah ws:// atau wss://

    def get_url(self) -> str:
        return self.gateway_url

    def get_manual_url(self) -> str:
        return self.gateway_url

    def get_auto_url(self) -> str:
        """URL halaman web klien + token pairing (isi QR). Scan HP → auto-pair;
        app Android fase 1 (WebView) memuat URL yang sama."""
        offer = self._last_offer or {}
        return (
            f"{self.gateway_url}/?token={quote(str(offer.get('pairing_token', '')), safe='')}"
            f"&code={quote(str(offer.get('pairing_code', '')), safe='')}"
        )

    def new_key(self) -> str:
        """Buat token pairing sekali-pakai di gateway (POST /pair). Balikan: kode 6 digit."""
        request = urllib.request.Request(
            self.gateway_url + "/pair",
            method="POST",
            headers={"Authorization": f"Bearer {self.gateway_token}"},
        )
        # Gateway lokal HTTPS pakai cert self-signed — jangan gagal di TLS check.
        ctx = None
        if self.gateway_url.startswith("https://"):
            import ssl
            ctx = ssl._create_unverified_context()
        with urllib.request.urlopen(request, timeout=8, context=ctx) as response:
            data = json.loads(response.read().decode("utf-8"))
        self._last_offer = data.get("pairing") or {}
        return str(self._last_offer.get("pairing_code", ""))

    def set_connect_callback(self, fn) -> None:
        self._connect_callback = fn

    # ── kirim ke klien ────────────────────────────────────────────────────

    async def broadcast(self, msg: dict) -> None:
        """Peta pesan gaya dashboard lama → protokol gateway (log/status)."""
        mtype = "status" if str(msg.get("type", "")) == "status" else "log"
        payload = {k: v for k, v in msg.items() if k != "type"}
        ws = self._ws
        if ws is None:
            return
        try:
            await ws.send(json.dumps(_msg(mtype, payload)))
        except Exception:
            pass

    async def send_audio(self, data: bytes) -> None:
        """Kirim frame PCM (TTS) ke semua klien lewat kanal audio biner."""
        ws = self._audio
        if ws is None:
            return
        try:
            await ws.send(data)
        except Exception:
            pass

    # ── loop koneksi (auto-reconnect) ─────────────────────────────────────

    def _wss_ssl(self):
        """SSL context untuk wss:// — cert self-signed gateway lokal diterima."""
        if not self._ws_base().startswith("wss://"):
            return None
        import ssl
        return ssl._create_unverified_context()

    async def serve(self) -> None:
        """Jalankan selamanya — sambung ke gateway, putus → coba lagi (backoff 3–30 dtk)."""
        import websockets

        self._running = True
        delay = 3.0
        while self._running:
            # Self-heal: jaringan bisa berganti (WiFi / hotspot HP / tether) —
            # resolusi ulang {LAN_IP} tiap kali mau menyambung, tanpa restart app.
            try:
                cfg_url, cfg_token = load_gateway_config()
                if cfg_url and cfg_url != self.gateway_url:
                    print(f"[Gateway] Alamat berubah → {cfg_url} (IP jaringan berubah)")
                    self.gateway_url = cfg_url.rstrip("/")
                if cfg_token:
                    self.gateway_token = cfg_token
            except Exception:
                pass
            try:
                async with websockets.connect(
                    self._ws_base() + "/ws", max_size=8_000_000,
                    ssl=self._wss_ssl()
                ) as ws:
                    self._ws = ws
                    await ws.send(json.dumps(_msg("authenticate", {
                        "role": "pc",
                        "device_id": self.device_id,
                        "device_key": self.gateway_token,
                    })))
                    ack = json.loads(await ws.recv())
                    if ack.get("type") != "device_online":
                        raise RuntimeError(f"Auth ditolak gateway: {ack}")
                    print(f"[Gateway] Terhubung ke {self.gateway_url} (role=pc)")
                    delay = 3.0
                    audio_task = asyncio.create_task(self._audio_loop())
                    try:
                        await self._recv_loop(ws)
                    finally:
                        audio_task.cancel()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                print(f"[Gateway] Koneksi terputus: {exc} — coba lagi {delay:.0f}s")
            finally:
                self._ws = None
                self._audio = None
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30.0)

    async def _recv_loop(self, ws) -> None:
        heartbeat = asyncio.create_task(self._heartbeat(ws))
        try:
            while True:
                raw = await ws.recv()
                try:
                    message = json.loads(raw)
                except Exception:
                    continue
                mtype = str(message.get("type", ""))
                payload = message.get("payload") or {}
                if mtype == "command":
                    text = str(payload.get("text", "")).strip()
                    if text:
                        await self._command_queue.put(text)
                elif mtype == "image":
                    # Gambar dari HP (paste/upload) — serahkan ke main.py untuk
                    # dikirim ke sesi Gemini sebagai inline_data (vision).
                    try:
                        raw = base64.b64decode(str(payload.get("data", "")))
                    except Exception:
                        raw = b""
                    if raw:
                        self._put_image({
                            "data": raw,
                            "mime_type": str(payload.get("mime_type") or "image/png"),
                            "caption": str(payload.get("caption") or ""),
                        })
                elif mtype == "device_online":
                    if payload.get("role") == "client" and self._connect_callback:
                        try:
                            self._connect_callback()
                        except Exception:
                            pass
                elif mtype == "audio":
                    data = base64.b64decode(str(payload.get("data", "")))
                    if data:
                        self._queue_audio(data)
        finally:
            heartbeat.cancel()

    async def _heartbeat(self, ws) -> None:
        while True:
            await asyncio.sleep(15)
            await ws.send(json.dumps(_msg("ping")))

    async def _audio_loop(self) -> None:
        """Kanal audio biner: mic HP → _phone_audio_queue (bentuk sama dashboard lama)."""
        import websockets

        url = (
            self._ws_base() + "/ws/phone-audio"
            f"?device_id={quote(self.device_id)}&device_key={quote(self.gateway_token)}"
        )
        try:
            async with websockets.connect(
                url, max_size=8_000_000, ssl=self._wss_ssl()
            ) as ws:
                self._audio = ws
                while True:
                    data = await ws.recv()
                    if isinstance(data, bytes):
                        self._queue_audio(data)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            print(f"[Gateway] Kanal audio terputus: {exc}")

    def _queue_audio(self, data: bytes) -> None:
        try:
            self._phone_audio_queue.put_nowait(
                {"data": data, "mime_type": "audio/pcm"}
            )
        except asyncio.QueueFull:
            pass

    def _put_image(self, item: dict) -> None:
        try:
            self._image_queue.put_nowait(item)
        except asyncio.QueueFull:
            # Antrean penuh (8 gambar tertunda) — buang yang lama, simpan yang baru.
            try:
                self._image_queue.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                self._image_queue.put_nowait(item)
            except asyncio.QueueFull:
                pass
