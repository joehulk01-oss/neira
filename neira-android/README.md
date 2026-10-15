# 📱 ANDROID — neira.apk (remote Neira dari HP)

> Peta lokasi: [`../README.md`](../README.md) · ☁️ VPS: [`../neira-gateway/README.md`](../neira-gateway/README.md) · 💻 PC: [`../Mark-LIV-main/deploy/README.md`](../Mark-LIV-main/deploy/README.md)
>
> **Folder ini = semua yang di-build untuk HP Android.** Repo GitHub: **`neira-android`** (baru).

## Peran
Klien Android yang menyambung ke VPS Gateway (`wss://`) dan meneruskan perintah/suara ke PC:
remote control Neira dari HP — kirim perintah suara/teks, dengar suara Neira (TTS) di HP, lihat log & status.

## Pilihan teknologi (rekomendasi = Opsi A dulu, lanjut B)

| Opsi | Stack | Kelebihan | Kekurangan |
|---|---|---|---|
| **A. WebView wrapper (fase 1)** | Kotlin + WebView memuat dashboard web dari VPS | cepat jadi (1-2 hari), UI = dashboard yang sudah ada, auto-update UI tanpa rilis APK | fitur native terbatas |
| **B. Native ringkas (fase 2)** | Kotlin + Jetpack Compose + OkHttp WebSocket | mic push-to-talk native, notifikasi, widget, kualitas audio lebih baik | butuh waktu bangun UI |
| C. Flutter | Flutter + web_socket_channel | satu kode untuk iOS nanti | ekosistem tambahan |

**Rencana:** rilis **Opsi A** dulu (APK kecil, langsung terpakai) → lanjut **Opsi B** untuk fitur suara penuh.

## Struktur akhir folder ini (saat implementasi)

```
neira-android/               ← folder ini (repo "neira-android")
├── README.md                ← file ini
├── gradle/ / build.gradle.kts / settings.gradle.kts
└── app/
    ├── src/main/
    │   ├── java/.../MainActivity.kt       # WebView + izin mic/kamera
    │   ├── java/.../GatewaySocket.kt      # (fase 2) klien WebSocket wss:// + reconnect
    │   ├── java/.../PairingActivity.kt    # scan QR pairing (kamera → token sekali-pakai)
    │   └── res/                           # ikon, splash Neira
    └── build.gradle.kts
```

## Fitur per fase
- **Fase 1 (WebView):** buka `https://domain-vps` → login via QR (pola [`RemoteKeyOverlay`](../Mark-LIV-main/ui.py)) →
  kirim teks/perintah, lihat log & status reaktor, mic via WebRTC dashboard (sudah ada `/ws/phone-audio`).
- **Fase 2 (native):** push-to-talk native (mic HP → `AUDIO` → [`_relay_phone_audio()`](../Mark-LIV-main/main.py)),
  notifikasi saat Neira selesai tugas, pemutaran suara Neira (TTS) di speaker HP,
  widget layar kunci, simpan `DEVICE_KEY` di EncryptedSharedPreferences.

## Protokol (sama persis dengan EXE — lihat [`../neira-gateway/README.md`](../neira-gateway/README.md))
`PAIR_REQUEST`/`PAIR_APPROVED` → `PING`/`PONG` → relay `COMMAND`/`LOG`/`STATUS`/`AUDIO`.

## Uji
- `./gradlew assembleDebug` → instal APK di HP → scan QR dari PC → kirim "halo" → balasan Neira muncul + suara terdengar di HP.
- Uji putus koneksi: matikan VPS sebentar → app auto-reconnect tanpa crash.
