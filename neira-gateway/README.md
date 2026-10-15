# ☁️ VPS — Neira Gateway (relay tipis, stateless)

> Peta lokasi: [`../README.md`](../README.md) · 💻 PC: [`../Mark-LIV-main/deploy/README.md`](../Mark-LIV-main/deploy/README.md) · 📱 Android: [`../neira-android/README.md`](../neira-android/README.md)
>
> **Folder ini = semua yang di-install/di-deploy ke VPS.** Repo GitHub: **`neira-gateway`** (disarankan private).

## Peran
Relay pesan antara PC (otak) dan klien (HP Android / browser). **Tidak menyimpan API key, memori, atau logik AI.**
Tugasnya: otentikasi device, pairing, dan meneruskan `COMMAND`/`LOG`/`STATUS`/`AUDIO`.

## Struktur akhir folder ini (saat implementasi)

```
neira-gateway/           ← folder ini (repo "neira-gateway")
├── README.md            ← file ini
├── gateway/
│   ├── server.py        # FastAPI + uvicorn, port 8765: /ws (device), /ws/phone-audio, /auto-login, /pair
│   ├── websocket.py     # ConnectionHub (attach/register/unregister/broadcast) — adaptasi brahma_connect/gateway/websocket.py
│   ├── protocol.py      # build_message()/validate_message() — adaptasi brahma_connect/gateway/protocol.py
│   └── devices.py       # registry device + pairing token (DEVICE_KEY, token sekali-pakai)
├── web/                 # (opsional) dashboard statis untuk browser HP
├── Dockerfile
├── docker-compose.yml   # gateway + caddy (TLS Let's Encrypt otomatis)
├── Caddyfile            # reverse-proxy :443 → gateway:8765, auto-HTTPS
├── .env.example         # GATEWAY_TOKEN=, DOMAIN=, PORT=8765
```

## Langkah deploy VPS (sekali jalan)
```
git clone git@github.com:<akun>/neira-gateway.git && cd neira-gateway
cp .env.example .env        # isi GATEWAY_TOKEN + DOMAIN
docker compose up -d        # gateway + Caddy TLS aktif
```

## Protokol (dipakai bersama oleh EXE & Android)
1. **Pairing:** klien kirim `PAIR_REQUEST` (token sekali-pakai dari QR) → VPS balas `PAIR_APPROVED` + `DEVICE_KEY` permanen (disimpan di `devices.py`).
2. **Heartbeat:** `PING`/`PONG` tiap ~15 dtk + reconnect exponential backoff.
3. **Relay:** `COMMAND` (klien→PC, diproses [`_process_dashboard_commands()`](../Mark-LIV-main/main.py)), `LOG`/`STATUS` (PC→klien, `broadcast()`), `AUDIO` (`/ws/phone-audio` → [`_relay_phone_audio()`](../Mark-LIV-main/main.py)).
4. **Auto-update (opsional):** klien poll hash-git dari VPS (pola `core/updater.py` Brahma-Echo).

## Referensi kode
| Mekanisme | Sumber pola (Brahma-Echo) | Output di folder ini |
|---|---|---|
| WS server + token auth | `Mark-LIV-main/scratch/Brahma-Echo/brahma_connect/gateway/server.py` (`BrahmaGatewayConfig`, `_pair_device()`, `serve()`) | `gateway/server.py` |
| Hub koneksi | `Mark-LIV-main/scratch/Brahma-Echo/brahma_connect/gateway/websocket.py` (`ConnectionHub`) | `gateway/websocket.py` |
| Protokol pesan | `Mark-LIV-main/scratch/Brahma-Echo/brahma_connect/gateway/protocol.py` (`build_message`/`validate_message`) | `gateway/protocol.py` |
| Relay audio + dashboard lokal | — | [`../Mark-LIV-main/dashboard/server.py`](../Mark-LIV-main/dashboard/server.py) (`/ws`, `/ws/phone-audio`, `broadcast`) |

## Uji
- Lokal: jalankan gateway → `wss://127.0.0.1:8765` dari skrip uji klien (PAIR → PING → COMMAND bolak-balik).
- VPS: HP scan QR → tersambung → kirim perintah → log muncul balik.
