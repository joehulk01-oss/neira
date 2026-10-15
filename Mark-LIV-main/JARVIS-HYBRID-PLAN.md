# 📋 RENCANA LENGKAP PROYEK: JARVIS HYBRID AI

> **Dokumen Teknis untuk Pengembangan**
> **Versi**: 1.0
> **Tanggal**: 22 September 2026
> **Status**: Siap Dikerjakan

---

## 🎯 1. RINGKASAN PROYEK

Membangun sistem asisten AI **JARVIS HYBRID** yang menggabungkan dua "otak" AI dalam satu aplikasi portabel:

- **Otak 1 - Gemini (via Mark-LIV)**: Untuk percakapan ringan, tampilan wajah holografik, suara, dan kontrol komputer dasar
- **Otak 2 - Hermes Agent**: Untuk tugas berat, analisa data, pembelajaran mandiri, dan pembuatan keterampilan baru
- **Router Pintar**: Sistem yang secara otomatis memutuskan otak mana yang harus aktif berdasarkan kompleksitas pertanyaan

**Prinsip Utama**: **PORTABEL** — Semua dalam satu folder, tinggal copy-paste + jalankan script instalasi, langsung jalan di komputer manapun.

---

## 🏗️ 2. ARSITEKTUR SISTEM

```
┌─────────────────────────────────────────────────────────┐
│                   USER (SUARA / TEKS)                    │
└────────────────────────────┬────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────┐
│              MARK-LIV (Speech-to-Text + TTS)            │
│              (Wajah Holografik + Suara)                 │
└────────────────────────────┬────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────┐
│                  🧠 BRAIN ROUTER                        │
│  • Cek kata kunci tugas berat                           │
│  • Nilai kompleksitas pertanyaan (skor 1-10)            │
│  • Putuskan: GEMINI (ringan) ATAU HERMES (berat)        │
└───────────────────┬─────────────────────────────────────┘
                    │
          ┌─────────┴──────────┐
          ↓                    ↓
┌──────────────────┐  ┌──────────────────────────┐
│ 🔵 GEMINI API    │  │ 🟣 HERMES AGENT          │
│ • Percakapan     │  │ • Analisa data           │
│ • Jawaban cepat  │  │ • Pembelajaran mandiri   │
│ • Kontrol dasar  │  │ • Pembuatan skill baru   │
└─────────┬────────┘  └────────────┬─────────────┘
          ↓                        ↓
┌─────────────────────────────────────────────────────────┐
│              MARK-LIV (Tampilkan Jawaban)               │
│          (Suara + Animasi Wajah + Teks)                 │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 3. STRUKTUR FOLDER FINAL

```
📦 JARVIS-HYBRID/                    ← FOLDER INDUK UTAMA (INI YANG DI-COPY)
│
├── 📂 mark-liv/                     ← Repo Mark-LIV asli (FatihMakes)
│   ├── 📄 main.py                   ← DIMODIFIKASI: memanggil Router
│   ├── 📂 memory/                   ← Memori jangka panjang Mark-LIV
│   │   ├── long_term.json
│   │   └── conversation_history.json
│   ├── 📂 plugins/
│   ├── 📂 assets/
│   └── ... (semua file asli Mark-LIV)
│
├── 📂 hermes-agent/                 ← Repo Hermes Agent (NousResearch)
│   ├── 📄 hermes_main.py
│   ├── 📂 data/
│   │   ├── 📂 memories/             ← Memori & pembelajaran Hermes
│   │   └── 📂 skills/               ← Skill yang dipelajari sendiri
│   └── ... (semua file asli Hermes)
│
├── 📂 router/                       ← BUAT BARU (Inti Integrasi)
│   ├── 📄 __init__.py
│   ├── 📄 brain_router.py           ← Logika pemilihan otak
│   ├── 📄 gemini_connector.py       ← Penghubung ke Gemini API
│   └── 📄 hermes_connector.py       ← Penghubung ke Hermes Agent
│
├── 📂 shared/                       ← BUAT BARU (Data Bersama)
│   ├── 📄 config.env                ← SEMUA API KEY & KONFIGURASI
│   ├── 📂 memory/                   ← Memori bersama kedua otak
│   │   ├── user_preferences.json
│   │   ├── business_data.json
│   │   └── system_settings.json
│   └── 📂 logs/                     ← Catatan aktifitas sistem
│
├── 📄 requirements.txt              ← Semua dependensi Python
├── 📄 install.bat                   ← Script instalasi OTOMATIS (Windows)
├── 📄 start.bat                     ← Script jalankan OTOMATIS (Windows)
└── 📄 README.md                     ← Dokumentasi penggunaan
```

---

## 🔧 4. SPESIFIKASI FILE-FILE UTAMA

### 4.1 `shared/config.env` — Konfigurasi Sentral

Semua konfigurasi dan API key disimpan di sini. **JANGAN hardcode di kode Python**.

```env
# ========================================
# API KEYS
# ========================================
GEMINI_API_KEY=your_gemini_key_here
HERMES_API_KEY=your_hermes_key_here
OPENROUTER_API_KEY=your_openrouter_key_here

