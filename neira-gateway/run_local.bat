@echo off
REM ============================================================================
REM  Neira Gateway — jalankan LOKAL (tanpa Docker/VPS) untuk uji end-to-end.
REM  Pakai Python venv Mark-LIV-main (sudah ada fastapi/uvicorn/websockets).
REM
REM  1. Jalankan script ini            -> gateway di https://localhost:8000 (TLS)
REM     Cert di-generate otomatis tiap start (certs\gen_certs.py): CA lokal
REM     (ca.pem — trust anchor di APK) + leaf SAN semua IP LAN aktif + localhost,
REM     jadi tahan ganti IP (WiFi / hotspot HP / tether).
REM     HP pakai https://IP-PC:8000 -> secure origin -> mic OK (tanpa USB).
REM  2. Di shared/config.env (PC) isi  -> GATEWAY_URL=https://{LAN_IP}:8000
REM                                       GATEWAY_TOKEN=lokal-uji-token
REM  3. Jalankan Neira (main.py) -> tombol Remote Control -> scan QR dari HP
REM     (QR membuka halaman web/index.html di gateway = klien uji di HP).
REM ============================================================================
cd /d "%~dp0"
:: Guard anti double-instance: kalau port 8000 sudah ada yang listen, keluar saja.
netstat -ano | findstr "LISTENING" | findstr ":8000" >nul 2>&1
if not errorlevel 1 (
    echo [Neira Gateway] sudah berjalan di port 8000 - tidak menyalakan duplikat.
    exit /b 0
)
if "%GATEWAY_TOKEN%"=="" set GATEWAY_TOKEN=lokal-uji-token
echo [Neira Gateway] token: %GATEWAY_TOKEN%  (samaran di .env VPS nanti)
echo [Neira Gateway] menyiapkan cert TLS dinamis (SAN = IP LAN aktif)...
..\Mark-LIV-main\.venv\Scripts\python.exe certs\gen_certs.py
if errorlevel 1 (
    echo [Neira Gateway] GAGAL generate cert — cek venv / "pip install cryptography".
    pause
    exit /b 1
)
..\Mark-LIV-main\.venv\Scripts\python.exe -m uvicorn gateway.server:app --host 0.0.0.0 --port 8000 --ssl-keyfile certs\key.pem --ssl-certfile certs\cert.pem
