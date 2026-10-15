@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo ========================================
echo   MENJALANKAN NEIRA HYBRID (DEBUG MODE)
echo ========================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo [PERINGATAN] Virtual environment .venv belum dibuat!
    echo Menjalankan install.bat terlebih dahulu...
    call install.bat
)

call .venv\Scripts\activate.bat
python main.py
if errorlevel 1 (
    echo.
    echo [INFO] Aplikasi terhenti dengan error. Tekan tombol apa saja untuk menutup.
    pause
)
