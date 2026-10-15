# 🔍 ANALISA REFERENSI: Brahma-Echo vs Neira (Mark-LIV)

> Referensi: <https://github.com/titechprabhasolutions/Brahma-Echo.git>
> Lokasi clone: [`scratch/Brahma-Echo/`](../scratch/Brahma-Echo/)
> Tanggal analisa: 2026-09-25
> Status proyek 5-otak: **PAUSED** — analisa ini bahan pertimbangan sebelum lanjut.

---

## 1. Ringkasan Eksekutif

Brahma-Echo adalah asisten desktop Windows open-source dengan klaim **"lebih responsif"** dibanding Neira. Setelah bedah kode, klaim itu berasal dari **5 mekanisme konkret**, bukan sekadar LLM lebih cepat:

1. **Model-pool fallback** ([`or_client.py`](../scratch/Brahma-Echo/or_client.py)) — 22 model gratis OpenRouter dirotasi otomatis + cooldown rate-limit per model.
2. **Agent loop plan→execute→replan** ([`agent/executor.py`](../scratch/Brahma-Echo/agent/executor.py)) — perintah kompleks dipecah jadi maks 5 langkah, tiap langkah punya 3 percobaan + keputusan error oleh LLM ([`agent/error_handler.py`](../scratch/Brahma-Echo/agent/error_handler.py)).
3. **Task queue async berprioritas** ([`agent/task_queue.py`](../scratch/Brahma-Echo/agent/task_queue.py)) — UI tidak pernah nge-hang; tugas berat jalan di thread dengan `cancel_flag`.
4. **Self-healing AST sandbox + Boot Sentry** ([`actions/auto_heal_engine.py`](../scratch/Brahma-Echo/actions/auto_heal_engine.py), [`core/boot_sentry.py`](../scratch/Brahma-Echo/core/boot_sentry.py)) — patch otomatis divalidasi `ast.parse()` sebelum ditulis, dan rollback otomatis saat boot jika patch bikin crash.
5. **Learned rules + feedback loop UI** ([`core/learned_rules.py`](../scratch/Brahma-Echo/core/learned_rules.py), [`sound_manager.py`](../scratch/Brahma-Echo/sound_manager.py)) — preferensi user diinjeksi ke prompt tanpa edit kode; breadcrumb "thinking out loud" + SFX prosedural membuat interaksi *terasa* instan.

Kesimpulan: **responsivitas = arsitektur**, bukan kecepatan model. Semua mekanisme di atas bisa dipindah ke Neira.

---

## 2. Anatomi "Responsivitas" Brahma-Echo

### 2.1 Model-pool fallback (anti rate-limit)

[`TEXT_MODELS`](../scratch/Brahma-Echo/or_client.py:36) berisi 22 model `:free` OpenRouter (Nemotron, Hermes-3-405B, MiniMax, Qwen3, Gemma 4, dst). Mekanisme [`_call_with_fallback()`](../scratch/Brahma-Echo/or_client.py:183):

- Coba model yang diminta user dulu; kalau gagal → lanjut ke pool.
- HTTP 429 → [`_mark_rate_limited()`](../scratch/Brahma-Echo/or_client.py:102) memberi **cooldown 60 detik** per model, model lain langsung dipakai.
- [`_call()`](../scratch/Brahma-Echo/or_client.py:109) retry 2× per model dengan jeda 2 detik, timeout 60 detik.
- [`UnifiedAIClient`](../scratch/Brahma-Echo/llm_client.py:20) di atasnya mendukung provider **Local** (Ollama/LM Studio, endpoint `http://localhost:11434/v1`) yang bisa di-switch lewat `app_settings.json` — plus API [`chat_json()`](../scratch/Brahma-Echo/or_client.py:239), [`vision()`](../scratch/Brahma-Echo/or_client.py:277), [`multi_turn()`](../scratch/Brahma-Echo/or_client.py:328).

> **Relevansi 5-otak:** ini persis pola `ask_best()` di [`core/brain_hub.py`](core/brain_hub.py) — tapi Brahma-Echo menambah **cooldown rate-limit per model** yang belum kita punya. Wajib ditiru.

### 2.2 Agent loop: plan → execute → replan

[`AgentExecutor.execute()`](../scratch/Brahma-Echo/agent/executor.py:395):

