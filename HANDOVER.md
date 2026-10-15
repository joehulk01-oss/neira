# HANDOVER — Neira Remote (APK) + Gateway: status, yang gagal, langkah berikut

_Dokumen ini dibuat otomatis untuk diberikan ke AI lain. Terakhir diperbarui: 2026-09-27 16:16 WIB._

## 1. Ringkasan state

| Item | Status |
|---|---|
| APK WebView ([`neira-android/`](neira-android/)) | ✅ build & install OK, jalan di HP Itel S681LN (Android 13) |
| Gateway HTTPS self-signed ([`neira-gateway/`](neira-gateway/)) | ✅ jalan, HP muat halaman + WS accepted |
| Fitur kirim gambar HP → Neira PC (paste/📎) | ✅ kode lengkap, compile OK — **belum teruji end-to-end** |
| Pairing kode 6 digit | ✅ works (`POST /pair 200`, HP `WebSocket /ws accepted`) |
| **Mic HP (`getUserMedia`)** | ❌ **MASIH GAGAL — error baru: `Could not start audio source`** |

## 2. Masalah yang belum selesai: MIC

### Riwayat error (penting — jangan ulangi diagnosa lama)
1. ~~`Cannot read properties of undefined (reading 'getUserMedia')`~~ — **SUDAH DIPERBAIKI**. Penyebab: halaman dibuka via `http://IP` (non-secure origin) → `navigator.mediaDevices` undefined. Fix: gateway sekarang **TLS** (`https://192.168.1.34:8765`), cert self-signed di-embed ke APK via network security config.
2. Error SEKARANG (setelah TLS fix): `error: izin mic ditolak / tidak tersedia (Could not start audio source)` — `getUserMedia` sudah terpanggil (artinya secure context OK), tapi **gagal start capture audio**.

### Kandidat penyebab (belum terkonfirmasi — device USB offline saat diagnosa)
- **Runtime permission `RECORD_AUDIO`** — pernah dilakukan `adb shell pm clear com.neira.remote` (reset semua permission). Cek status:
  ```
  adb shell dumpsys package com.neira.remote | grep RECORD_AUDIO
  adb shell appops get com.neira.remote RECORD_AUDIO
  ```
  Kalau `granted=false`: `adb shell pm grant com.neira.remote android.permission.RECORD_AUDIO` (hanya untuk user aktif).
- **HP dual-user** — sebelumnya ditemukan entry permission `granted=false` untuk **user 999** dan `pm grant --user 999` gagal: `SecurityException: Shell does not have permission to access user 999`. Kalau app berjalan di user 999 (mode kedua/privasi Itel), shell tidak bisa grant — permission harus lewat dialog dari app itu sendiri. Cek user aktif: `adb shell am get-current-user`.
- **WebView `onPermissionRequest`** — sudah ada handler di [`MainActivity.kt`](neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) (cek `RESOURCE_AUDIO_CAPTURE` → `requestPermissions`). Kalau user pernah menekan "Tolak" + "Jangan tanya lagi", WebView auto-deny → getUserMedia gagal. Solusi: minta user hapus izin manual (Setelan → Aplikasi → Neira → Izin → Mikrofon → Izinkan) atau buat ulang permission request di startup.
- **Mic dipakai app lain** — `Could not start audio source` juga muncul kalau hardware mic busy (NotReadableError). Tutup app perekam/kamera lain.

### Saran langkah berikutnya untuk AI penerima
1. Hubungkan USB, jalankan diagnosa permission di atas (tunggu `adb wait-for-device`, device sempat `offline` berulang).
2. Kalau permission user 999 → tambahkan **izin Mikrofon diminta saat app startup** di `MainActivity.onCreate` (sebelum load URL), supaya dialog sistem muncul sekali dan jelas.
3. Tambah logging detail di JS [`neira-gateway/web/index.html`](neira-gateway/web/index.html) bagian `micStart()`: log `e.name` + `e.message` + `navigator.mediaDevices !== undefined` + `isSecureContext` ke console (sudah diteruskan ke logcat tag `NeiraWeb` via `onConsoleMessage`).
4. Verifikasi dengan: `adb logcat -s NeiraWeb:D chromium:I`.

## 3. Fitur gambar (paste/upload) — kode selesai, belum E2E

Pipeline: web UI [`sendImage()`](neira-gateway/web/index.html) (compress canvas 1280px JPEG 0.82) → WS `type:"image"` → relay server [`server.py`](neira-gateway/gateway/server.py) (`ProtocolTypes.IMAGE` client→PC) → [`GatewayLink._recv_loop`](Mark-LIV-main/dashboard/gateway_link.py) → `_image_queue` (max 8, drop-oldest) → [`main.py::_process_phone_images`](Mark-LIV-main/main.py) → `session.send_client_content` (`inline_data` base64) masuk pipeline vision Neira.

