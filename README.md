# 🗺️ Neira — Peta Lokasi Folder (biar tidak bingung)

> **Status: RENCANA deploy (belum ada kode).** 25–26 September 2026 — lanjut besok (entri #19 di [`UPDATE_LOG.md`](Mark-LIV-main/UPDATE_LOG.md)).
> Setiap mesin punya folder sendiri-sendiri **sesuai lokasi fisiknya** — buka folder itu kalau mau kerja untuk mesin tersebut.

## Pembagian Lokasi (folder mana = mesin mana)

```
d:\hack\Neira\
├── README.md          ← file ini (peta lokasi)
├── Mark-LIV-main\     ← 💻 PC — project utama (otak Neira + UI)
│   └── deploy\            panduan build & install Neira.exe (PyInstaller + Inno Setup)
├── neira-gateway\     ← ☁️ VPS — repo "Neira Gateway" (relay tipis, Docker + TLS)
├── neira-android\     ← 📱 HP — repo "neira-android" (app remote Neira)
├── scratch\           ← uji-coba & kode referensi eksternal (Brahma-Echo dll)
└── Mark-LIV-main.zip  ← arsip cadangan
```

| Mesin | Folder | Isi | Bentuk akhir | Repo sumber |
|---|---|---|---|---|
| 💻 **PC** | [`Mark-LIV-main/`](Mark-LIV-main/deploy/README.md) | otak + UI + [`skills/`](Mark-LIV-main/skills) + [`deploy/`](Mark-LIV-main/deploy/README.md) (build EXE) | `Neira.exe` | repo ini |
| ☁️ **VPS** | [`neira-gateway/`](neira-gateway/README.md) | kode gateway (server/WS/protocol/devices) + Docker | container "Neira Gateway" | `neira-gateway` (baru) |
| 📱 **HP Android** | [`neira-android/`](neira-android/README.md) | app Android (fase 1 WebView → fase 2 Kotlin) | `neira.apk` | `neira-android` (baru) |

## Prinsip (tidak berubah)
- **Otak (AI, memori, skill) TETAP di PC.** VPS hanya relay + otentikasi — tanpa API key.
- Semua klien koneksi **outbound `wss://`** ke VPS (aman di balik NAT, tidak perlu buka port rumah).
- Protokol sama untuk EXE & Android — adaptasi `brahma_connect`:
  `PAIR_REQUEST`/`PAIR_APPROVED` → `PING`/`PONG` → relay `COMMAND`/`LOG`/`STATUS`/`AUDIO` → auto-update hash-git.

## Urutan Kerja Besok (jadi entri #19)
1. [`neira-gateway/`](neira-gateway/README.md): kode gateway adaptasi brahma_connect + uji WS lokal.
2. Mode `GATEWAY_URL` di [`main.py`](Mark-LIV-main/main.py) (kosong = mode LAN lama).
3. [`Mark-LIV-main/deploy/`](Mark-LIV-main/deploy/README.md): `build_exe.bat` + Inno Setup → `Neira.exe`.
4. [`neira-gateway/`](neira-gateway/README.md): Dockerfile + docker-compose + Caddy → deploy ke VPS.
5. [`neira-android/`](neira-android/README.md): app fase 1 (WebView wrapper).
6. Catat [`CHANGELOG.md`](Mark-LIV-main/CHANGELOG.md) + [`UPDATE_LOG.md`](Mark-LIV-main/UPDATE_LOG.md) + regresi test.

**Catatan tertunda lain:** karya 5-otak (Dola dkk) belum tercatat di CHANGELOG — lanjutkan saat resume.
