@echo off
REM ============================================================================
REM  Neira — build Neira.exe (PyInstaller --onedir --windowed)
REM  Jalankan dari folder ini:  deploy\build_exe.bat
REM  Prasyarat : .venv dengan PyInstaller
REM      Mark-LIV-main\.venv\Scripts\pip install pyinstaller
REM  Hasil     : dist\Neira\Neira.exe
REM  Lanjut    : bungkus installer via deploy\installer\neira.iss (Inno Setup 6)
REM
REM  Catatan mode remote (opsional): isi GATEWAY_URL + GATEWAY_TOKEN di
REM  shared/config.env SEBELUM build supaya ikut terbawa, atau edit setelah
REM  install (kosong = mode LAN lama, dashboard lokal).
REM ============================================================================
setlocal
cd /d "%~dp0.."

echo [1/2] PyInstaller --onedir --windowed ...
pyinstaller --noconfirm --clean --onedir --windowed --name Neira ^
    --add-data "core/prompt.txt;core" ^
    --add-data "assets;assets" ^
    --add-data "skills;skills" ^
    --add-data "shared;shared" ^
    --add-data "dashboard/static;dashboard/static" ^
    --collect-all PyQt6 ^
    --collect-all playwright ^
    --collect-all rembg ^
    --collect-submodules websockets ^
    main.py

if errorlevel 1 (
    echo [GAGAL] PyInstaller gagal — lihat pesan error di atas.
    exit /b 1
)

echo [2/2] Selesai: dist\Neira\Neira.exe
echo        Installer: buka deploy\installer\neira.iss di Inno Setup Compiler.
endlocal
