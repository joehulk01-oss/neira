# 💻 PC — Neira.exe (desktop, otak penuh)

> Peta lokasi: [`../../README.md`](../../README.md) · ☁️ VPS: [`../../neira-gateway/README.md`](../../neira-gateway/README.md) · 📱 Android: [`../../neira-android/README.md`](../../neira-android/README.md)
>
> **Folder ini (`Mark-LIV-main/deploy/`) = semua yang dipakai untuk build & install EXE di PC.**
> Sumber utama = repo ini ([`../main.py`](../main.py)) — folder ini ikut repo PC karena tool build-nya membangun project ini.

## Peran
Neira lengkap (UI PyQt6 + reactor 3D, Gemini Live + mic/spk, [`skills/`](../skills), [`memory/`](../memory), brain) dikemas jadi
aplikasi Windows yang bisa diinstal di PC mana pun, lalu **keluar (outbound) `wss://` ke VPS Gateway**
supaya HP Android bisa menyambung (aman di balik NAT — tidak perlu buka port rumah).

## Struktur akhir folder ini (saat implementasi)

```
Mark-LIV-main/deploy/      ← folder ini
├── README.md              ← file ini
├── build_exe.bat          # perintah PyInstaller (jalankan dari root repo)
├── installer/
│   └── neira.iss          # skrip Inno Setup → NeiraSetup.exe (shortcut desktop + uninstaller)
└── (hasil build tidak di-commit: dist/Neira/ di root repo)
```

## File sumber yang ikut ke EXE (via `--add-data`)
[`core/prompt.txt`](../core/prompt.txt), [`assets/`](../assets), [`skills/`](../skills), [`shared/`](../shared) (config + memory), [`memory/`](../memory).

## Perintah build (isi `build_exe.bat`)
```
pyinstaller --onedir --windowed --name Neira ^
  --add-data "core/prompt.txt;core" ^
  --add-data "assets;assets" ^
  --add-data "skills;skills" ^
  --add-data "shared;shared" ^
  --collect-all PyQt6 ^
  --collect-all playwright ^
  --collect-all rembg ^
  main.py
```
- `--onedir` (bukan `--onefile`) → startup cepat + aman untuk PyQt6/QtWebEngine.
- `--windowed` → tanpa console.
- Installer: **Inno Setup** membungkus `dist/Neira/` (pola [`_create_desktop_shortcut()`](../ui.py)).

## Config koneksi (di [`shared/config.env`](../shared/config.env))
```
GATEWAY_URL=wss://domain-vps:443
DEVICE_KEY=<token dari pairing>
```
- `GATEWAY_URL` kosong → mode lama (hanya dashboard LAN [`dashboard/server.py`](../dashboard/server.py)).
- `GATEWAY_URL` terisi → client relay aktif: terima `COMMAND` → [`_process_dashboard_commands()`](../main.py),
  kirim `LOG`/`STATUS` (state reaktor, teks log, metrik), `AUDIO` → [`_relay_phone_audio()`](../main.py).

## Perubahan kode yang dibutuhkan (tahap implementasi)
1. Modul gateway di [`neira-gateway/`](../../neira-gateway/README.md) (adaptasi `brahma_connect`) + uji WS lokal.
2. Mode `GATEWAY_URL` di [`main.py`](../main.py) — koneksi outbound + auto-reconnect (PING/PONG).
3. `build_exe.bat` + `installer/neira.iss` di folder ini.
4. Uji exe di PC bersih: boot reactor jalan, pairing QR muncul ([`RemoteKeyOverlay`](../ui.py)), perintah dari HP diterima.

## Uji
```
deploy\build_exe.bat               # hasil di dist/Neira/Neira.exe
dist\Neira\Neira.exe               # jalankan: cek boot animasi + pairing
```
Regresi saat build dari sumber: `test_reactor3d.py`, `test_ui_restyle.py`, `test_brahma_adoptions.py` tetap hijau.
