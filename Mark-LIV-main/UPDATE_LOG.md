# 🗒️ UPDATE LOG — Catatan Perubahan untuk Update Berikutnya

> **Aturan wajib:** setiap kali ada update/perubahan kode, WAJIB menambah entri baru di bagian
> [Riwayat Entri](#riwayat-entr) di bawah (terbaru di atas). Entri harus cukup konteks agar update
> berikutnya bisa langsung melanjutkan tanpa membaca ulang seluruh kode: file yang diubah, alasan,
> cara mengubah/extend, dan cara menguji.
>
> Detail arsitektur panjang tetap di [`CHANGELOG.md`](CHANGELOG.md). File ini ringkas + actionable.

---

## 📜 Riwayat Entri

### #23 — APK "Halaman Tidak Tersedia": Paksa https:// untuk Host Privat (Gateway TLS-only) (29 September 2026, malam)
- **Masalah (laporan user):** *"di apk halaman tidak tersedia meskipun udah manggil ip gateway:8000, kalau lewat browser di pc udah aktif bisa"* — halaman WebView APK gagal (`ERR_CONNECTION_REFUSED` → pesan "halaman tidak tersedia") padahal alamat sama (`IP-PC:8000`) **normal** di browser PC.
- **Akar masalah (terbukti, bukan dugaan):** gateway lokal ([`run_local.bat`](../neira-gateway/run_local.bat) → uvicorn dengan `--ssl-keyfile/--ssl-certfile`) **HANYA melayani TLS**. Prefs APK ([`shared_prefs/neira.xml`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt), key [`gateway_url`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt)) masih menyimpan `http://192.168.1.28:8000`. Bukti: `curl -sk https://192.168.1.28:8000/health` → **200** vs `curl http://192.168.1.28:8000/health` → **`tls_http_code=000`** (koneksi datar ditolak). Browser PC "tetap bisa" karena browser otomatis mencoba/meng-upgrade ke https, sedangkan WebView tidak.
- **Temuan pendukung (membuang teori firewall):** `toybox nc -w 2 <IP> 8000 </dev/null` dari emulator → **`exit_0`** (TCP port 8000 **terjangkau** dari HP), jadi **bukan** Windows Firewall. `netsh advfirewall add rule ...` memang butuh elevation ("requires elevation (Run as administrator)") tetapi **tidak diperlukan** untuk kasus ini.
- **File diubah:** [`../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt)
  - [`onCreate()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt:63) — migrasi build lama kini **memaksa skema `https://`** (bukan hanya `:8765`→`:8000`) untuk host privat / port 8000 / 8765; tulis balik ke SharedPreferences ([`KEY_URL`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt)).
  - [`normalize()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt:418) — input user `http://<host-privat>:8000` otomatis di-upgrade ke `https://` (host publik/VPS tidak disentuh). Default tanpa skema tetap `https://`.
  - [`setupWebView()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt:138) — tambah [`MIXED_CONTENT_COMPATIBILITY_MODE`](https://developer.android.com/reference/android/webkit/WebSettings#MIXED_CONTENT_COMPATIBILITY_MODE) agar konten campuran tidak diblokir keras.
- **Cara uji (regresi):**
  ```
  neira-android\build_apk.bat
  D:\LDPlayer\LDPlayer9\adb.exe install -r neira-android\app\build\outputs\apk\debug\app-debug.apk
  D:\LDPlayer\LDPlayer9\adb.exe shell run-as com.neira.remote cat shared_prefs/neira.xml
  #   → <string name="gateway_url">https://192.168.1.28:8000</string>   (auto-migrasi berhasil)
  curl -sk https://localhost:8000/health
  #   → {"status":"ok","gateway":"Neira Gateway","pc_online":true,"clients":1}   (WebSocket APK tersambung)
  ```
- **Catatan:** [`apply_diff`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) gagal berulang di `MainActivity.kt` (CRLF vs LF → butuh 100% match; laporan 96%/85% similarity) — workaround: [`write_to_file`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) rewrite penuh. `adb install -r` pertama gagal `INSTALL_PARSE_FAILED_NOT_APK` karena APK masih setengah tertulis → beri jeda (`ping -n 30`) lalu ulangi = **Success**.
- **Jebakan diagnosa (pelajaran):** emulator LDPlayer jalan **bridged** (wlan0 `192.168.1.18`, PC `192.168.1.28`, subnet `/24` sama). `ping` dari emulator ke PC **100% loss** walau port TCP terbuka (ICMP diblokir) → **jangan** pakai `ping` untuk uji reachability; pakai `toybox nc -w 2 <IP> <port> </dev/null; echo exit_$?` (exit_0 = terbuka). Emulator tanpa `su`/`curl`/`nc -z`.
- **Jawab user:** halaman sekarang terbuka di APK karena URL dipaksa `https://` (gateway TLS-only). Kalau ganti IP lagi, cukup tap **⚙️** → isi `https://IP-BARU:8000` → **Sambung** (skema juga otomatis jadi https).

### #22 — Port Web Gateway 8000 (bukan 8765) + Kode Pair Angka di Mode LAN + Config Tak Terhapus + APK Self-Heal (29 September 2026, malam)
- **Masalah (laporan user):** (1) "port web gateway pakai **8000** bukan 8765" — seluruh rantai masih 8765; (2) `GATEWAY_URL`/`GATEWAY_TOKEN` **hilang** dari [`shared/config.env`](shared/config.env) setelah Apply/Save → Neira diam-diam balik ke mode LAN [`DashboardServer`](dashboard/server.py) (port 8000) sehingga gateway asli tak terpakai; (3) "g bisa nulis id pairing karena id pairing ada huruf" — kode mode LAN berisi huruf tapi keyboard APK numeric-only; (4) "api gateway masih g bisa konek di APK" — APK lama simpan URL `:8765` + whitelist SSL `:8765` saja.
- **File diubah:**
  - [`../neira-gateway/run_local.bat`](../neira-gateway/run_local.bat) — uvicorn `--port 8000`; **guard anti double-instance** (cek `netstat :8000` dulu → sudah jalan = `exit /b 0`).
  - [`../neira-gateway/gateway/server.py`](../neira-gateway/gateway/server.py) — default [`port`](../neira-gateway/gateway/server.py) 8000 + env `GATEWAY_PORT` default `"8000"`.
  - [`dashboard/gateway_link.py`](dashboard/gateway_link.py) — [`load_gateway_config()`](dashboard/gateway_link.py:62): fallback `auto`/`{LAN_IP}` → `:8000`; paksa https untuk `:8000`.
  - [`start.bat`](start.bat) — auto-start gateway kini cek `netstat :8000`.
  - [`main.py`](main.py) — blok autostart (2467+) cek socket `127.0.0.1:8000` dulu sebelum launch [`run_local.bat`](../neira-gateway/run_local.bat) (anti double instance, jawaban: **tidak perlu klik run_local.bat manual**).
  - [`memory/config_manager.py`](memory/config_manager.py) — [`sync_all_configs()`](memory/config_manager.py) **tidak lagi menghapus** `GATEWAY_URL`/`GATEWAY_TOKEN`/`AUTOSTART_LOCAL_GATEWAY` saat rewrite [`shared/config.env`](shared/config.env) (akar bug config hilang).
  - [`shared/config.env`](shared/config.env) — kembalikan `GATEWAY_URL=https://{LAN_IP}:8000` + `GATEWAY_TOKEN=lokal-uji-token` + `AUTOSTART_LOCAL_GATEWAY=true`.
  - [`dashboard/server.py`](dashboard/server.py) — [`_KEY_CHARS`](dashboard/server.py:69) → `string.digits`: kode pairing mode LAN kini **6 digit** (konsisten dengan [`create_offer()`](../neira-gateway/gateway/devices.py:132) gateway).
  - [`../neira-android/.../MainActivity.kt`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) — hint `https://IP-PC:8000`; whitelist SSL `:8000` **atau** `:8765` (APK lama tidak mati); [`isPrivateHost()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) + **migrasi halus** URL tersimpan `:8765`→`:8000` (hanya host privat/localhost, domain VPS tak disentuh).
  - [`../neira-gateway/web/index.html`](../neira-gateway/web/index.html) — placeholder `:8000`.
- **Cara uji:** `Mark-LIV-main\.venv\Scripts\python.exe neira-gateway\tests\test_gateway_ws.py` (8/8) + `Mark-LIV-main\.venv\Scripts\python.exe Mark-LIV-main\scratch\test_gateway_link.py` (PASS) + `py_compile` OK + `curl -sk https://localhost:8000/health` → `{"status":"ok",...,"pc_online":true}` + [`build_apk.bat`](../neira-android/build_apk.bat) BUILD SUCCESSFUL + `adb install -r`.
- **Jawab user "APA HARUS klik run_local.bat?":** **TIDAK** — [`start.bat`](start.bat) dan [`main.py`](main.py) auto-start gateway (idempoten, cek port 8000 dulu). Cukup jalankan [`start.bat`](start.bat).
- **Catatan:** Pyrefly "Cannot find module fastapi/uvicorn/cryptography" = linter pakai Python sistem bukan venv — abaikan (jebakan lama).

### #21 — Koneksi Tahan Ganti IP (dinamis, tanpa IP hardcode) + Kode Pair Angka Saja (29 September 2026, malam)
- **Masalah:** (1) IP PC sering berubah (WiFi tetangga / hotspot HP / tether) — alamat gateway di web "beda sendiri" karena override `localStorage`, cert TLS per-IP (`192.168.1.34`) gagal tiap IP pindah, dan `GATEWAY_URL` sempat mau di-hardcode (DITOLAK — harus dinamis); (2) input kode pairing di APK keyboard numeric, tapi web masih terima huruf; (3) `shared/config.env` belum punya `GATEWAY_URL`/`GATEWAY_TOKEN` → Neira jalan mode LAN lama (bukan gateway).
- **Prinsip: TIDAK ADA IP hardcode di mana pun.** Semua dideteksi runtime.
- **File diubah:**
  - [`../neira-gateway/web/index.html`](../neira-gateway/web/index.html) — [`gatewayBase()`](../neira-gateway/web/index.html:555) kini SELALU [`location.origin`](../neira-gateway/web/index.html:555) (hapus override `neira_gateway_url`/`neira_gateway_host` = penyebab "IP beda"); tombol simpan panel ⚙️ = **navigasi** [`location.href`](../neira-gateway/web/index.html) ke alamat baru (bukan override); filter **angka saja** maks 6 digit untuk input `#code`/`#sp-code` (`.replace(/\D+/g,"").slice(0,6)`).
  - [`dashboard/gateway_link.py`](dashboard/gateway_link.py) — [`detect_lan_ip()`](dashboard/gateway_link.py:36) baru (trik UDP-connect + fallback `getaddrinfo`, tanpa hardcode); [`load_gateway_config()`](dashboard/gateway_link.py) resolve placeholder `{LAN_IP}` di `GATEWAY_URL` (atau nilai `auto`) jadi IP LAN aktif saat start; [`serve()`](dashboard/gateway_link.py) **self-heal**: tiap reconnect resolve ulang config → ganti jaringan (WiFi/hotspot/tether) otomatis ikut, tanpa restart app.
  - [`shared/config.env`](shared/config.env) — tambah `GATEWAY_URL=https://{LAN_IP}:8765` + `GATEWAY_TOKEN=lokal-uji-token` (placeholder dinamis, bukan angka IP).
  - [`../neira-gateway/certs/gen_certs.py`](../neira-gateway/certs/gen_certs.py) — **BARU**: generate TLS dinamis tahan ganti IP. [`ensure_ca()`](../neira-gateway/certs/gen_certs.py) buat/muat **CA lokal** (`ca.pem`, 10 tahun — trust anchor di APK, sekali embed); [`issue_leaf()`](../neira-gateway/certs/gen_certs.py) terbitkan leaf server baru SETIAP start dengan **SAN = semua IP LAN aktif + localhost** (deteksi runtime); [`sync_android_anchor()`](../neira-gateway/certs/gen_certs.py) tulis ulang [`raw/neira_cert`](../neira-android/app/src/main/res/raw/neira_cert) (DER dari CA) otomatis. Dependency: `cryptography` (sudah terpasang di venv).
  - [`../neira-gateway/run_local.bat`](../neira-gateway/run_local.bat) — panggil [`gen_certs.py`](../neira-gateway/certs/gen_certs.py) sebelum uvicorn start (cert selalu fresh sesuai IP saat itu).
  - [`../neira-android/app/src/main/res/xml/network_security_config.xml`](../neira-android/app/src/main/res/xml/network_security_config.xml) — trust anchor `@raw/neira_cert` (CA) dipindah ke [`base-config`](../neira-android/app/src/main/res/xml/network_security_config.xml) untuk **SEMUA alamat** (bukan domain `192.168.1.34` saja) → wss:// valid berapa pun IP PC.
  - [`../neira-android/.../MainActivity.kt`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) — hint input tidak lagi menyebut IP tetap (`https://IP-PC:8765`).
- **Alur ganti jaringan:** pindah WiFi/hotspot → biarkan saja. [`gen_certs.py`](../neira-gateway/certs/gen_certs.py) (saat [`run_local.bat`](../neira-gateway/run_local.bat) start) terbitkan leaf SAN baru; [`GatewayLink.serve()`](dashboard/gateway_link.py) resolve ulang `{LAN_IP}` tiap reconnect; HP cukup tap ⚙️ → isi alamat baru (ditampilkan tombol REMOTE CONTROL / BUKA WEB GATEWAY) → Sambung. Tidak perlu rebuild APK (CA tetap).
- **Cara uji:** `Mark-LIV-main\.venv\Scripts\python.exe neira-gateway\tests\test_gateway_ws.py` (8/8 lulus) + `Mark-LIV-main\.venv\Scripts\python.exe Mark-LIV-main\scratch\test_gateway_link.py` (PASS) + `py_compile` OK + verifikasi chain: leaf issuer = `Neira Local CA`, SAN berisi IP LAN terdeteksi. Build APK ulang ([`build_apk.bat`](../neira-android/build_apk.bat)) karena [`network_security_config.xml`](../neira-android/app/src/main/res/xml/network_security_config.xml) + [`raw/neira_cert`](../neira-android/app/src/main/res/raw/neira_cert) berubah.
- **Catatan:** Pyrefly false-positive [`ui.py`](ui.py) `img.save(buf, format="PNG")` (qrcode) — sudah tercatat di Jebakan, abaikan.

### #20 — Setelan Android (edit IP gateway + kode pair ulang) & Tombol Buka Web Gateway di PC (29 September 2026)
- **Masalah:** setelah Neira PC restart, Android minta kode pair lagi — tapi **tidak ada menu setelan** untuk isi IP gateway / kode ulang (menu opsi tidak tampil karena theme [`Theme.Material.NoActionBar`](../neira-android/app/src/main/res/values/themes.xml:3)), dan saat halaman gagal dimuat tombol ⚙️ web ikut hilang. Di PC juga belum ada tombol buka web gateway.
- **File diubah:**
  - [`../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) — tombol **⚙️ melayang native** (selalu tampil di atas WebView, bahkan saat halaman error) → [`showSettingsDialog()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt): edit alamat/IP gateway (simpan [`KEY_URL`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) SharedPreferences) + input **kode pairing 6 digit** (repair) + tombol **Hapus Data Pair** (`localStorage.clear()`). Isi kode → muat `https://IP:8765/?code=XXXXXX` → halaman web langsung [`pair_request`](../neira-gateway/gateway/server.py:259) (via [`get_offer_by_code()`](../neira-gateway/gateway/devices.py:149)). [`normalize()`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt) default `https://` (gateway lokal pakai TLS self-signed).
  - [`../neira-gateway/web/index.html`](../neira-gateway/web/index.html) — [`gatewayBase()`](../neira-gateway/web/index.html:555)/[`wsBase()`](../neira-gateway/web/index.html:564) terpusat: panel ⚙️ simpan `neira_gateway_url` (bukan cuma host), dan [`openAudioWS()`](../neira-gateway/web/index.html:842) ikut pindah host saat IP diedit (sebelumnya hardcode `location.host`).
  - [`ui.py`](ui.py) — tombol [`🌐 BUKA WEB GATEWAY`](ui.py) di panel CONTROLS (di bawah REMOTE CONTROL) → [`_open_web_gateway()`](ui.py) buka alamat gateway di browser default PC; properti [`on_web_url`](ui.py).
  - [`main.py`](main.py) — [`_get_web_url()`](main.py) (balikan [`self._dashboard.get_url()`](dashboard/gateway_link.py:97)) di-wire ke [`ui.on_web_url`](ui.py).
- **Alur repair PC restart:** PC nyala → Neira → tombol **REMOTE CONTROL** → kode 6 digit baru → di HP tap **⚙️** → isi IP (bila berubah) + kode → **Sambung** → langsung pair ulang tanpa scan QR.
- **Cara uji:** `Mark-LIV-main\.venv\Scripts\python.exe neira-gateway\tests\test_gateway_ws.py` (8/8 lulus) + `py_compile ui.py main.py` (OK) + [`build_apk.bat`](../neira-android/build_apk.bat) → install `app-debug.apk` → matikan Neira PC → tap ⚙️ di HP (tetap tampil) → nyalakan PC → isi kode baru → tersambung.
- **Catatan:** menu opsi Android tetap ada sebagai fallback (beberapa device menampilkan overflow menu), tapi jalur utama tombol ⚙️ melayang.

### #19 — Deploy "Neira Online": Gateway VPS + Mode GATEWAY_URL + Installer PC + App Android (25–26 September 2026) — **SELESAI (5 dari 6 sub-langkah)**
- **Apa:** implementasi rencana deploy penuh sesuai peta lokasi [`../README.md`](../README.md): **otak tetap di PC** (EXE via [`deploy/build_exe.bat`](deploy/build_exe.bat)), **VPS hanya relay tipis** (repo [`../neira-gateway/`](../neira-gateway/README.md) — FastAPI + WS hub + pairing token + TLS Caddy), **app Android** [`../neira-android/`](../neira-android/README.md) sebagai remote (fase 1 WebView wrapper). Koneksi semua klien **outbound `wss://`** (aman di balik NAT). Protokol adaptasi `brahma_connect`: `PAIR_REQUEST`/`PAIR_APPROVED`, `PING`/`PONG`, relay `COMMAND`/`LOG`/`STATUS`/`AUDIO`.
- **File BARU:** [`../neira-gateway/`](../neira-gateway/README.md) (seluruh repo: [`gateway/server.py`](../neira-gateway/gateway/server.py), [`gateway/websocket.py`](../neira-gateway/gateway/websocket.py), [`gateway/devices.py`](../neira-gateway/gateway/devices.py), [`gateway/protocol.py`](../neira-gateway/gateway/protocol.py), [`Dockerfile`](../neira-gateway/Dockerfile), [`docker-compose.yml`](../neira-gateway/docker-compose.yml), [`Caddyfile`](../neira-gateway/Caddyfile), [`.env.example`](../neira-gateway/.env.example), [`run_local.bat`](../neira-gateway/run_local.bat), [`web/index.html`](../neira-gateway/web/index.html), [`tests/test_gateway_ws.py`](../neira-gateway/tests/test_gateway_ws.py)); [`dashboard/gateway_link.py`](dashboard/gateway_link.py); [`deploy/build_exe.bat`](deploy/build_exe.bat) + [`deploy/installer/neira.iss`](deploy/installer/neira.iss); seluruh repo [`../neira-android/`](../neira-android/README.md) (15 file: [`MainActivity.kt`](../neira-android/app/src/main/java/com/neira/remote/MainActivity.kt), [`build_apk.bat`](../neira-android/build_apk.bat), dst).
- **File diubah:** [`main.py`](main.py) (patch mode GATEWAY_URL via [`gateway_link.py`](dashboard/gateway_link.py)), [`shared/config.env`](shared/config.env) (kunci `GATEWAY_URL`/`GATEWAY_TOKEN` — kosong = mode LAN lama), [`../README.md`](../README.md) (peta lokasi per mesin).
- **Status:** ✅ gateway (uji 8/8) ✅ mode GATEWAY_URL ([`test_gateway_link.py`](scratch/test_gateway_link.py) PASS) ✅ skrip EXE+installer ✅ uji lokal end-to-end (gateway `:8765` live, halaman web tersaji) ✅ **APK jadi** ([`app-debug.apk`](../neira-android/app/build/outputs/apk/debug/app-debug.apk) BUILD SUCCESSFUL) ✅ dokumentasi CHANGELOG + regresi. ⏳ **Belum:** build EXE nyata (butuh `pip install pyinstaller` + Inno Setup 6) dan **LANGKAH 4 deploy VPS** (butuh akses VPS user: `git clone neira-gateway` → `cp .env.example .env` → `docker compose up -d`).
- **Cara uji:** `Mark-LIV-main\.venv\Scripts\python.exe neira-gateway\tests\test_gateway_ws.py` (8/8) + `Mark-LIV-main\.venv\Scripts\python.exe Mark-LIV-main\scratch\test_gateway_link.py` (PASS) + `neira-gateway\run_local.bat` → PC `start.bat` → Remote Control QR → HP buka `http://192.168.1.34:8765` / install `app-debug.apk`.
- **Catatan tertunda lain:** karya 5-otak (Dola dkk) belum tercatat di CHANGELOG — lanjutkan pencatatan saat resume (lihat juga [`../README.md`](../README.md)).

### #18 — Reactor 3D Multi-Mode (25 September 2026, malam)
- **Apa:** reaktor HUD lama (2D datar) → mesin multi-mode [`core/reactor3d.py`](core/reactor3d.py) dengan 4 gaya: `classic` (2D lama), `quantum` (faux-3D QPainter — default), `glsl` (raymarch GPU), `web3d` (three.js + bloom). Semua berbagi [`ReactorContext`](core/reactor3d.py) (amp, viseme `v_open`/`v_wide`, `boot`, `shutdown`, warna tema). Animasi: boot ~2,5 dtk (spark → bolt → spin-up overshoot → shockwave), bicara (sonar ring + cincin membuka + partikel bergetar), shutdown ~1,5 dtk (implosi → padam).
- **File baru:** [`core/reactor3d.py`](core/reactor3d.py), [`assets/web_background/reactor.html`](assets/web_background/reactor.html) (+ 7 file three.js di [`assets/web_background/`](assets/web_background)), [`scratch/test_reactor3d.py`](scratch/test_reactor3d.py).
- **File diubah:** [`memory/config_manager.py`](memory/config_manager.py) ([`REACTOR_STYLES`](memory/config_manager.py), [`get_reactor_style()`](memory/config_manager.py)/[`save_reactor_style()`](memory/config_manager.py), key `reactor_style`); [`ui.py`](ui.py) ([`HudCanvas`](ui.py) delegate engine + [`set_reactor_style()`](ui.py)/[`begin_shutdown()`](ui.py)/[`_reactor_ctx()`](ui.py), tombol picker [`_cycle_reactor_style()`](ui.py) di quick drawer, fix `border-radius: 4px`→6px); [`main.py`](main.py) ([`_do_shutdown()`](main.py) memicu [`ui.begin_shutdown()`](main.py)).
- **Cara extend:** gaya baru → tambah di [`REACTOR_STYLES`](core/reactor3d.py) + [`STYLE_LABELS`](core/reactor3d.py), buat engine (painter: `step(dt, ctx)` + `paint(p, rect, ctx)`; widget: `set_state(dict)` + `set_name(str)`), daftarkan di [`make_reactor_widget()`](core/reactor3d.py). Semua state masuk lewat [`ReactorContext`](core/reactor3d.py) — jangan ubah [`ui.py`](ui.py).
- **Cara uji:** `.venv\Scripts\python.exe scratch\test_reactor3d.py` (13 checks) + regresi [`test_ui_restyle.py`](scratch/test_ui_restyle.py) 23/23, [`test_brahma_adoptions.py`](scratch/test_brahma_adoptions.py) 70/70, [`test_skill_memory.py`](scratch/test_skill_memory.py) 29/29, [`test_role_identity.py`](scratch/test_role_identity.py) 33/33.
- **Catatan dependensi:** `glsl` butuh `PyQt6.QtOpenGLWidgets` (bawaan PyQt6); `web3d` butuh `pip install PyQt6-WebEngine` (opsional — fallback ke `quantum` dengan pesan jelas). Bila gaya tak tersedia, [`style_available()`](core/reactor3d.py) memberi pesan cara mengaktifkan.

### #17 — Adopsi 4 Mekanisme Terbaik Brahma-Echo ke Neira (25 September 2026, malam)
TaskQueue [`core/task_queue.py`](core/task_queue.py), cooldown otak [`core/brain_hub.py`](core/brain_hub.py), boot sentry + patch sandbox [`core/boot_sentry.py`](core/boot_sentry.py)/[`core/hermes_remediator.py`](core/hermes_remediator.py), learned rules [`core/learned_rules.py`](core/learned_rules.py). Uji [`scratch/test_brahma_adoptions.py`](scratch/test_brahma_adoptions.py) 70/70. Detail di [`CHANGELOG.md`](CHANGELOG.md).

---

## 🧭 Peta Kode Penting (baca ini dulu sebelum update)

| Mau mengubah… | File utama | Catatan |
|---|---|---|
| Persona / aturan bicara Neira | [`core/prompt.txt`](core/prompt.txt) | Token `{braces}` diisi [`_render_prompt()`](main.py) saat startup |
| Otak inti (deep reasoning) | [`router/hermes_connector.py`](router/hermes_connector.py), [`skills/dev/deep_think.py`](skills/dev/deep_think.py) | Prompt inti otak ada di [`process_heavy_task()`](router/hermes_connector.py) & [`deep_think()`](skills/dev/deep_think.py) |
| Eksekusi fisik (buka app/terminal/script) | [`core/hermes_executor.py`](core/hermes_executor.py) | Judul terminal & banner = `Neira Terminal` / `[NEIRA TERMINAL]` |
| Self-healing / belajar dari kegagalan | [`core/hermes_remediator.py`](core/hermes_remediator.py) | Teks hasil wajib orang pertama "saya" |
| Skill (tambah/ubah/kategori) | [`skills/<kategori>/`](skills), [`core/skill_hub.py`](core/skill_hub.py), [`core/action_loader.py`](core/action_loader.py) | Katalog live auto-refresh — tak perlu restart |
| Routing kategori skill | [`SkillHub.get_routing_guide()`](core/skill_hub.py) | Dipakai DUA prompt (Neira + inti otak) via token `{skill_routing}` |
| UI (tema, font, label) | [`ui.py`](ui.py) | Setelan font: `ui_font_family` / `ui_font_color` / `ui_font_scale` |
| Nama asisten / user / API | [`ui.py`](ui.py) `CustomizeOverlay` → [`memory/config_manager.py`](memory/config_manager.py) | `sync_all_configs()` menyinkronkan semua file config |

## 📜 Aturan Role yang Disepakati (JANGAN dilanggar update berikutnya)

1. **SATU identitas: "Neira".** "Hermes" hanya nama internal inti otak — dilarang disebut ke user
   (di ucapan, teks hasil tool, label terminal, label UI).
2. **Laporan selalu orang pertama "saya"** — "sudah saya perbaiki…", bukan "Hermes menemukan…".
3. **Alur heavy task:** konfirmasi tepat 1 kalimat ("baik, saya kerjakan") → inti otak bekerja
   **senyap** (tanpa update berkala) → lapor hasil dengan "saya".
4. Nama internal kode (`HermesConnector`, blok ```` ```hermes_action ````, `hermes-agent/`,
   `HERMES_API_KEY`) **tidak diubah** demi kompatibilitas parser & config.

## 🧪 Cara Menguji (jalankan dari root repo)

```
.venv\Scripts\python.exe scratch\test_role_identity.py   # identitas role (33 assert)
.venv\Scripts\python.exe scratch\test_skill_memory.py    # memori skill bersama (29 assert)
.venv\Scripts\python.exe scratch\test_ui_restyle.py      # UI/font (23 assert)
.venv\Scripts\python.exe scratch\test_model_picker.py    # dialog pilih model AI (21 assert, offscreen)
```

## ⚠️ Jebakan yang Sudah Diketahui

- Pyrefly false-positive lama: [`ui.py`](ui.py) `img.save(buf, format="PNG")` (qrcode) — **abaikan**.
- Detektor perubahan skill harus pakai signature `(path, mtime_ns)` penuh — detektor `mtime`
  maksimum lama melewatkan **penghapusan** file.
- File skill yang diawali `_` atau `.` dilewati [`discover()`](core/skill_hub.py).
- `execute_command` butuh `cwd` path nyata (`d:/hack/Neira`) — jangan `null`/string "undefined".

---

## Riwayat Entri

### 2026-09-25 — #17 Adopsi 4 Mekanisme Terbaik Brahma-Echo ke Neira
- **File BARU:** [`core/task_queue.py`](core/task_queue.py), [`core/boot_sentry.py`](core/boot_sentry.py),
  [`core/learned_rules.py`](core/learned_rules.py), [`scratch/test_brahma_adoptions.py`](../scratch/test_brahma_adoptions.py).
- **File UBAH:** [`core/brain_hub.py`](core/brain_hub.py) (cooldown per otak),
  [`core/hermes_remediator.py`](core/hermes_remediator.py) (sandbox patch aman), [`main.py`](main.py)
  (wiring boot_sentry + injeksi learned rules).
- **Yang diadopsi (4 mekanisme terbaik dari analisa #16):**
  1. **TaskQueue async berprioritas** — [`core/task_queue.py`](core/task_queue.py): kontrak
     `fn(cancel_flag: threading.Event) -> Any`, prioritas HIGH/NORMAL/LOW, `submit()` non-blocking
     (balik `task_id` 8-hex langsung), `cancel()`, `get_status()`/`get_all_statuses()`, singleton
     [`get_queue()`](core/task_queue.py). Port dari `agent/task_queue.py` Brahma-Echo.
  2. **Cooldown rate-limit per otak** — [`BrainHub`](core/brain_hub.py) kini punya
     [`is_rate_limited()`](core/brain_hub.py)/[`mark_rate_limited()`](core/brain_hub.py)/[`clear_rate_limited()`](core/brain_hub.py)
     (default [`RATE_LIMIT_COOLDOWN = 60.0`](core/brain_hub.py)). [`ask_best()`](core/brain_hub.py) melewati
     otak yang cooldown (`force=True` untuk bypass); `BrainNotReady` TIDAK di-cooldown; anti-lockout
     (bila semua otak cooldown, tetap dicoba); sukses → cooldown dibersihkan. API lama
     `ask_best(prompt)` tetap kompatibel.
  3. **Boot Sentry + patch sandbox (anti-brick)** — [`core/boot_sentry.py`](core/boot_sentry.py)
     (auto-rollback patch terakhir dari `.bak` bila crash log ada saat boot; `mark_crash()`/`clear_crash()`;
     riwayat patch di `shared/memory/patch_history.json`) + di
     [`hermes_remediator.py`](core/hermes_remediator.py): [`validate_code()`](core/hermes_remediator.py)
     (AST+compile in-memory), [`apply_patch_safely()`](core/hermes_remediator.py) (immune files → backup
     `.bak` → tulis atomik `os.replace` → catat riwayat), [`rollback_patch()`](core/hermes_remediator.py).
  4. **Learned rules → prompt injection** — [`core/learned_rules.py`](core/learned_rules.py):
     `add_rule` (dedup case-insensitive), `list_rules`/`toggle_rule`/`delete_rule`,
     [`get_prompt_injections()`](core/learned_rules.py); state di `shared/memory/learned_rules.json`;
     disuntik ke `parts` prompt Neira di [`main.py`](main.py) setelah `parts.append(sys_prompt)`.
- **Wiring [`main.py`](main.py):** `main()` import [`core.boot_sentry`](core/boot_sentry.py) saat
  startup (auto-recovery jalan saat import); `runner()` memanggil `boot_sentry.mark_crash()` bila
  exception tak terduga sebelum re-raise.
- **Yang TIDAK diadopsi (sengaja):** monolith `main.py` 218 KB, dispatch if-elif tool
  (`skill_hub.py` TOOL-dict kita lebih baik), `generate_fix()` eksekusi kode hasil LLM (terlalu berisiko).
- **Uji:** `.venv\Scripts\python.exe scratch\test_brahma_adoptions.py` → **70 PASS / 0 FAIL**
  (5 bagian: task queue, cooldown otak, patch sandbox + boot_sentry, learned rules, wiring + py_compile).
  Regresi: `test_dola_chat.py` 62/62, `test_role_identity.py` 33/33, `test_skill_memory.py` 29/29 — semua hijau.
- **Extend:** mau pakai task queue? `from core.task_queue import get_queue, TaskPriority` lalu
  `get_queue().submit(fn, label=..., priority=..., on_complete=...)` — pastikan `fn` menerima
  `cancel_flag` dan tidak memblokir event loop UI.
- **STATUS PROYEK:** proyek 5-otak (Dola dkk) tetap **PAUSED** oleh user; karya 5-otak yang belum
  tercatat (core/dola_client.py, core/brain_hub.py dasar, skills dola/brain/duck/deepseek/qwen,
  fix uuid dola_pool, fix report_usage) belum masuk CHANGELOG — lanjutkan pencatatan saat resume.

### 2026-09-25 — #16 Analisa Referensi Eksternal "Brahma-Echo" (PAUSED, dokumen saja)
- **File:** [`BRAHMA-ECHO-ANALISIS.md`](BRAHMA-ECHO-ANALISIS.md) (baru), clone referensi di
  `scratch/Brahma-Echo/` (repo `titechprabhasolutions/Brahma-Echo`, depth-1 clone, jangan di-commit).
- **Perubahan:** HANYA dokumen analisa — TIDAK ada kode yang diubah. Referensi = asisten desktop
  Windows sejenis yang diklaim "lebih responsif". 5 rahasia responsivitasnya:
  (1) model-pool 22 model OpenRouter `:free` + cooldown rate-limit per model
  ([`or_client.py`](../scratch/Brahma-Echo/or_client.py)),
  (2) agent loop plan→execute→replan dengan `ErrorDecision` (RETRY/SKIP/REPLAN/ABORT) oleh LLM
  ([`agent/executor.py`](../scratch/Brahma-Echo/agent/executor.py), [`agent/error_handler.py`](../scratch/Brahma-Echo/agent/error_handler.py)),
  (3) task queue async berprioritas + `cancel_flag` ([`agent/task_queue.py`](../scratch/Brahma-Echo/agent/task_queue.py)),
  (4) self-healing AST sandbox + Boot Sentry auto-rollback ([`actions/auto_heal_engine.py`](../scratch/Brahma-Echo/actions/auto_heal_engine.py), [`core/boot_sentry.py`](../scratch/Brahma-Echo/core/boot_sentry.py)),
  (5) learned-rules prompt injection + breadcrumb "thinking out loud" + SFX prosedural
  ([`core/learned_rules.py`](../scratch/Brahma-Echo/core/learned_rules.py), [`sound_manager.py`](../scratch/Brahma-Echo/sound_manager.py)).
  Rekomendasi adopsi P1–P4 + peta jalan TAHAP A–F ada di bagian 5–6 dokumen tersebut.
- **Extend:** mau mulai adopsi? Ikuti TAHAP A (port `agent/task_queue.py` → `core/task_queue.py`)
  dulu; jangan tiru kelemahannya (monolith `main.py` 218 KB, dispatch if-elif `agent/executor.py`).
- **Uji:** tidak ada kode baru → tidak ada test. Konvensi test tetap pakai
  `.venv\Scripts\python.exe scratch\test_*.py` dari root repo.
- **STATUS PROYEK:** proyek 5-otak (Dola dkk) tetap **PAUSED** oleh user; karya 5-otak yang belum
  tercatat (core/dola_client.py, core/brain_hub.py, skills dola/brain/duck/deepseek/qwen,
  fix uuid dola_pool, fix report_usage) belum masuk CHANGELOG — lanjutkan pencatatan saat resume.

### 2026-09-25 — #15 Dialog Pilih Model AI (ModelPickerDialog)
- **File:** `ui.py`, `scratch/test_model_picker.py` (baru).
- **Perubahan:** popup model [`QInputDialog.getItem`](ui.py) yang kaku/fixed-size diganti
  class [`ModelPickerDialog(QDialog)`](ui.py) (sebelum [`PluginManagerOverlay`](ui.py)):
  resizable (min 520×420), pencarian real-time (filter substring, case-insensitive),
  double-click / Enter / tombol PILIH untuk memilih, tombol BATAL, model aktif ditandai
  `● AKTIF` (teks bold `C.PRI`, id asli disimpan di [`Qt.ItemDataRole.UserRole`](ui.py)),
  tema gelap aplikasi (`C.*`), subtitle jumlah model + base URL, status bar
  "Menampilkan X dari Y model". Hasil: `dlg.selected` (str, `""` jika batal) →
  [`_fetch_models()`](ui.py) menyalin ke `self._model_input`.
- **Extend:** mau tambah kolom (harga/latensi) atau multi-pilih? Edit
  [`ModelPickerDialog._apply_filter()`](ui.py) (isi baris) + [`_pick_selected()`](ui.py).
  Mau ganti ukuran default: `resize()` di [`__init__`](ui.py) class tersebut.
- **Uji:** `test_model_picker.py` 21/21 PASS (offscreen, `QT_QPA_PLATFORM=offscreen`);
  `py_compile ui.py` OK. Catatan: test butuh `dlg.show()` dulu sebelum cek fokus
  (widget tak pernah tampil = fokus belum diberikan), dan stdout test di-reconfigure
  utf-8 (console cp1252 tak bisa cetak karakter `●`).

### 2026-09-25 — #14 Rombak Role & Naming: SATU Identitas "Neira"
- **File:** `core/prompt.txt`, `router/hermes_connector.py`, `skills/dev/deep_think.py`,
  `core/hermes_executor.py`, `core/hermes_remediator.py`, `skills/admin/manage_skills.py`,
  `skills/admin/open_app.py`, `core/skill_hub.py`, `ui.py`, `scratch/test_role_identity.py` (baru).
- **Perubahan:** framing "Mandor ↔ Hermes" (2 entitas) dihapus → ONE identity + Surface/Deep-core
  layer; IDENTITY RULE larang sebut "Hermes"; HEAVY TASK FLOW (1 kalimat → senyap → lapor "saya");
  `report_for_mark` wajib orang pertama; semua teks user-facing dibersihkan dari "Hermes"
  (judul terminal → `Neira Terminal`, label UI → "INTI OTAK", hasil remediasi → "Saya membuka…").
- **Extend:** mau ubah gaya laporan? Edit `report_for_mark` di kedua prompt inti otak + [SELF]
  `core/prompt.txt`. Mau ubah alur heavy task? Edit bagian `HEAVY TASK FLOW` di `core/prompt.txt`.
- **Uji:** `test_role_identity.py` 33/33 PASS; regresi `test_skill_memory.py` 29/29 PASS.

### 2026-09-25 — #13 Memori Skill Bersama (Katalog Live & Routing Kategori)
- **File:** `core/skill_hub.py`, `core/action_loader.py`, `main.py`, `core/prompt.txt`,
  `router/hermes_connector.py`, `scratch/test_skill_memory.py` (baru).
- **Perubahan:** auto-refresh [`ensure_fresh()`](core/skill_hub.py) signature `(path, mtime_ns)`;
  label `[KONTEN]`/`[ADMIN]`/… di deklarasi tool; [`get_routing_guide()`](core/skill_hub.py)
  disuntikkan ke kedua prompt via `{skill_routing}`; fallback [`skill_hub.run()`](core/skill_hub.py)
  di `_execute_tool()`; fix `import re` hilang di `hermes_connector.py`.
- **Extend:** skill baru cukup taruh di `skills/<kategori>/<nama>.py` dengan `TOOL = {...}` —
  otomatis muncul di katalog + routing map dua lapis tanpa restart.
- **Uji:** `test_skill_memory.py` 29/29 PASS.

### 2026-09-25 — #12 Rombak UI: Setelan Font + Restyle QSS Modern
- **File:** `ui.py`, `scratch/test_ui_restyle.py` (baru).
- **Perubahan:** section UI FONT (family/warna/skala 85–130%) via shim QFont modular; radius
  seragam 6/8px; palet surface lebih berlapis; `MetricBar` baris tipis; `LogWidget` chat row.
- **Extend:** warna tema utama tetap di palet `C.*`; font disimpan sebagai `ui_font_*` di config.
- **Uji:** `test_ui_restyle.py` 23/23 PASS.
