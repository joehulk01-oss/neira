@echo off
chcp 65001 >nul
:: Pastikan direktori kerja selalu mengarah ke folder tempat file bat ini berada
cd /d "%~dp0"

echo ========================================
echo   JARVIS HYBRID - INSTALASI OTOMATIS
echo ========================================
echo.

if not exist ".venv\Scripts\activate.bat" (
    echo [1/4] Membuat Virtual Environment (.venv)...
    python -m venv .venv
    if errorlevel 1 goto error
) else (
    echo [1/4] Virtual Environment (.venv) sudah ada, lanjut...
)

echo [2/4] Mengaktifkan Virtual Environment...
call .venv\Scripts\activate.bat

echo [3/4] Menginstal/memperbarui library...
python.exe -m pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto error

echo [4/4] Menyiapkan folder dan struktur memori...
if not exist "shared\memory" mkdir shared\memory
if not exist "shared\logs" mkdir shared\logs
if not exist "hermes-agent\data\memories" mkdir hermes-agent\data\memories
if not exist "hermes-agent\data\skills" mkdir hermes-agent\data\skills

echo.
echo ========================================
echo   INSTALASI BERHASIL!
echo   Jalankan 'start.bat' untuk memulai.
echo ========================================
pause
exit /b 0

:error
echo.
echo [ERROR] TERJADI KESALAHAN PADA INSTALASI!
echo Pastikan Python 3.11-3.13 sudah terinstal dan ditambahkan ke PATH Windows.
pause
exit /b 1
