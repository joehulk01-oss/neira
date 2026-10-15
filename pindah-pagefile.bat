@echo off
rem Pindahkan memori virtual (pagefile) dari C: ke D: - HARUS dijalankan sebagai Administrator.
rem Efek: setelah reboot berikutnya, C:\pagefile.sys (9.4 GB) hilang, D:\pagefile.sys dipakai.
powershell -NoProfile -Command "Get-CimInstance Win32_ComputerSystem | Set-CimInstance -Property @{AutomaticManagedPagefile=$false}"
wmic pagefileset create name="D:\\pagefile.sys"
wmic pagefileset where name="D:\\pagefile.sys" set InitialSize=8192,MaximumSize=16384
wmic pagefileset where name="C:\\pagefile.sys" delete
echo === HASIL PAGEFILE ===
wmic pagefileset list brief
echo === SELESAI ===