1. [`create_plan(goal)`](../scratch/Brahma-Echo/agent/planner.py) — LLM (Gemini Flash-Lite) memecah goal jadi JSON langkah (`tool` + `parameters` + `critical`), **maks 5 langkah**, dengan katalog tool lengkap yang ditulis eksplisit di [`PLANNER_PROMPT`](../scratch/Brahma-Echo/agent/planner.py:24).
2. Tiap langkah: [`_inject_context()`](../scratch/Brahma-Echo/agent/executor.py:117) menyuntik hasil riset langkah sebelumnya ke parameter `content` (mis. hasil `web_search` masuk ke `pdf_document`), lalu [`_call_tool()`](../scratch/Brahma-Echo/agent/executor.py:197) mengeksekusi.
3. Gagal → [`analyze_error()`](../scratch/Brahma-Echo/agent/error_handler.py:58) memutuskan `RETRY | SKIP | REPLAN | ABORT` via LLM; langkah `critical: true` tidak boleh di-skip (dipaksa REPLAN).
4. REPLAN → [`replan()`](../scratch/Brahma-Echo/agent/planner.py) menyusun ulang plan dari langkah yang sudah selesai + [`generate_fix()`](../scratch/Brahma-Echo/agent/error_handler.py:145) membuat langkah pengganti. Maksimal [`MAX_REPLAN_ATTEMPTS = 2`](../scratch/Brahma-Echo/agent/executor.py:393).
5. Selesai → [`_summarize()`](../scratch/Brahma-Echo/agent/executor.py:580) merangkum jadi satu kalimat untuk dibacakan.

Keunggulan halus: deteksi **deliverable file** via regex path Windows ([`agent/executor.py:466`](../scratch/Brahma-Echo/agent/executor.py:466)) → file hasil langsung ditampilkan di HUD.

### 2.3 Task queue: UI tidak pernah blokir

[`TaskQueue`](../scratch/Brahma-Echo/agent/task_queue.py:38): priority queue (`HIGH/NORMAL/LOW`) + worker thread daemon + `threading.Event` [`cancel_flag`](../scratch/Brahma-Echo/agent/task_queue.py:34) untuk batal-in tugas dari UI. [`submit()`](../scratch/Brahma-Echo/agent/task_queue.py:74) mengembalikan `task_id` seketika → UI langsung bebas. Callback [`on_complete`](../scratch/Brahma-Echo/agent/task_queue.py:196) melaporkan hasil.

### 2.4 Self-healing aman (AST sandbox + Boot Sentry)

- [`TracebackAnalyzer.parse()`](../scratch/Brahma-Echo/actions/auto_heal_engine.py:63) — isolasi file + baris first-party yang error, file inti masuk daftar **immune** (tidak boleh di-patch).
- [`SafetySandbox.validate_code()`](../scratch/Brahma-Echo/actions/auto_heal_engine.py:148) — kandidat patch wajib lolos `ast.parse()` + `py_compile` **di memori** sebelum menyentuh disk; [`create_backup()`](../scratch/Brahma-Echo/actions/auto_heal_engine.py:139) membuat `.bak` atomik; [`rollback_patch()`](../scratch/Brahma-Echo/actions/auto_heal_engine.py:159) bisa membalik per `patch_id`.
- [`check_and_recover_on_boot()`](../scratch/Brahma-Echo/core/boot_sentry.py:23) — **dijalankan saat import** ([`core/boot_sentry.py:75`](../scratch/Brahma-Echo/core/boot_sentry.py:75)), sebelum UI/Gemini dimuat: kalau ada `FATAL_CRASH.log` dan patch terakhir < 5 menit sebelum crash → otomatis restore dari `.bak`. Inilah klaim **"zero-brick"**.

### 2.5 Responsivitas "terasa": learned rules, breadcrumbs, SFX

- [`LearnedRulesEngine.get_prompt_injections()`](../scratch/Brahma-Echo/core/learned_rules.py:113) — aturan preferensi user (dedup, toggle, kategori) di-**inject ke system prompt runtime** → asisten "belajar" tanpa edit kode.
- Breadcrumb per langkah di [`_call_tool()`](../scratch/Brahma-Echo/agent/executor.py:198) (`"Searching: ..."` → `ui.set_state("THINKING")`) = *thinking out loud*.
- [`sound_manager.py`](../scratch/Brahma-Echo/sound_manager.py) — 5 SFX sci-fi **disintesis prosedural** (sine + envelope, [`_generate_default_sounds()`](../scratch/Brahma-Echo/sound_manager.py:29)) jadi WAV 44.1 kHz, diputar non-blocking via `QSoundEffect` → feedback <50 ms tanpa menunggu LLM.