# ========================================
# PENGATURAN SISTEM
# ========================================
ROUTER_THRESHOLD=5              # Ambang batas kompleksitas (1-10)
DEFAULT_VOICE=Mark-LIV-Voice
LANGUAGE=id-ID
AUTO_LEARN=true
LOG_LEVEL=INFO
```

---

### 4.2 `router/brain_router.py` — Otak Pengatur Lalu Lintas

**Tanggung Jawab**:
1. Menerima input teks dari user
2. Menganalisa kompleksitas dengan 2 metode:
   - **Cek kata kunci**: `analisa`, `analisis`, `buatkan`, `rancang`, `kode`, `program`, `data`, `laporan`, `ingat`, `pelajari`, `pola`, `strategi`, `perhitungan`
   - **Penilaian skor**: Minta Gemini menilai 1-10, di atas ambang batas → lempar ke Hermes
3. Memanggil otak yang tepat
4. Mengembalikan hasil jawaban

**Logika Routing (Prioritas)**:
```
1. JIKA ada kata kunci tugas berat → HERMES
2. JIKA panjang teks > 20 kata     → HERMES
3. JIKA skor kompleksitas > ambang → HERMES
4. SELAIN ITU                      → GEMINI
```

**Fallback**: Jika Hermes error, otomatis kembali ke Gemini dengan pesan: *"Saya coba jawab dengan cara yang lebih sederhana ya..."*

---

### 4.3 `router/gemini_connector.py`

**Fungsi yang harus ada**:
- `__init__(config_path)`: Memuat konfigurasi dari `config.env`
- `chat(user_input)`: Percakapan ringan dengan Gemini
- `rate_complexity(user_input)`: Menilai skor kompleksitas 1-10
- `speak_nicely(text)`: Memperhalus bahasa jawaban dari Hermes sebelum disampaikan

---

### 4.4 `router/hermes_connector.py`

**Fungsi yang harus ada**:
- `__init__(config_path)`: Memuat konfigurasi & inisialisasi Hermes
- `process_heavy_task(user_input)`: Memproses tugas berat melalui Hermes
- `save_learning()`: Menyimpan hasil pembelajaran ke `hermes-agent/data/`
- `get_skill(skill_name)`: Memanggil skill yang sudah dipelajari Hermes

---

### 4.5 Modifikasi `mark-liv/main.py`

Bagian yang memproses input user diubah dari:
```python
# LAMA: Langsung panggil Gemini
response = gemini_model.generate_content(user_input)
```

Menjadi:
```python
# BARU: Lewat Router dulu
import sys
import os

# Tambahkan path router
router_path = os.path.join(os.path.dirname(__file__), '..', 'router')
sys.path.append(router_path)

from brain_router import BrainRouter

# Inisialisasi router (hanya sekali saat startup)
config_path = os.path.join(os.path.dirname(__file__), '..', 'shared', 'config.env')
router = BrainRouter(config_path=config_path)

# Di bagian pemrosesan input:
response = router.route_response(user_input)
```

---

### 4.6 `requirements.txt`

Daftar semua library yang dibutuhkan. Generate dengan perintah:
```bash
pip freeze > requirements.txt
```

Pastikan mencakup minimal:
```
google-generativeai>=0.3.0
python-dotenv>=1.0.0
numpy>=1.24.0
sounddevice>=0.4.6
soundfile>=0.12.1
# + semua dependensi asli Mark-LIV & Hermes
```

---

### 4.7 `install.bat` — Instalasi Otomatis

```batch
@echo off
chcp 65001 >nul
echo ========================================
echo   JARVIS HYBRID - INSTALASI OTOMATIS
echo ========================================
echo.

echo [1/4] Membuat Virtual Environment...
python -m venv venv
if errorlevel 1 goto error

echo [2/4] Mengaktifkan Virtual Environment...
call venv\Scripts\activate.bat

echo [3/4] Menginstal semua library (mohon tunggu)...
pip install --upgrade pip
pip install -r requirements.txt
if errorlevel 1 goto error

echo [4/4] Membuat folder yang dibutuhkan...
if not exist "shared\memory" mkdir shared\memory
if not exist "shared\logs" mkdir shared\logs

echo.
echo ========================================
echo   INSTALASI BERHASIL!
echo   Jalankan 'start.bat' untuk memulai
echo ========================================
pause
exit /b 0

:error
echo.
echo TERJADI KESALAHAN!
echo Pastikan Python 3.10+ sudah terinstal dan ada di PATH.
pause
exit /b 1
```

---

### 4.8 `start.bat` — Menjalankan Otomatis

```batch
@echo off
chcp 65001 >nul
echo ========================================
echo   MENJALANKAN JARVIS HYBRID
echo ========================================

