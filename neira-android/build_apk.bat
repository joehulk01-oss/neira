@echo off
rem Build APK Neira Remote (fase 1 WebView) - hasil: app\build\outputs\apk\debug\app-debug.apk
rem Strategi: pakai Gradle yang SUDAH ada di cache (D:\pindah-c\.gradle hasil pindah dari C:),
rem fallback ke %USERPROFILE%\.gradle, lalu terakhir ke wrapper (unduh sekali).
setlocal
cd /d "%~dp0"
set "JAVA_HOME=C:\Program Files\Android\Android Studio\jbr"
set "GRADLE_USER_HOME=D:\pindah-c\.gradle"
set "GRADLE_CMD="
for /d %%G in ("D:\pindah-c\.gradle\wrapper\dists\gradle-8.7-bin\*" "%USERPROFILE%\.gradle\wrapper\dists\gradle-8.7-bin\*") do (
    if exist "%%G\gradle-8.7\bin\gradle.bat" set "GRADLE_CMD=%%G\gradle-8.7\bin\gradle.bat"
)
if defined GRADLE_CMD (
    echo Memakai Gradle dari cache: "%GRADLE_CMD%"
    call "%GRADLE_CMD%" assembleDebug
) else (
    echo Gradle cache tidak ada, memakai wrapper - akan unduh sekali.
    call "%~dp0gradlew.bat" assembleDebug
)
if errorlevel 1 (
    echo.
    echo BUILD GAGAL - lihat pesan error di atas.
    exit /b 1
)
echo.
echo APK siap: %~dp0app\build\outputs\apk\debug\app-debug.apk
endlocal