---

## 3. Peta Fitur: Brahma-Echo vs Neira (Mark-LIV)

| Aspek | Brahma-Echo | Neira (Mark-LIV) | Nilai buat Neira |
|---|---|---|---|
| LLM utama | Gemini Flash-Lite + pool 22 model OpenRouter `:free` + Ollama lokal | Gemini + Hermes ([`router/hermes_connector.py`](router/hermes_connector.py)) + 5-otak [`core/brain_hub.py`](core/brain_hub.py) (baru) | **Tiru pool + cooldown** |
| Routing multi-otak | Tidak ada (pool = jenis model sama) | [`BrainHub.ask_best()`](core/brain_hub.py) 5 otak beda vendor | Kita sudah lebih maju — tinggal matangkan |
| Agent multi-langkah | [`agent/`](../scratch/Brahma-Echo/agent) plan/executor/error_handler/task_queue | [`actions/dev_agent.py`](actions/dev_agent.py) + [`core/hermes_executor.py`](core/hermes_executor.py) (terbatas) | **Tiru plan→replan + error decision** |
| Async task queue | ✅ prioritas + cancel | ❌ sebagian besar sinkron | **Tiru** (kunci UI responsif) |
| Self-healing | AST sandbox + Boot Sentry + rollback per patch | [`core/hermes_remediator.py`](core/hermes_remediator.py) + [`core/undo.py`](core/undo.py) (tanpa guard AST/boot) | **Gabungkan** pola sandbox ke remediator |
| Belajar preferensi | [`core/learned_rules.py`](../scratch/Brahma-Echo/core/learned_rules.py) → inject prompt | [`shared/memory/user_preferences.json`](shared/memory/user_preferences.json) + [`memory/config_manager.py`](memory/config_manager.py) | **Tiru injeksi prompt otomatis** |
| Skill/action system | `actions/` flat + dispatch if-elif besar di [`_call_tool()`](../scratch/Brahma-Echo/agent/executor.py:197) | [`core/skill_hub.py`](core/skill_hub.py) auto-discovery + TOOL dict (30 skill) | **Kita lebih rapi** — jangan tiru if-elif |
| Browser automation | Playwright MCP resmi (JSON-RPC stdio, 24 aksi, a11y tree) | [`skills/admin/browser_control.py`](skills/admin/browser_control.py) + CDP custom | Pertimbangkan `@playwright/mcp` |
| Remote/Android | Brahma Connect (WebSocket + pairing kripto + Accessibility autopilot) + Discord bot | ❌ belum ada | Fitur masa depan |
| UI | PyQt6 holographic + HUD telemetry + SFX prosedural + 3D cursor gaze | [`ui.py`](ui.py) (avatar [`core/avatar.py`](core/avatar.py), viseme [`core/viseme.py`](core/viseme.py)) | Tiru **breadcrumb + SFX** saja |
| Dokumentasi | README 391 baris marketing-grade | [`CHANGELOG.md`](CHANGELOG.md) + [`UPDATE_LOG.md`](UPDATE_LOG.md) + [`JARVIS-HYBRID-PLAN.md`](JARVIS-HYBRID-PLAN.md) | Setara, beda gaya |

---

## 4. Kelemahan Brahma-Echo (jangan ditiru)

1. **[`main.py`](../scratch/Brahma-Echo/main.py) 218 KB satu file** (± 5.000 baris) — monolit UI+logic; Neira sudah lebih termodulasi lewat [`core/skill_hub.py`](core/skill_hub.py).
2. **Dispatch if-elif raksasa** di [`_call_tool()`](../scratch/Brahma-Echo/agent/executor.py:197) — menambah tool = edit fungsi inti; berbeda dengan konvensi `TOOL` dict Neira.
3. **API key Gemini dibaca ulang** dari `api_keys.json` di banyak modul ([`_get_api_key()`](../scratch/Brahma-Echo/agent/executor.py:32)) tanpa caching — rawan race & I/O berulang.
4. **`generate_fix()`** ([`agent/error_handler.py:145`](../scratch/Brahma-Echo/agent/error_handler.py:145)) memanggil Gemini untuk menulis kode lalu menjalankannya lewat `claude_code`/`generated_code` — permukaan serangan besar kalau prompt bocor.
5. Test hanya 2 file ([`tests/`](../scratch/Brahma-Echo/tests)) vs [`scratch/test_*.py`](scratch) Neira yang lebih luas.

---

