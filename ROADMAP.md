# 🧭 NEIRA — ROADMAP & CATATAN LANGKAH (dibuat 27 Sep 2026)

> Dokumen kerja untuk AI (Roo) & pemilik proyek supaya tidak rancang/loncat.
> Perbarui checklist ini setiap kali satu langkah selesai.

## 1. Konsep inti (JANGAN DIRANCUKAN)

```
HP (APK/browser) ──> GATEWAY (relai, FastAPI WS) ──> PC (Neira main.py = otak Gemini Live + skills)
```

- **Mode A — LAN** (di depan PC): gateway lokal di PC (`http://192.168.1.34:8765`).
  Fungsi HP di depan PC: **mikrofon + percakapan saja** (HP = mic nirkabel Neira).
- **Mode B — VPS** (di luar rumah): gateway di VPS publik (`wss://domain-vps`, Caddy :443).
  PC **outbound** ke VPS (NAT-friendly, tanpa buka port rumah).
  Fungsi HP dari jarak jauh: **kontrol penuh PC** — perintah, log/status, upload file, mic percakapan.
- Pindah mode = ganti **satu baris** `GATEWAY_URL` di `Mark-LIV-main/shared/config.env`.
- Tujuan akhir: **Neira PC on 24/7 + bisa diakses Android dari mana pun.**

## 2. Fase & status

### ✅ Fase 0 — Komponen siap (SELESAI)
- [x] LANGKAH 1: gateway code `neira-gateway/` — uji WS 8/8 lulus
- [x] LANGKAH 2: mode GATEWAY_URL (`Mark-LIV-main/dashboard/gateway_link.py` + patch `main.py`) — test PASS
- [x] LANGKAH 3: `Mark-LIV-main/deploy/build_exe.bat` + `installer/neira.iss`
- [x] LANGKAH 5: APK Android `neira-android/app/build/outputs/apk/debug/app-debug.apk` BUILD SUCCESSFUL
- [x] LANGKAH 6: CHANGELOG + UPDATE_LOG entri #19 + regresi test
- [x] Restyle `neira-gateway/web/index.html` + mic getUserMedia → `/ws/phone-audio`

### 🔄 Fase 1 — Uji jalur lokal (SEKARANG, HARI INI)
- [ ] Gateway lokal jalan: `neira-gateway\run_local.bat` (port 8765, token `lokal-uji-token`)
- [ ] `shared/config.env` berisi `GATEWAY_URL=http://127.0.0.1:8765` + `GATEWAY_TOKEN=lokal-uji-token` ✔ (sudah ditambah 27 Sep)
- [ ] Neira desktop (`main.py`) jalan → `/health` balas `pc_online:true` ✔ (sudah terverifikasi 27 Sep)
- [ ] Pair HP: minta kode baru bila expired:
      `curl.exe -s -X POST http://127.0.0.1:8765/pair -H "Authorization: Bearer lokal-uji-token"`
- [ ] APK: set Gateway URL `http://192.168.1.34:8765` → masukkan kode → pair sukses
- [ ] Uji chat teks HP → PC (muncul di log Neira)
- [ ] Uji mic HP → `/ws/phone-audio` → Neira dengar & jawab

### ⬜ Fase 2 — PC on 24/7 (software, tanpa VPS)
- [ ] Matikan sleep/hibernate: `powercfg /change standby-timeout-ac 0` + `powercfg /change hibernate-timeout-ac 0`
- [ ] Auto-start Neira saat login: Scheduled Task (trigger logon, `d:\hack\Neira\Mark-LIV-main\.venv\Scripts\pythonw.exe main.py`) — gantikan klik manual `start.bat`
- [ ] Auto-restart kalau crash: Scheduled Task restart-on-failure / wrapper loop
- [ ] Verifikasi reconnect: GatewayLink + Gemini `_watch_reconnect()` (`Mark-LIV-main/main.py:812`) nyambung sendiri setelah putus
- [ ] (Opsional) matikan auto-update Windows yang me-restart PC