Status verifikasi: `py_compile` semua file OK, JS parse OK, relay & antrean terpasang. **Belum ada tes kirim gambar nyata HP → PC** (butuh Neira `main.py` sesi aktif + HP sudah pair).

## 4. Konfigurasi & perintah kunci

- IP PC: `192.168.1.34` (WiFi). HP: `192.168.1.5`. Gateway: `https://192.168.1.34:8765`.
- Jalankan gateway (TLS): [`neira-gateway/run_local.bat`](neira-gateway/run_local.bat) — uvicorn `--ssl-keyfile certs\key.pem --ssl-certfile certs\cert.pem`. Token: `lokal-uji-token`.
- Regenerate cert bila IP PC berubah:
  ```
  openssl req -x509 -newkey rsa:2048 -nodes -keyout neira-gateway/certs/key.pem -out neira-gateway/certs/cert.pem -days 3650 -subj "/CN=neira.local" -addext "subjectAltName=IP:192.168.1.34,DNS:localhost,DNS:neira.local"
  openssl x509 -in neira-gateway/certs/cert.pem -outform DER -out neira-android/app/src/main/res/raw/neira_cert
  ```
  Lalu update domain IP di [`network_security_config.xml`](neira-android/app/src/main/res/xml/network_security_config.xml) dan **rebuild APK**.
- Config PC: [`Mark-LIV-main/shared/config.env`](Mark-LIV-main/shared/config.env) → `GATEWAY_URL=https://127.0.0.1:8765`, `GATEWAY_TOKEN=lokal-uji-token`. `load_gateway_config()` otomatis meng-upgrade `http://…:8765` → `https://` (backward compat).
- Build+install APK:
  ```
  cd neira-android && gradlew.bat assembleDebug --console=plain -q
  adb install -r app\build\outputs\apk\debug\app-debug.apk
  ```
- Set URL gateway di HP (tanpa buka dialog):
  ```
  adb push neira-android/neira_pref_tmp.xml /data/local/tmp/neira.xml
  adb shell "run-as com.neira.remote cp /data/local/tmp/neira.xml shared_prefs/neira.xml"
  adb shell am force-stop com.neira.remote
  adb shell am start -n com.neira.remote/.MainActivity
  ```
- `adb` tidak di PATH: `C:\Users\Has bin Hacked\AppData\Local\Android\Sdk\platform-tools\adb.exe`.
- Note: `monkey` diblokir di HP ini (`MonkeyMonitorThread not allowed`) → pakai `am start`.

## 5. File yang dimodifikasi sesi ini

- [`neira-gateway/gateway/protocol.py`](neira-gateway/gateway/protocol.py) — `ProtocolTypes.IMAGE`.
- [`neira-gateway/gateway/server.py`](neira-gateway/gateway/server.py) — relay `COMMAND, IMAGE` client→PC.
- [`Mark-LIV-main/dashboard/gateway_link.py`](Mark-LIV-main/dashboard/gateway_link.py) — `_image_queue`, handler `"image"`, `_wss_ssl()`, `new_key()` terima cert self-signed, upgrade http→https :8765.
- [`Mark-LIV-main/main.py`](Mark-LIV-main/main.py) — `_process_phone_images()`, penjadwalan di `run()`, hint error remote key.
- [`neira-gateway/web/index.html`](neira-gateway/web/index.html) — tombol 📎 `#imgbtn`, `compressImage()`, `sendImage()`, handler paste.
- [`neira-gateway/run_local.bat`](neira-gateway/run_local.bat) — jalankan uvicorn dengan TLS.
- [`Mark-LIV-main/shared/config.env`](Mark-LIV-main/shared/config.env) — `GATEWAY_URL=https://127.0.0.1:8765`.
- APK: [`AndroidManifest.xml`](neira-android/app/src/main/AndroidManifest.xml) (`networkSecurityConfig`), [`MainActivity.kt`](neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) (debug WebView, console→logcat, `onReceivedSslError` proceed untuk `:8765`), [`res/xml/network_security_config.xml`](neira-android/app/src/main/res/xml/network_security_config.xml), [`res/raw/neira_cert`](neira-android/app/src/main/res/raw/neira_cert).

## 6. Catatan environment / noise

- Error Pyrefly `Cannot find module fastapi/uvicorn` = linter pakai Python system, bukan venv `Mark-LIV-main\.venv` — bukan error nyata.
- Terminal yang berjalan: (1) uvicorn gateway TLS `0.0.0.0:8765`, (2) `adb wait-for-device` menunggu HP.
- USB ke HP sering putus/`offline` — semua langkah Android harus `adb wait-for-device` dulu.