## 5. Rekomendasi Adopsi untuk Neira (urut prioritas)

### P1 — Bikin Neira "terasa" responsif (murah, dampak besar)
1. **Task queue berprioritas** — port [`agent/task_queue.py`](../scratch/Brahma-Echo/agent/task_queue.py) → `core/task_queue.py`; semua skill `behavior: "NON_BLOCKING"` lewat queue ini + `cancel_flag`.
2. **Breadcrumb "thinking out loud"** — tiap langkah skill/agent update status UI (Neira sudah punya state di [`ui.py`](ui.py)).
3. **SFX prosedural** — port [`sound_manager.py`](../scratch/Brahma-Echo/sound_manager.py) (murni stdlib `wave`+`struct`, tanpa asset) untuk feedback listen/think/done.

### P2 — Ketahanan 5-otak
4. **Cooldown rate-limit per otak** — tambah `_rate_limited` map ala [`or_client.py:80`](../scratch/Brahma-Echo/or_client.py:80) ke [`BrainHub`](core/brain_hub.py): otak kena limit → fallback [`ask_best()`](core/brain_hub.py) otomatis pindah, cooldown 60 detik.
5. **Model-pool per otak** — tiap otak (Dola/DeepSeek/Qwen/Duck) boleh punya daftar model `:free` seperti [`TEXT_MODELS`](../scratch/Brahma-Echo/or_client.py:36); OpenRouter `:free` bisa jadi **otak cadangan ke-6** gratis.
6. **Error decision loop** — port pola [`ErrorDecision`](../scratch/Brahma-Echo/agent/error_handler.py:19) (`RETRY/SKIP/REPLAN/ABORT`) ke [`core/hermes_executor.py`](core/hermes_executor.py).

### P3 — Self-improvement aman
7. **AST sandbox** — tambah validasi `ast.parse()` + `py_compile` + backup `.bak` ke [`core/hermes_remediator.py`](core/hermes_remediator.py) sebelum patch ditulis.
8. **Boot sentry** — port [`core/boot_sentry.py`](../scratch/Brahma-Echo/core/boot_sentry.py) (75 baris, jalan saat import) → anti-brick untuk patch Neira.
9. **Learned rules → prompt injection** — port [`core/learned_rules.py`](../scratch/Brahma-Echo/core/learned_rules.py) ke atas [`shared/memory/user_preferences.json`](shared/memory/user_preferences.json); injeksi ke [`core/prompt.txt`](core/prompt.txt) saat runtime.

### P4 — Ekosistem (nanti)
10. Pertimbangkan **`@playwright/mcp`** untuk [`skills/admin/browser_control.py`](skills/admin/browser_control.py) (a11y tree > koordinat pixel).
11. **Brahma Connect** (Android remote) sebagai fitur masa depan setelah 5-otak stabil.

---

## 6. Peta Jalan yang Diusulkan (setelah PAUSE diangkat)

```
TAHAP A  core/task_queue.py + breadcrumb UI          (P1, ±1 hari)
TAHAP B  BrainHub cooldown + model-pool per otak      (P2, ±1 hari)
TAHAP C  ErrorDecision di hermes_executor             (P2, ±1 hari)
TAHAP D  AST sandbox + boot_sentry di remediator      (P3, ±1 hari)
TAHAP E  learned_rules → prompt injection             (P3, ±0.5 hari)
TAHAP F  lanjut otak 3/4/5 (duck/deepseek/qwen)       (proyek 5-otak, sudah di-pause)
```

Catatan: proyek 5-otak (Dola dkk) tetap **paused** sesuai instruksi; TAHAP A–E adalah adopsi Brahma-Echo yang bisa dikerjakan lebih dulu karena memperkuat fondasi sebelum otak 3/4/5 diisi.

---

## 7. Kesimpulan

Brahma-Echo memang **lebih responsif**, tapi rahasianya bisa dipinjam utuh: (1) pool model + cooldown anti rate-limit, (2) task queue async, (3) agent loop plan→replan dengan keputusan error oleh LLM, (4) self-healing ber-guard AST + boot rollback, (5) umpan balik instan (breadcrumb + SFX + learned rules). Arsitektur skill Neira ([`core/skill_hub.py`](core/skill_hub.py)) dan konsep 5-otak ([`core/brain_hub.py`](core/brain_hub.py)) sudah lebih unggul dari pola if-elif Brahma-Echo — jadi strateginya: **adopsi mekanisme responsivitas & ketahanannya, pertahankan arsitektur kita**.