### ⬜ Fase 3 — Akses Android jarak jauh (BUTUH VPS dari user)
- [ ] **User beri: IP/domain VPS + akses SSH** (belum diberikan — ini blokir utama)
- [ ] Di VPS: `cd neira-gateway && cp .env.example .env` (isi `DOMAIN`, `GATEWAY_TOKEN`) → `docker compose up -d`
- [ ] Cek `https://<domain>/health` → `pc_online:false` (belum ada PC)
- [ ] PC pindah mode: `shared/config.env` → `GATEWAY_URL=wss://<domain>` (hapus/buang mode lokal)
- [ ] Restart Neira → `/health` di VPS balas `pc_online:true`
- [ ] APK arahkan `https://<domain>` → pair → uji chat + mic dari **data seluler** (bukan WiFi rumah)
- [ ] Uji kontrol PC dari luar: kirim perintah → `_process_dashboard_commands()` (`Mark-LIV-main/main.py:2079`)

### ⬜ Fase 4 — (Opsional, SETELAH Fase 3 sukses) PC dari kondisi mati total
- [ ] Wake-on-LAN: BIOS + driver NIC (Advanced Properties → Wake on Magic Packet ON)
- [ ] HP kirim paket WOL lewat VPS (atau router port-forward UDP 9)
- [ ] Catatan: selama PC nyala 24/7 (Fase 2), WOL belum diperlukan

### ⬜ Tertunda lain-lain
- [ ] Build EXE nyata: install pyinstaller + Inno Setup 6 → jalankan `build_exe.bat` + `neira.iss`
- [ ] Uji cloning Coqui TTS: `referensi.wav` (3–6 dtk) → `D:\hack\coqui-tts\run.ps1` → `output.wav`
- [ ] Catat karya 5-otak (Dola dkk) ke CHANGELOG
- [ ] Hapus `scratch/Brahma-Echo` **SETELAH** seluruh deploy selesai
- [ ] (Admin) `pindah-pagefile.bat` bila perlu

## 3. Fakta teknis penting (jangan ditanya ulang)
| Item | Nilai |
|---|---|
| IP LAN PC | `192.168.1.34` |
| Gateway lokal port | `8765` (HTTP + WS), admin token `lokal-uji-token` |
| VPS gateway | `wss://<domain>:443` (Caddy TLS) → internal `gateway:8765` |
| APK | `neira-android/app/build/outputs/apk/debug/app-debug.apk` (WebView wrapper, mic sudah diizinkan `onPermissionRequest`) |
| Web UI | diserve gateway di `/` (`neira-gateway/web/index.html`) — dipakai browser HP & APK |
| Audio HP→PC | `getUserMedia` → `AudioContext{16k}` → `ScriptProcessor(4096)` → PCM16 → WS `/ws/phone-audio` → `server.py:365` → AudioHub → `gateway_link.py:_audio_loop` → `main.py:_relay_phone_audio` → Gemini Live |
| Test gateway | `Mark-LIV-main\.venv\Scripts\python.exe neira-gateway\tests\test_gateway_ws.py` (8 uji) |
| Aturan proyek | laporan bahasa Indonesia "saya"; referensi file/sintaks wajib markdown link `[nama](path:baris)`; JANGAN hapus `scratch/Brahma-Echo` sebelum deploy selesai |

## 4. Insiden yang perlu diingat
- **Instance ganda**: `.venv\pythonw.exe` + `C:\Python312\pythonw.exe` pernah jalan bersamaan → jendela/konflik. Selalu tutup semua python lama sebelum launch ulang.
- **Crash Gemini Live**: `TimeoutError: timed out during opening handshake` (`main.py:2171`) = gangguan jaringan ke Google, bukan bug kode — biarkan auto-reconnect.
- **`start.bat` pakai `pythonw.exe`** → error tak terlihat. Untuk diagnosis jalankan: `python.exe main.py > neira_run.log 2>&1`.
- **`timeout /t` & `Get-Content -Tail` hang** di shell non-interaktif VS Code — pakai `ping -n N 127.0.0.1` (delay) dan `cmd /c type` / `findstr` (baca file).
- **Pairing code TTL 300 detik** — kode cepat kedaluwarsa, minta baru saat dibutuhkan.
