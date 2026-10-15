@echo off
chcp 65001 >nul
:: Pastikan direktori kerja selalu mengarah ke folder tempat file bat ini berada
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo ========================================
    echo   PERSIAPAN AWAL
    echo ========================================
    echo [PERINGATAN] Virtual environment .venv belum dibuat!
    echo Menjalankan install.bat terlebih dahulu...
    call install.bat
)

:: Auto-start Neira Gateway lokal bila belum berjalan (cek port 8000).
:: run_local.bat otomatis generate cert TLS sesuai IP LAN aktif (tanpa IP hardcode).
netstat -ano | findstr "LISTENING" | findstr ":8000" >nul 2>&1
if errorlevel 1 (
    echo [Neira] Gateway lokal belum jalan - menyalakan otomatis di background...
    start "" /min "%~dp0..\neira-gateway\run_local.bat"
)

:: Jalankan aplikasi menggunakan pythonw.exe agar jendela CMD langsung tertutup secara otomatis
start "" ".venv\Scripts\pythonw.exe" main.py
exit