call venv\Scripts\activate.bat

cd mark-liv
python main.py
```

---

## 🚀 5. URUTAN PENGERJAAN (TIMELINE)

### TAHAP 1: Persiapan & Struktur Dasar
1. Clone repo Mark-LIV ke folder `mark-liv/`
2. Clone repo Hermes Agent ke folder `hermes-agent/`
3. Buat struktur folder `router/` dan `shared/`
4. Buat file template `shared/config.env`

### TAHAP 2: Membangun Router & Konektor
5. Buat `router/brain_router.py` dengan logika routing
6. Buat `router/gemini_connector.py`
7. Buat `router/hermes_connector.py`
8. Test router secara terpisah (unit test tanpa Mark-LIV)

### TAHAP 3: Integrasi dengan Mark-LIV
9. Modifikasi `mark-liv/main.py` untuk memanggil router
10. Pastikan suara & wajah tetap berfungsi normal
11. Test alur lengkap: suara → router → jawaban → suara/wajah

### TAHAP 4: Portabilitas & Otomatisasi
12. Generate `requirements.txt` yang lengkap
13. Buat `install.bat` dan `start.bat`
14. **Test Migrasi**: Copy folder ke lokasi baru, jalankan `install.bat`, verifikasi semua berjalan

### TAHAP 5: Pengujian & Penyempurnaan
15. Test berbagai skenario pertanyaan (ringan & berat)
16. Verifikasi memori tersimpan & terbaca dengan benar
17. Optimasi performa & kecepatan respon
18. Buat dokumentasi `README.md`

---

## ✅ 6. KRITERIA KEBERHASILAN

Sistem dinyatakan **BERHASIL & SIAP PAKAI** jika memenuhi SEMUA kriteria di bawah:

| No | Kriteria | Status |
|---|---|---|
| 1 | Bisa diinstal hanya dengan **double klik `install.bat`** | ⬜ |
| 2 | Bisa dijalankan hanya dengan **double klik `start.bat`** | ⬜ |
| 3 | Pertanyaan ringan otomatis dijawab oleh **Gemini** (cepat, hemat token) | ⬜ |
| 4 | Pertanyaan berat otomatis dialihkan ke **Hermes** (akurat, mendalam) | ⬜ |
| 5 | **Tidak pernah** ada dua jawaban bersamaan atau tabrakan suara | ⬜ |
| 6 | Memori tetap **utuh 100%** setelah folder dipindah ke komputer lain | ⬜ |
| 7 | Tampilan wajah & suara Mark-LIV **berfungsi normal** seperti aslinya | ⬜ |
| 8 | Semua API key tersimpan **aman di `config.env`**, tidak ada di kode | ⬜ |
| 9 | Jika Hermes error, sistem **otomatis fallback** ke Gemini | ⬜ |
| 10 | Semua path menggunakan **relative path**, bukan absolute path | ⬜ |

---

## 📝 7. CATATAN PENTING UNTUK DEVELOPER

1. **PATH**: Selalu gunakan **relative path** (`../folder/file`), **JANGAN** gunakan absolute path (`C:\Users\...`)
2. **API KEY**: Semua kunci API harus di `shared/config.env`, **JANGAN** di-hardcode di file Python manapun
3. **PORTABILITAS**: Folder `venv/` **TIDAK PERLU** dibawa saat migrasi. Akan dibuat ulang otomatis oleh `install.bat`
4. **ERROR HANDLING**: Setiap pemanggilan API harus ada try-except dan mekanisme fallback
5. **LOGGING**: Semua aktifitas penting dicatat ke `shared/logs/` untuk debugging
6. **KOMENTAR**: Berikan komentar yang jelas di bagian kode yang krusial
7. **GIT**: Jika menggunakan Git, tambahkan ini ke `.gitignore`:
   ```
   venv/
   __pycache__/
   *.log
   shared/config.env
   ```

---

## 🎁 8. FITUR MASA DEPAN (OPSIONAL)

Fitur ini bisa ditambahkan setelah sistem dasar berjalan stabil:

- [ ] Memori bersama otomatis tersinkronisasi antara Gemini & Hermes
- [ ] Dashboard monitoring sederhana untuk melihat otak mana yang aktif
- [ ] Mode "belajar intensif" khusus untuk Hermes
- [ ] Backup memori otomatis ke cloud storage
- [ ] Sistem plugin untuk menambah kemampuan tanpa ubah kode inti
- [ ] Multi-user support dengan profil masing-masing

---

## 📞 9. KONTAK & REFERENSI

- **Mark-LIV (FatihMakes)**: https://github.com/FatihMakes/Mark-LIV
- **Hermes Agent (NousResearch)**: https://github.com/NousResearch/hermes-agent

---

> **Dokumen ini adalah panduan lengkap pengembangan. Ikuti urutan tahapan dan pastikan semua kriteria keberhasilan terpenuhi.**
