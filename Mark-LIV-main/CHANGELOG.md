# 📋 JARVIS / NEIRA / HERMES — ARSITEKTUR & CHANGELOG SISTEM

Dokumen ini mencatat seluruh pembaruan arsitektur, penambahan skill, serta daftar komponen yang diubah atau sudah tidak terpakai (deprecated/obsolete) agar pengembangan sistem tetap terarah dan transparan.

> **Catatan cepat untuk update berikutnya:** setiap perubahan WAJIB dicatat juga di [`UPDATE_LOG.md`](UPDATE_LOG.md) (ringkas + actionable: file yang diubah, cara extend, cara uji). Dokumen ini = detail arsitektur; [`UPDATE_LOG.md`](UPDATE_LOG.md) = riwayat perubahan & peta kode.

---

## 📅 Pembaruan: 29 September 2026 (malam) — APK "Halaman Tidak Tersedia" → Paksa https:// untuk Host Privat (Entri #23)

### 🌟 1. Ringkasan Perubahan Utama (What Changed)
1. **Akar "halaman tidak tersedia" di APK (koreksi user: browser PC bisa, APK tidak).** Gateway lokal ([`run_local.bat`](../neira-gateway/run_local.bat) → uvicorn `--ssl-keyfile/--ssl-certfile`) **hanya melayani TLS**. Prefs APK menyimpan `http://192.168.1.28:8000` → WebView gagal. Bukti: `https://...:8000/health` = **200** vs `http://...:8000/health` = **`000`**. Browser PC tetap bisa karena meng-upgrade ke https; WebView tidak.
2. **[`MainActivity.kt`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) memaksa `https://` untuk host privat.** [`onCreate()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt:63) memigrasikan prefs lama (skema + `:8765`→`:8000`); [`normalize()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt:418) meng-upgrade input `http://<host-privat>:8000` → `https://` (domain publik/VPS tidak disentuh); [`setupWebView()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt:138) menambah `MIXED_CONTENT_COMPATIBILITY_MODE`.
3. **Teori firewall DIBUANG:** dari emulator, `toybox nc -w 2 <IP> 8000` → `exit_0` (port TCP terbuka). `ping` ke PC 100% loss (ICMP diblokir) — bukan indikator. Tidak perlu aturan `netsh advfirewall` (dan memang butuh elevation).
4. **Verifikasi live:** prefs APK auto-migrasi ke `https://192.168.1.28:8000` dan `curl -sk https://localhost:8000/health` → `{"status":"ok","gateway":"Neira Gateway","pc_online":true,"clients":1}` (**clients:1** = WebSocket APK tersambung).

### 📊 2. Cara Uji
```
neira-android\build_apk.bat
D:\LDPlayer\LDPlayer9\adb.exe install -r neira-android\app\build\outputs\apk\debug\app-debug.apk
D:\LDPlayer\LDPlayer9\adb.exe shell run-as com.neira.remote cat shared_prefs/neira.xml   # gateway_url = https://IP:8000
curl -sk https://localhost:8000/health                                                   # pc_online:true, clients:1
```

### ⏳ 3. Belum
- Uji fisik end-to-end di HP asli (bukan hanya emulator LDPlayer) dengan pairing 6 digit.

## 📅 Pembaruan: 29 September 2026 (malam) — Port Web Gateway 8000 + Kode Pair Angka di Mode LAN + Config Tak Terhapus + APK Self-Heal (Entri #22)

### 🌟 1. Ringkasan Perubahan Utama (What Changed)
1. **Port web gateway = 8000** (koreksi user, sebelumnya salah 8765). Seluruh rantai di-re-alias: [`run_local.bat`](../neira-gateway/run_local.bat) (`--port 8000`), [`NeiraGatewayConfig`](../neira-gateway/gateway/server.py) default 8000, [`load_gateway_config()`](dashboard/gateway_link.py:62) fallback `:8000`, [`start.bat`](start.bat) cek `netstat :8000`, hint & whitelist SSL [`MainActivity.kt`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) `:8000`, placeholder [`index.html`](../neira-gateway/web/index.html) `:8000`, [`shared/config.env`](shared/config.env) `GATEWAY_URL=https://{LAN_IP}:8000`.
2. **Akar bug "gateway gak konek" terungkap:** [`sync_all_configs()`](memory/config_manager.py) me-rewrite [`shared/config.env`](shared/config.env) tanpa membawa `GATEWAY_URL`/`GATEWAY_TOKEN` → tiap Apply/Save, Neira **diam-diam** kembali ke mode LAN [`DashboardServer`](dashboard/server.py) (yang juga memakai port 8000 — membingungkan saat diagnosa). Kini [`sync_all_configs()`](memory/config_manager.py) mempertahankan `GATEWAY_URL`/`GATEWAY_TOKEN`/`AUTOSTART_LOCAL_GATEWAY`.
3. **Kode pairing = ANGKA SAJA di semua mode.** [`_KEY_CHARS`](dashboard/server.py:69) (mode LAN) diubah dari huruf+angka → `string.digits` 6 digit, konsisten dengan [`create_offer()`](../neira-gateway/gateway/devices.py:132) mode gateway dan keyboard numeric APK — user sebelumnya "g bisa nulis id pairing karena ada huruf".
4. **APK self-heal:** [`isPrivateHost()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) + migrasi halus URL tersimpan `:8765`→`:8000` (hanya host privat); whitelist SSL [`onReceivedSslError`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) menerima `:8000` **dan** `:8765` (kompatibilitas APK lama).
5. **Anti double-instance:** [`run_local.bat`](../neira-gateway/run_local.bat) (guard `netstat :8000`) + [`main.py`](main.py) (cek socket `127.0.0.1:8000` sebelum autostart) — jawaban "APA HARUS klik run_local.bat?": **TIDAK**, [`start.bat`](start.bat) / [`main.py`](main.py) auto-start, idempoten.

### 📊 2. Cara Uji
```
Mark-LIV-main\.venv\Scripts\python.exe neira-gateway\tests\test_gateway_ws.py     # 8/8 lulus
Mark-LIV-main\.venv\Scripts\python.exe Mark-LIV-main\scratch\test_gateway_link.py # PASS
curl -sk https://localhost:8000/health   # {"status":"ok",...,"pc_online":true}
neira-android\build_apk.bat              # BUILD SUCCESSFUL → adb install -r
```

### ⏳ 3. Belum
- Uji fisik end-to-end HP↔PC setelah install APK baru (pairing 6 digit + koneksi API di HP).

## 📅 Pembaruan: 29 September 2026 (malam) — Koneksi Tahan Ganti IP (Dinamis, Tanpa IP Hardcode) + Kode Pair Angka Saja (Entri #21)

### 🌟 1. Ringkasan Perubahan Utama (What Changed)
1. **Prinsip baru: tidak ada IP hardcode.** IP PC sering berubah (WiFi tetangga / hotspot HP / tether HP), maka semua komponen kini dinamis:
   - **Web UI ([`web/index.html`](../neira-gateway/web/index.html))**: [`gatewayBase()`](../neira-gateway/web/index.html:555) selalu [`location.origin`](../neira-gateway/web/index.html:555) — alamat yang ditampilkan di panel ⚙️ **pasti sama** dengan gateway yang benar-benar dilayani (menghapus bug "IP di setelan beda dengan IP gateway" akibat override `localStorage`). Tombol simpan kini **menavigasi** ([`location.href`](../neira-gateway/web/index.html)) ke alamat baru, bukan menyimpan override. Input kode pairing (`#code`/`#sp-code`) kini **angka saja** maks 6 digit — cocok dengan keyboard numeric APK.
   - **PC ([`dashboard/gateway_link.py`](dashboard/gateway_link.py))**: [`detect_lan_ip()`](dashboard/gateway_link.py:36) mendeteksi IP LAN aktif runtime (trik UDP-connect); [`load_gateway_config()`](dashboard/gateway_link.py) resolve placeholder `{LAN_IP}` di [`shared/config.env`](shared/config.env) (`GATEWAY_URL=https://{LAN_IP}:8765`); [`serve()`](dashboard/gateway_link.py) **self-heal** — resolve ulang tiap reconnect, jadi ganti jaringan otomatis terlayani tanpa restart Neira.
   - **TLS cert ([`../neira-gateway/certs/gen_certs.py`](../neira-gateway/certs/gen_certs.py), BARU)**: skema **CA lokal + leaf SAN dinamis**. CA (`ca.pem`, 10 tahun) dibuat sekali dan di-embed di APK sebagai trust anchor ([`raw/neira_cert`](../neira-android/app/src/main/res/raw/neira_cert), di-`sync` otomatis [`sync_android_anchor()`](../neira-gateway/certs/gen_certs.py)); leaf server diterbitkan ulang setiap [`run_local.bat`](../neira-gateway/run_local.bat) start dengan **SAN = semua IP LAN aktif + localhost** ([`issue_leaf()`](../neira-gateway/certs/gen_certs.py)). Ganti IP → restart gateway → leaf baru, **APK tidak perlu di-rebuild** (CA tetap).
   - **Android ([`network_security_config.xml`](../neira-android/app/src/main/res/xml/network_security_config.xml))**: trust anchor `@raw/neira_cert` dipindah ke `base-config` (berlaku untuk SEMUA alamat, bukan cuma `192.168.1.34`) → `wss://` valid berapa pun IP PC.
2. **[`shared/config.env`](shared/config.env)** kini punya `GATEWAY_URL=https://{LAN_IP}:8765` + `GATEWAY_TOKEN=lokal-uji-token` → Neira PC otomatis masuk **mode gateway** (bukan dashboard LAN lama) tanpa mengetahui IP di muka.

### 📊 2. Cara Uji
```
Mark-LIV-main\.venv\Scripts\python.exe neira-gateway\tests\test_gateway_ws.py    # 8/8 lulus
Mark-LIV-main\.venv\Scripts\python.exe Mark-LIV-main\scratch\test_gateway_link.py # PASS
# chain cert: leaf issuer = "Neira Local CA", SAN = localhost + IP LAN terdeteksi
neira-android\build_apk.bat   # BUILD SUCCESSFUL (raw/neira_cert = CA baru)
```

### ⏳ 3. Belum
- Uji fisik end-to-end HP↔PC lintas jaringan (ganti WiFi → hotspot) setelah install APK baru.

## 📅 Pembaruan: 29 September 2026 — Setelan Android (Edit IP Gateway + Kode Pair Ulang) & Tombol Buka Web Gateway di PC (Entri #20)

### 🌟 1. Ringkasan Perubahan Utama (What Changed)
1. **Android — tombol ⚙️ Setelan melayang ([`MainActivity.kt`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt))**: selalu tampil di atas WebView (bahkan saat halaman gagal dimuat), membuka dialog **Setelan Koneksi** berisi: edit alamat/IP gateway (disimpan di SharedPreferences [`KEY_URL`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt)), input **kode pairing 6 digit** untuk pair ulang (repair) setelah PC restart, dan tombol **Hapus Data Pair** (`localStorage.clear()`). Isi kode → muat `https://IP:8765/?code=XXXXXX` → halaman web otomatis [`pair_request`](../neira-gateway/gateway/server.py:259) via [`get_offer_by_code()`](../neira-gateway/gateway/devices.py:149). Default skema [`normalize()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) kini `https://` (gateway lokal jalan TLS self-signed — [`run_local.bat`](../neira-gateway/run_local.bat)).
2. **Web UI ([`web/index.html`](../neira-gateway/web/index.html)) — alamat gateway terpusat**: [`gatewayBase()`](../neira-gateway/web/index.html:555)/[`wsBase()`](../neira-gateway/web/index.html:564) dipakai [`connect()`](../neira-gateway/web/index.html:571) **dan** [`openAudioWS()`](../neira-gateway/web/index.html:842) — sebelumnya audio WS hardcode `location.host`, jadi mic tidak ikut pindah saat IP diedit dari panel ⚙️. Panel ⚙️ kini simpan `neira_gateway_url` (origin penuh).
3. **PC — tombol [`🌐 BUKA WEB GATEWAY`](ui.py)** di panel CONTROLS & SETTINGS ([`ui.py`](ui.py), di bawah REMOTE CONTROL): [`_open_web_gateway()`](ui.py) membuka halaman web gateway di browser default PC lewat [`_get_web_url()`](main.py) → [`GatewayLink.get_url()`](dashboard/gateway_link.py:97).

### 📊 2. Cara Uji
```
Mark-LIV-main\.venv\Scripts\python.exe neira-gateway\tests\test_gateway_ws.py   # 8/8 lulus
Mark-LIV-main\.venv\Scripts\python.exe -m py_compile Mark-LIV-main\ui.py Mark-LIV-main\main.py  # OK
neira-android\build_apk.bat                                                     # BUILD SUCCESSFUL
# Uji repair: matikan Neira PC → tap ⚙️ di HP (tetap tampil) → nyalakan PC →
# Remote Control → kode baru → isi di Setelan HP → Sambung → pair ulang tanpa QR.
```

### ⏳ 3. Belum
- Uji fisik end-to-end HP↔PC setelah install `app-debug.apk` baru (butuh device Android).

## 📅 Pembaruan: 26 September 2026 — Deploy "Neira Online": Gateway VPS + Mode GATEWAY_URL + Installer PC + App Android (Entri #19)

Rencana deploy (lihat [`UPDATE_LOG.md`](UPDATE_LOG.md) #19) diimplementasikan penuh. Arsitektur: **otak tetap di PC**, **VPS hanya relay tipis**, **HP = remote control** — semua klien koneksi outbound `wss://` (aman di balik NAT). Hasil uji regresi: **8/8 PASS** ([`neira-gateway/tests/test_gateway_ws.py`](../neira-gateway/tests/test_gateway_ws.py)) + **PASS** ([`scratch/test_gateway_link.py`](scratch/test_gateway_link.py)) + `py_compile` OK.

### 🌟 1. Ringkasan Perubahan Utama (What Changed)
1. **[`../neira-gateway/`](../neira-gateway/README.md) — repo gateway baru (LANGKAH 1)**: server FastAPI + WS hub di [`gateway/server.py`](../neira-gateway/gateway/server.py)/[`gateway/websocket.py`](../neira-gateway/gateway/websocket.py), registry device + pairing token di [`gateway/devices.py`](../neira-gateway/gateway/devices.py), protokol pesan [`gateway/protocol.py`](../neira-gateway/gateway/protocol.py) (adaptasi `brahma_connect`: `PAIR_REQUEST`/`PAIR_APPROVED`, `PING`/`PONG`, relay `COMMAND`/`LOG`/`STATUS`/`AUDIO`). File deploy: [`Dockerfile`](../neira-gateway/Dockerfile) + [`docker-compose.yml`](../neira-gateway/docker-compose.yml) + [`Caddyfile`](../neira-gateway/Caddyfile) (TLS) + [`.env.example`](../neira-gateway/.env.example).
2. **Mode `GATEWAY_URL` di PC (LANGKAH 2)**: klien gateway baru [`dashboard/gateway_link.py`](dashboard/gateway_link.py) (dipakai [`main.py`](main.py) via patch); [`shared/config.env`](shared/config.env) kunci `GATEWAY_URL` + `GATEWAY_TOKEN` — **kosong = mode LAN lama** (DashboardServer), terisi = mode gateway (butuh VPS / [`../neira-gateway/run_local.bat`](../neira-gateway/run_local.bat) untuk uji lokal).
3. **Build EXE + installer (LANGKAH 3)**: [`deploy/build_exe.bat`](deploy/build_exe.bat) (PyInstaller `--onedir --windowed`) + [`deploy/installer/neira.iss`](deploy/installer/neira.iss) (Inno Setup 6).
4. **Uji lokal end-to-end (tanpa VPS)**: [`../neira-gateway/run_local.bat`](../neira-gateway/run_local.bat) (uvicorn `0.0.0.0:8765`) + [`../neira-gateway/web/index.html`](../neira-gateway/web/index.html) (remote web: QR auto-pair, relay perintah, statis di-mount [`build_app()`](../neira-gateway/gateway/server.py)). Alamat HP di LAN: `http://<IP-PC>:8765` (contoh mesin ini `http://192.168.1.34:8765`).
5. **App Android fase 1 (LANGKAH 5)**: repo baru [`../neira-android/`](../neira-android/README.md) — pembungkus WebView Kotlin murni [`MainActivity.kt`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) (0 dependensi eksternal, `minSdk 26`, izin [`RECORD_AUDIO`](../neira-android/app/src/main/AndroidManifest.xml)/[`CAMERA`](../neira-android/app/src/main/AndroidManifest.xml) untuk mic/kamera HP, [`usesCleartextTraffic`](../neira-android/app/src/main/AndroidManifest.xml) untuk uji HTTP lokal, simpan alamat gateway di SharedPreferences + dialog pertama kali). Build: [`build_apk.bat`](../neira-android/build_apk.bat) (pakai cache Gradle 8.7) → **`app-debug.apk` SUDAH JADI** ([`app/build/outputs/apk/debug/app-debug.apk`](../neira-android/app/build/outputs/apk/debug/app-debug.apk), BUILD SUCCESSFUL 8m28s).

### 📊 2. Cara Uji
```
# regresi gateway (dari root workspace)
Mark-LIV-main\.venv\Scripts\python.exe neira-gateway\tests\test_gateway_ws.py   # 8/8
Mark-LIV-main\.venv\Scripts\python.exe Mark-LIV-main\scratch\test_gateway_link.py # PASS
# uji lokal LIVE
neira-gateway\run_local.bat                       # Terminal 1: gateway di :8765
# -> PC: start.bat -> Remote Control -> QR; HP: buka http://192.168.1.34:8765 / scan QR / install app-debug.apk
```

### ⏳ 3. Belum / Butuh Luar (sisa entri #19)
- **Build EXE nyata**: butuh `pip install pyinstaller` + Inno Setup 6 di mesin PC (belum terpasang) — jalankan [`deploy/build_exe.bat`](deploy/build_exe.bat) lalu kompilasi [`neira.iss`](deploy/installer/neira.iss).
- **Deploy VPS (LANGKAH 4)**: butuh akses VPS user — `git clone neira-gateway`, `cp .env.example .env`, `docker compose up -d`.
- **Uji HP live**: install [`app-debug.apk`](../neira-android/app/build/outputs/apk/debug/app-debug.apk) di HP, uji scan QR + kirim perintah.

---

## 📅 Pembaruan: 25 September 2026 (malam) — Reactor 3D Multi-Mode: Quantum / GLSL / Web3D + Animasi Boot & Shutdown

Reaktor HUD yang lama (2D datar) digantikan mesin reaktor multi-mode di [`core/reactor3d.py`](core/reactor3d.py) — pengguna tinggal memilih gaya lewat tombol `◉ REACTOR:` di quick drawer, tanpa bingung. Hasil uji: **13/13 PASS** ([`scratch/test_reactor3d.py`](scratch/test_reactor3d.py)) + regresi hijau (23/23, 70/70, 29/29, 33/33).

### 🌟 1. Ringkasan Perubahan Utama (What Changed)
1. **[`core/reactor3d.py`](core/reactor3d.py) — baru: mesin reaktor multi-mode** dengan state bersama [`ReactorContext`](core/reactor3d.py) (amp/speaking/viseme `v_open`/`v_wide`, progres `boot` & `shutdown`, warna tema) — pergantian gaya tidak mengubah logika [`ui.py`](ui.py):
   - **`classic`** — reaktor 2D lama [`_paint_core()`](ui.py) (tetap tersedia bagi yang suka tampilan lama).
   - **`quantum` (default)** — faux-3D di QPainter murni: 6 cincin elips bertumpuk (proyeksi orbit 3D, sisi depan terang/belakang redup), 260 partikel orbital dengan perspektif `f/(f+z)` + jejak cahaya, inti plasma volumetrik, dan **sonar ring** yang memuai tiap ledakan suara. Tanpa dependensi tambahan.
   - **`glsl`** — true-3D GPU: [`GlslReactorWidget`](core/reactor3d.py) (QOpenGLWidget + fragment shader raymarch: bola plasma fbm + 3 torus orbit + glow akumulatif). Butuh `PyQt6.QtOpenGLWidgets` (bawaan PyQt6).
   - **`web3d`** — three.js + [`UnrealBloomPass`](assets/web_background/UnrealBloomPass.js) via [`assets/web_background/reactor.html`](assets/web_background/reactor.html) dalam [`WebReactorWidget`](core/reactor3d.py) (QWebEngineView, state dikirim ~25 FPS ke `window.__reactorState()`). Butuh `pip install PyQt6-WebEngine`; bila tidak ada, tampil pesan fallback + otomatis jatuh ke `quantum`.
2. **Animasi penuh lifecycle**:
   - **Boot (saat start, ~2,5 dtk)**: spark → 6 bolt petir menuju inti → spin-up cincin dengan overshoot (`ease-out-back`) → shockwave putih memuai → idle. [`HudCanvas`](ui.py) memulai `boot 0→1` otomatis saat dibuat.
   - **Berbicara ("ngorol")**: [`v_open`](core/reactor3d.py) membuka cincin + membesar inti, [`v_wide`](core/reactor3d.py)/amp menggetarkan partikel & glow, sonar ring memancar tiap ledakan suara, spin cincin mempercepat saat `THINKING`/`SPEAKING`.
   - **Shutdown (saat ditutup, ~1,5 dtk)**: implosi partikel ke inti + fade — dipicu [`JarvisUI.begin_shutdown()`](ui.py) dari [`_do_shutdown()`](main.py) sebelum `os._exit(0)`.
3. **Config + picker**: [`REACTOR_STYLES`](memory/config_manager.py) + [`get_reactor_style()`](memory/config_manager.py)/[`save_reactor_style()`](memory/config_manager.py) (key `reactor_style`, default `quantum`). Tombol `◉ REACTOR: …` di quick drawer ([`_cycle_reactor_btn`](ui.py) → [`_cycle_reactor_style()`](ui.py)) berputar classic → quantum → glsl → web3d; gaya `n/a` ditandai dan log menjelaskan cara mengaktifkan.
4. **Wiring [`ui.py`](ui.py)**: [`HudCanvas`](ui.py) mendelegasi ke engine via [`set_reactor_style()`](ui.py)/[`_reactor_ctx()`](ui.py) — widget engine (glsl/web3d) ditempatkan di pita HUD (aman dengan kamera `QStackedWidget`), engine painter digambar di [`paintEvent`](ui.py). Fix kecil: `border-radius: 4px` tersisa di [`PluginManagerOverlay`](ui.py) → 6px (baseline restyle).

### 📊 2. Cara Uji
```
.venv\Scripts\python.exe scratch\test_reactor3d.py       # 13/13
.venv\Scripts\python.exe scratch\test_ui_restyle.py      # 23/23
.venv\Scripts\python.exe scratch\test_brahma_adoptions.py # 70/70
.venv\Scripts\python.exe scratch\test_skill_memory.py    # 29/29
.venv\Scripts\python.exe scratch\test_role_identity.py   # 33/33
```

---

## 📅 Pembaruan: 25 September 2026 (malam) — Adopsi Brahma-Echo: TaskQueue, Cooldown Otak, Boot Sentry & Learned Rules

Empat mekanisme responsivitas terbaik dari referensi eksternal [`Brahma-Echo`](../scratch/Brahma-Echo) (analisa lengkap: [`BRAHMA-ECHO-ANALISIS.md`](BRAHMA-ECHO-ANALISIS.md)) diadopsi ke Neira. Hasil uji: **70/70 PASS** ([`scratch/test_brahma_adoptions.py`](../scratch/test_brahma_adoptions.py)) + regresi hijau semua (62/62, 33/33, 29/29).

### 🌟 1. Ringkasan Perubahan Utama (What Changed)
1. **TaskQueue Async Berprioritas (`core/task_queue.py` — baru)**:
   - Antrean tugas background dengan kontrak `fn(cancel_flag: threading.Event) -> Any` — UI tidak pernah terblokir tugas berat.
   - Prioritas `HIGH=1 / NORMAL=2 / LOW=3`, eksekusi terurut `(prioritas, waktu_buat)`, worker thread daemon `max_concurrent=1`.
   - API: [`submit()`](core/task_queue.py) non-blocking → `task_id` 8-hex instan, [`cancel()`](core/task_queue.py), [`get_status()`](core/task_queue.py)/[`get_all_statuses()`](core/task_queue.py), callback `on_complete(task_id, result)` (dibatalkan → callback tidak dipanggil), singleton [`get_queue()`](core/task_queue.py).
2. **Cooldown Rate-Limit per Otak (`core/brain_hub.py`)**:
   - [`BrainHub`](core/brain_hub.py) kini mencatat otak yang gagal dengan [`mark_rate_limited()`](core/brain_hub.py) (cooldown [`RATE_LIMIT_COOLDOWN = 60.0`](core/brain_hub.py) detik) dan [`ask_best()`](core/brain_hub.py) melewati otak yang masih cooldown — rantai fallback langsung maju ke otak berikutnya tanpa menunggu 2× timeout.
   - `BrainNotReady` (belum dikonfigurasi) **tidak** di-cooldown; anti-lockout: bila seluruh rantai cooldown, semua tetap dicoba; `force=True` bypass; sukses → [`clear_rate_limited()`](core/brain_hub.py). [`status_report()`](core/brain_hub.py) menandai otak `(cooldown 60s)`. API lama `ask_best(prompt)` tetap kompatibel.
3. **Boot Sentry + Patch Sandbox — Anti-Brick (`core/boot_sentry.py` baru, `core/hermes_remediator.py`)**:
   - [`core/boot_sentry.py`](core/boot_sentry.py): `mark_crash()`/`clear_crash()` (log `FATAL_CRASH.log`), riwayat patch di `shared/memory/patch_history.json`, dan [`check_and_recover_on_boot()`](core/boot_sentry.py) yang otomatis jalan saat import — bila crash terdeteksi setelah patch < 1 jam, file dipulihkan dari backup `.bak` ("zero-brick").
   - [`hermes_remediator.py`](core/hermes_remediator.py) bertambah [`validate_code()`](core/hermes_remediator.py) (AST parse + compile di memori), [`apply_patch_safely()`](core/hermes_remediator.py) (tolak file immune [`IMMUNE_FILES`](core/hermes_remediator.py) → validasi → backup `.bak` → tulis atomik `os.replace` → catat riwayat), [`rollback_patch()`](core/hermes_remediator.py).
4. **Learned Rules → Prompt Injection (`core/learned_rules.py` baru)**:
   - Mesin aturan perilaku yang dipelajari dari koreksi user: `add_rule` (dedup case-insensitive), `list_rules`/`toggle_rule`/`delete_rule`, [`get_prompt_injections()`](core/learned_rules.py); state di `shared/memory/learned_rules.json`.
   - [`main.py`](main.py) menyuntik injeksi ini ke `parts` prompt Neira setelah `parts.append(sys_prompt)` — preferensi user selalu hadir di system prompt.
5. **Wiring [`main.py`](main.py)**: `main()` import [`core.boot_sentry`](core/boot_sentry.py) saat startup (auto-recovery aktif sejak awal), dan `runner()` memanggil [`mark_crash()`](core/boot_sentry.py) saat exception tak terduga sebelum re-raise.

### 🚫 2. Yang Sengaja TIDAK Diadopsi
- Monolith `main.py` 218 KB Brahma-Echo (Neira tetap modular).
- Dispatch tool if-elif ([`skill_hub.py`](core/skill_hub.py) registry kita sudah lebih baik).
- `generate_fix()` yang mengeksekusi kode hasil LLM tanpa sandbox penuh (terlalu berisiko untuk diadopsi sekarang).

### 📊 3. Cara Uji
```
.venv\Scripts\python.exe scratch\test_brahma_adoptions.py   # 70 assert — adopsi Brahma-Echo
.venv\Scripts\python.exe scratch\test_dola_chat.py          # regresi 5-otak (62 assert)
.venv\Scripts\python.exe scratch\test_role_identity.py      # identitas (33 assert)
.venv\Scripts\python.exe scratch\test_skill_memory.py       # skill hub (29 assert)
```

---

## 📅 Pembaruan: 25 September 2026 — Shared Skill Hub, Abigail Video, Jev Ultrafast, Storefront UI & Claude Code Tips

### 🌟 1. Ringkasan Perubahan Utama (What Changed)
1. **Universal Shared Skill Hub (`core/skill_hub.py` & `skills/`)**:
   - Seluruh skill dipindahkan dari folder datar (`actions/`) ke folder terstruktur berbasis kategori di `skills/`:
     - 📁 `skills/admin/`: Kendali OS, settings, windows, open app, browser control, manajemen skill.
     - 📁 `skills/konten/`: Pembuatan media, pencarian web, YouTube, cuaca, AI video.
     - 📁 `skills/dev/`: Coding, terminal, file controller, file processor, deep think.
     - 📁 `skills/asisten/`: Reminder, pesan (WA/Telegram), flight finder.
     - 📁 `skills/custom/`: Khusus menampung skill baru dari repo eksternal / buatan user.
2. **Hermes Skill Binding & Awareness (`router/hermes_connector.py` & `core/hermes_executor.py`)**:
   - **Masalah Lama:** Hermes hanya tahu 4 aksi (`open_cmd`, `create_script`, `open_app`, `open_code_tool`), tidak sadar bahwa dia punya skill bawaan seperti `web_search`, `youtube_video`, dll.
   - **Perubahan:**
     - Prompt Hermes kini otomatis disuntikkan live catalog dari `SkillHub`.
     - Ditambahkan aturan routing tegas (*Skill Awareness Protocol*): sebelum membuat script mentah atau membuka terminal, Hermes **wajib mengecek catalog** dan memanggil skill yang sudah ada.
     - Ditambahkan action baru `register_skill` agar Hermes bisa belajar mandiri dan menyimpan skill permanen ke `skills/custom/`.
3. **Neira Self-Awareness & Skill Management (`core/prompt.txt` & `skills/admin/manage_skills.py`)**:
   - **Masalah Lama:** Neira sering tidak tahu skill apa saja yang terpasang jika file skill ditambah secara manual saat aplikasi berjalan.
   - **Perubahan:**
     - Ditambahkan tool baru **`manage_skills`** (bisa dipanggil Neira & Hermes via `manage_skills(action='list')` atau `manage_skills(action='reload')`).
     - `core/prompt.txt` diperbarui dengan aturan kesadaran skill (*Skill Awareness & Execution Rules*).
4. **Adopsi Repositori Abigail (`github.com/iqbalmh18/abigail`)**:
   - Package `abigail` diinstal ke virtual environment (`.venv`).
   - Ditambahkan skill baru: **`skills/konten/video_generator.py`** (Text-to-Video AI via Cloud GPU HuggingFace LTX-Video).
   - Pengujian live: Sukses menghasilkan file MP4 nyata di `workspace/videos/ocean_sunset.mp4` (367 KB).
5. **Adopsi Repositori Jev Ultrafast (`github.com/browser-use/jev-ultrafast`)**:
   - Package `jev_ultrafast` + `browser-harness==0.1.13` + `httpx[http2]` diinstal ke `.venv` (vendor copy di `vendor/jev-ultrafast`).
   - Ditambahkan skill baru: **`skills/admin/browser_agent.py`** — agen browser otonom (satu goal + URL → klik/ketik/pilih sendiri sampai tujuan tercapai).
   - Model keputusan: TypeSafe (`TYPESAFE_API_KEY`) memilih operasi + elemen; model kecil OpenAI-compatible (`TEXT_MODEL_API_KEY`) hanya menulis teks kolom.
   - Kunci API baru ditambahkan ke `shared/config.env` dan dijaga oleh [`memory/config_manager.py`](memory/config_manager.py:83) saat sync.
   - Jika kunci belum diisi, skill mengembalikan pesan yang jelas (bukan crash).
6. **Adopsi Repositori Storefront UI (`github.com/vuestorefront/storefront-ui`)**:
  - Clone lokal di `scratch/storefront-ui` (library komponen e-commerce Vue/Nuxt & React/Next berbasis Tailwind).
  - Ditambahkan skill baru: **`skills/dev/storefront_ui.py`** — telusuri komponen (`list`/`search`), baca source siap-salin (`component`), dan ambil contoh block e-commerce (`block`, mis. ProductCard, Checkout) untuk framework `vue`/`react`/`all`.
7. **Setting Hermes/VansRouter Terpisah di UI (`ui.py` CustomizeOverlay)**:
   - Label dipisah: `NEIRA · GEMINI API KEY` (Google AI Studio, sesi suara) vs `HERMES · VANSROUTER BASE URL` + `HERMES · MODEL`.
   - Tombol **⟳ LIHAT MODEL** mengambil daftar model aktif via `GET {base}/v1/models` (dialog pilihan + pesan error jelas bila router mati).
   - Hasil simpan: `vansrouter_model` → `sync_all_configs()` → `VANSROUTER_MODEL` di `shared/config.env` (dibaca `hermes_connector`/`gemini_connector`/`deep_think`).
8. **Adopsi Repositori Claude Code Tips (`github.com/ykdojo/claude-code-tips`)**:
   - Clone lokal di `scratch/claude-code-tips` (README 45+ tips + skill SKILL.md yang tidak kompatibel langsung, jadi ditulis ulang ke Python).
   - Ditambahkan 2 skill baru di `skills/konten/`:
     - **`hn_summarize.py`** — daftar top story / cari / ringkas 1 thread Hacker News + komentar (Firebase + Algolia API). Teruji live (top 3 story nyata).
     - **`reddit_fetch.py`** — listing `hot`/`top`/`new`/`search` + 1 thread Reddit dengan komentar teratas. Bertingkat: requests UA browser → **fallback sesi Playwright `browser_control`** (buka reddit.com dulu, lalu `fetch()` `.json` dari dalam halaman — melewati blokir 403; teruji live, listing + thread sukses).
9. **Petik Tips Repo Claude Code Tips → `core/prompt.txt`**:
   - Ditambahkan section **[CLOSE THE LOOP]**: verifikasi output sebelum klaim sukses, baca seluruh error (bukan baris pertama), gagal 2× → ganti pendekatan, instruksi seringkas mungkin.
10. **Adopsi Konsep Removerized (`github.com/yossdotpro/removerized` → skill Python)**:
   - Repo asli = toolkit gambar browser (Next.js + ONNX Runtime Web) — kodenya tidak bisa dipakai langsung di Neira (TypeScript/canvas), tapi konsep & modelnya cocok.
   - Ditambahkan skill baru: **`skills/konten/image_remove_bg.py`** — engine **`rembg`** (pip, model ISNet/U2-Net, kualitas setara removerized) + upscale OpenCV.
   - Aksi: `remove` (1 gambar → PNG transparan / ganti latar warna), `batch` (folder), `upscale` (factor 2/3/4). Lokal 100% offline, tanpa API key.
   - Dependency baru `rembg[cpu]` ditambahkan ke [`requirements.txt`](requirements.txt:32). Test live: foto contoh dari repo → PNG transparan sukses (model auto-download sekali lalu cache).
11. **Adopsi Repositori BrowserSkill (`github.com/Tencent/BrowserSkill`)**:
   - Toolkit otomasi browser dari Tencent: CLI `bsk` (binary Rust v0.3.1, terpasang di `%USERPROFILE%\.local\bin\bsk.exe` via installer resmi) + daemon lokal + extension Chrome/Edge.
   - Ditambahkan skill baru: **`skills/admin/browser_skill.py`** — pembungkus perintah `bsk` (doctor/start/navigate/observe/click/fill/screenshot/console/network/debug).
   - Keunggulan di atas `browser_control`: pakai **sesi login Chrome asli**, **website debugging** (rekam request+response+console saat reproduksi bug), full-page screenshot, multi-profile.
   - **Pemasangan extension OTOMATIS** (`action=setup` / otomatis saat `start`): cek koneksi → extension belum ada? tulis policy HKCU `ExtensionInstallForcelist` → Chrome/Edge mengunduh & memasang sendiri dari Web Store saat browser dibuka; sudah terpasang/terhubung? skip. Local connection default aktif (lihat code extension) — tanpa klik manual.
   - Workflow skill: `setup → start → navigate → observe → interaksi → stop` (session_id disimpan sementara di file temp).
   - Test live E2E sukses: kompilasi OK, SkillHub **25 skill**, `start` → session `jbbz` → `navigate https://example.com` (load OK) → `get_text` (aria snapshot + ref `@e1`) → `stop` bersih. Chrome 153 + extension 0.3.1 terhubung ke daemon.
12. **Rombak UI Neira — Setelan Font + Tampilan Modern (`ui.py`)**:
   - **A. Setelan font baru** (selama ini warna tema sudah ada, font belum):
     - `CustomizeOverlay` dapat section **UI FONT**: dropdown family (Courier New, Cascadia, Consolas, JetBrains Mono, Fira Code, Segoe UI, Inter, dll), hex warna teks + swatch + tombol DEFAULT (kosong = ikut tema), slider **skala 85–130 %**.
     - Semua ~124 `QFont("Courier New", …)` lewat **shim QFont modular** — family mono diganti & ukuran diskalakan otomatis, termasuk teks yang digambar `QPainter` (HUD, metric, drop-zone) yang tak bisa dijangkau stylesheet.
     - Warna font = overlay di atas palet hasil accent ([`_overlay_font_color()`](Mark-LIV-main/ui.py)); live preview (`on_font_preview`) + rollback saat CANCEL; disimpan via `sync_all_configs()` sebagai `ui_font_family` / `ui_font_color` / `ui_font_scale`.
     - Diterapkan saat startup SEBELUM widget dibangun ([`MainWindow.__init__`](Mark-LIV-main/ui.py)) dan saat APPLY.
   - **B. Restyle QSS modern (tema warna tetap)**:
     - Radius seragam: `2/3/4px → 6px`, `5px → 8px` (76 titik) — hilang sudut kotak tajam.
     - Palet surface dinaikkan (`PANEL #0a121b`, `PANEL2 #0e1722`, `BORDER #17384d`, `DARK #080e16`) — hierarki depth lebih jelas tanpa mengubah hue.
     - `MetricBar` jadi **baris tipis** (tanpa kotak per metrik — panel kiri = satu kartu), status `AI CORE/SEC/PROTOCOL` jadi chip aksen border-kiri transparan, `info_panel` tanpa border.
     - `LogWidget` jadi **chat row**: satu blok per pesan — baris Anda rata kanan band cyan, jawaban Neira rata kiri band biru, `err`/`file` band merah/hijau, `sys` polos; radius 10px + `clear()` override.
     - Uji: `py_compile` OK + smoke test offscreen **23/23 PASS** ([`scratch/test_ui_restyle.py`](Mark-LIV-main/scratch/test_ui_restyle.py)).
13. **Memori Skill Bersama Neira + Hermes — Katalog Live & Routing Kategori (`core/skill_hub.py`, `core/action_loader.py`, `main.py`, `core/prompt.txt`, `router/hermes_connector.py`)**:
   - **Masalah Lama:** "2 otak g bisa saling ngerti" — Neira tidak tahu kategori skill (deskripsi dipotong 150 char tanpa label), katalog Hermes bisa kosong/stale (hanya terisi saat `manage_skills reload`), tidak ada aturan routing kategori ("butuh konten" → skill KONTEN), dan skill baru tak bisa dipanggil Neira tanpa restart.
   - **Perubahan:**
     - **Katalog live auto-refresh** ([`SkillHub.ensure_fresh()`](Mark-LIV-main/core/skill_hub.py)): detektor signature `(path, `mtime_ns`)` penuh — skill yang **ditambah, diubah, maupun DIHAPUS** langsung terlihat kedua otak pada panggilan berikutnya, tanpa restart & tanpa reload manual. (Detektor `mtime` maksimum lama melewatkan penghapusan file — bug nyata yang ditemukan saat uji.)
     - **Label kategori di semua deklarasi tool Neira**: [`ActionRecord.category`](Mark-LIV-main/core/action_loader.py) diisi dari folder `skills/<kategori>/`, prefix `[KONTEN]`/`[ADMIN]`/`[DEV]`/`[ASISTEN]` di deskripsi deklarasi (sama seperti [`SkillHub.get_tool_declarations()`](Mark-LIV-main/core/skill_hub.py)) — Neira kini bisa memilih skill berdasarkan kategori.
     - **Routing map bersama** ([`SkillHub.get_routing_guide()`](Mark-LIV-main/core/skill_hub.py)): peta `KATEGORI → daftar skill` yang sama disuntikkan ke prompt Neira (token `{skill_routing}` di [`prompt.txt`](Mark-LIV-main/core/prompt.txt)) dan prompt Hermes ([`hermes_connector.py`](Mark-LIV-main/router/hermes_connector.py)) — kedua otak membaca SATU peta, jadi selalu sepakat skill mana untuk pekerjaan apa.
     - **Aturan routing kategori eksplisit** di kedua prompt: cocokkan jenis pekerjaan → kategori (KONTEN = konten/riset, ADMIN = sistem/browser/app, DEV = kode/file, ASISTEN = pribadi) → pilih skill berdasarkan nama. Contoh: "butuh konten" → skill KONTEN.
     - **Fallback skill live di [`_execute_tool()`](Mark-LIV-main/main.py)**: skill yang didaftarkan SETELAH sesi dimulai (via `register_skill` Hermes atau file baru) tetap bisa dipanggil Neira — [`skill_hub.run()`](Mark-LIV-main/core/skill_hub.py) jadi cadangan terakhir sebelum "Unknown tool".
     - Bonus fix: [`import re`](Mark-LIV-main/router/hermes_connector.py) yang hilang (NameError di jalur eksekusi action Hermes) — ditemukan Pyrefly saat edit.
     - Uji: `py_compile` OK + smoke test **29/29 PASS** ([`scratch/test_skill_memory.py`](Mark-LIV-main/scratch/test_skill_memory.py)) — termasuk bukti skill baru langsung muncul di katalog+routing map kedua otak, dan skill yang dihapus langsung hilang.
14. **Rombak Role & Naming — SATU Identitas "Neira" (`core/prompt.txt`, `router/hermes_connector.py`, `skills/dev/deep_think.py`, `core/hermes_executor.py`, `core/hermes_remediator.py`, `skills/admin/manage_skills.py`, `skills/admin/open_app.py`, `ui.py`)**:
  - **Kesepakatan role (hasil diskusi):** hanya **"Neira"** yang terlihat ke user. "Hermes" kini hanya **nama internal inti otak** (deep core) — tidak boleh disebut ke user, tidak pernah diperkenalkan sebagai asisten kedua. Arsitektur tetap 2 lapis (suara/interaksi + inti otak berat), tapi persona menyatu: semua kerja inti otak dilaporkan sebagai kerja Neira sendiri, **orang pertama "saya"** ("sudah saya perbaiki…", bukan "Hermes menemukan…").
  - **Alur heavy task yang disepakati:** (1) konfirmasi singkat **tepat 1 kalimat** ("baik, saya kerjakan") lalu langsung panggil tool; (2) inti otak bekerja **senyap** — tanpa update berkala; (3) setelah hasil tiba, lapor hasil lengkap dengan **"saya"** (apa yang gagal, apa yang saya temukan, apa yang saya ubah, kondisi akhir).
  - **Perubahan prompt:** [`prompt.txt`](Mark-LIV-main/core/prompt.txt) [SELF] dirombak — framing "Mandor ↔ Hermes / You supervise Hermes" (2 entitas) dihapus, jadi ONE identity + dua lapis (Surface layer / Deep core layer) + IDENTITY RULE (larangan menyebut "Hermes"/nama engine ke user) + HEAVY TASK FLOW di atas; aturan skill "You and Hermes share…" → "surface & deep-core layers share…".
  - **Prompt inti otak:** [`hermes_connector.py`](Mark-LIV-main/router/hermes_connector.py) & [`deep_think.py`](Mark-LIV-main/skills/dev/deep_think.py) — "You are Hermes Agent… Your partner is Neira" → "You are the inner brain of Neira… never name yourself"; `report_for_mark` kini wajib **ORANG PERTAMA ("saya")** dilarang menyebut nama internal; deskripsi tool `deep_think` dibersihkan agar Neira melapor sebagai kerjanya sendiri.
  - **Bocoran "Hermes" ke user dibersihkan:** judul terminal & banner CMD/PowerShell (`[NEIRA TERMINAL]`, `Neira Terminal`, `neira_script_*`), label status eksekusi, teks hasil [`hermes_remediator.py`](Mark-LIV-main/core/hermes_remediator.py) ("Saya membuka…", "Analisis saya…"), output [`manage_skills.py`](Mark-LIV-main/skills/admin/manage_skills.py), hasil [`open_app.py`](Mark-LIV-main/skills/admin/open_app.py), label & log [`ui.py`](Mark-LIV-main/ui.py) ("INTI OTAK · VANSROUTER…", "Pilih Model Inti Otak"). (Nama internal kode — `HermesConnector`, blok ` ```hermes_action `, `hermes-agent/` — sengaja TIDAK diubah demi kompatibilitas parser.)
  - Uji: `py_compile` OK + smoke test identitas **33/33 PASS** ([`scratch/test_role_identity.py`](Mark-LIV-main/scratch/test_role_identity.py)) — prompt tanpa entitas "Hermes"/"Mandor"/"Tony", alur 1-kalimat→senyap→lapor "saya" terverifikasi, semua teks user-facing bebas "Hermes"; regresi memori skill tetap **29/29 PASS**.
15. **Dialog Pilih Model AI Profesional — [`ModelPickerDialog`](Mark-LIV-main/ui.py) (`ui.py`)**:
  - **Masalah:** popup pilih model pakai [`QInputDialog.getItem`](Mark-LIV-main/ui.py) — fixed-size, tidak bisa di-resize, tanpa pencarian, terasa amatir.
  - **Solusi:** class baru [`ModelPickerDialog(QDialog)`](Mark-LIV-main/ui.py) (di atas [`PluginManagerOverlay`](Mark-LIV-main/ui.py)) menggantikan popup bawaan di [`_fetch_models()`](Mark-LIV-main/ui.py): **resizable** (min 520×420), **pencarian real-time** (filter substring case-insensitive + status "Menampilkan X dari Y model"), **pilih cepat** double-click / Enter / tombol `PILIH`, tombol `BATAL`, model aktif ditandai **`● AKTIF`** (bold warna aksen, id asli disimpan di `Qt.ItemDataRole.UserRole` sehingga label tidak pernah ikut terpilih), subtitle jumlah model + base URL, tema gelap aplikasi (`C.*`), fokus otomatis ke kolom pencarian. Hasil dibaca lewat `dlg.selected`.
  - **Extend:** tambah kolom info / multi-pilih → edit [`ModelPickerDialog._apply_filter()`](Mark-LIV-main/ui.py) (isi baris) & [`_pick_selected()`](Mark-LIV-main/ui.py); ubah ukuran default → `resize()` di `__init__` class.
  - Uji: `py_compile` OK + smoke test dialog **21/21 PASS** ([`scratch/test_model_picker.py`](Mark-LIV-main/scratch/test_model_picker.py), offscreen) — filter, penanda AKTIF, pemilihan (Enter/double-click memakai id asli), dan bebas nama engine internal terverifikasi.

---

### ⚠️ 2. Komponen yang TIDAK DIPAKAI / DIHINDARI (Obsolete & Deprecated)

| Komponen / Fitur | Status | Alasan Tidak Dipakai / Solusi Pengganti |
|---|---|---|
| **Abigail Perchance Image Generation (`ImageClient`)** | ❌ **TIDAK DIPAKAI** | Menggunakan otomasi browser headless (`nodriver`) untuk bypass Cloudflare Turnstile. Di Windows sering timeout (>60 detik), gagal mendapatkan token, dan meninggalkan proses Chrome yang memakan CPU/RAM. |
| **Folder Flat `actions/` sebagai tempat skill baru** | ⚠️ **DEPRECATED (Hanya untuk Kompatibilitas)** | Jangan menaruh skill baru di `actions/`. Seluruh skill baru wajib dimasukkan ke subfolder `skills/<kategori>/`. Folder `actions/` hanya dipertahankan untuk live loop engine inti (`screen_processor`, `proactive`, `background_monitor`). |
| **Hermes Isolated Skills (`hermes-agent/data/skills/`)** | ❌ **USANG / DIALIHKAN** | Sebelumnya Hermes menyimpan skill di folder terisolasi yang tidak bisa diakses Neira. Sekarang dialihkan langsung ke `skills/custom/` agar Neira & Hermes berbagi satu skill yang sama (*Shared Hub*). |

---

### 📊 3. Status 25 Skill Aktif Saat Ini

```text
Daftar Skill Aktif Asisten (Shared Hub Neira & Hermes):
• [ADMIN] (8):
  - browser_agent      : 🌟 BARU (Jev Ultrafast) - Agen browser otonom (goal + URL → selesai).
  - browser_control    : Navigasi, klik web, tab browser.
  - browser_skill      : 🌟 BARU (Tencent BrowserSkill) - Otomasi browser login asli via CLI bsk + website debugging.
  - computer_control   : Klik, ketik, shortcut, screenshot mouse.
  - computer_settings  : Volume, brightness, wifi, restart, shutdown.
  - desktop_control    : Wallpaper, clean, organize desktop.
  - manage_skills      : Cek daftar skill aktif & reload memory katalog.
  - open_app           : Buka aplikasi sistem & software.

• [ASISTEN] (3):
  - flight_finder      : Cari tiket & rute penerbangan.
  - reminder           : Alarm & pengingat jadwal via Task Scheduler.
  - send_message       : Kirim pesan WhatsApp / Telegram / Notifikasi.

• [DEV] (7):
   - code_helper        : Tulis, edit, analisa, jalankan kode program.
   - deep_think         : Delegasi penalaran & eksekusi berat ke Hermes Core.
   - dev_agent          : Bangun proyek multi-file otomatis.
   - file_controller    : Manajemen file/folder workspace (create/copy/move/delete).
   - file_processor     : Ekstraksi & olah file (PDF, Word, Excel, Video, Audio).
   - game_updater       : Manajemen update game Steam / Epic Games.
   - storefront_ui      : 🌟 BARU (Storefront UI) - Jelajah komponen & block e-commerce Vue/React, source siap salin.

• [KONTEN] (7):
  - generate_video     : 🌟 BARU (Abigail) - Buat video AI singkat (Text-to-Video).
  - hn_summarize       : 🌟 BARU (Claude Code Tips) - Top story/cari/ringkas thread Hacker News + komentar.
  - image_remove_bg    : 🌟 BARU (Removerized) - Hapus latar gambar AI lokal (rembg) + upscale, offline.
  - reddit_fetch       : 🌟 BARU (Claude Code Tips) - Listing & thread Reddit (fallback otomatis via browser_control utk blokir 403).
  - weather_report     : Prakiraan cuaca terkini.
  - web_search         : Pencarian web, riset, berita terkini.
  - youtube_video      : Cari, putar, rangkum transkrip video YouTube.
```

---

### 🛠️ 4. Panduan Menambah Skill Baru Manual (Agar Neira & Hermes Langsung Tahu)

Jika kamu ingin menambahkan skill baru di kemudian hari:
1. Buat satu file Python di salah satu folder:
   - `skills/admin/<nama_skill>.py`
   - `skills/konten/<nama_skill>.py`
   - `skills/dev/<nama_skill>.py`
   - `skills/asisten/<nama_skill>.py`
   - `skills/custom/<nama_skill>.py`
2. Pastikan file memiliki struktur standar:
   ```python
   def handler_fungsi(argumen_1: str) -> str:
       # Logika skill kamu di sini
       return "Hasil eksekusi"

   TOOL = {
       "name": "nama_skill",
       "description": "Deskripsi jelas fungsi skill ini (Gemini & Hermes membaca ini)",
       "parameters": {
           "type": "OBJECT",
           "properties": {
               "argumen_1": {"type": "STRING", "description": "Penjelasan argumen"}
           },
           "required": ["argumen_1"]
       },
       "handler": handler_fungsi
   }
   ```
3. Begitu file disimpan:
   - **Hermes** otomatis tahu di tugas berikutnya karena `skill_hub.get_hermes_catalog()` membaca file live dari disk.
   - **Neira** bisa langsung me-refresh memorinya dengan perintah suara: *"Neira, muat ulang skill"* (memanggil `manage_skills(action="reload")`).

### 🌟 5. Skill Baru dari Repo Eksternal (Resep Cepat)
Contoh adopsi repo luar menjadi satu skill (dipakai untuk Abigail & Jev Ultrafast):
1. `git clone <repo> scratch/<nama>` lalu copy ke `vendor/<nama>` (agar tidak ikut ke-git-ignore scratch).
2. Install ke venv: `.venv\Scripts\python.exe -m pip install vendor/<nama>`.
3. Catat env/kunci yang dibutuhkan → tambahkan ke `shared/config.env` **dan** ke blok `new_env_content` di [`memory/config_manager.py`](memory/config_manager.py:72) agar tidak hilang saat Apply/Settings disimpan.
4. Tulis `skills/<kategori>/<nama>.py` dengan handler + `TOOL` dict (import library di dalam fungsi, bukan di level modul, supaya skill tetap valid walau paket belum terpasang).
5. Uji: `.venv\Scripts\python.exe -c "from core.skill_hub import skill_hub; print(skill_hub.has('<nama>'))"`.
6. Perbarui `CHANGELOG.md` dan (opsional) [`requirements.txt`](requirements.txt:84).
