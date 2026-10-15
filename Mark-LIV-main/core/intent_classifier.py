# intent_classifier.py — Blueprint Tahap 13
"""
Intent Classifier: bedakan NIAT user SEBELUM routing — obrolan santai vs
tugas nyata vs pertanyaan vs perintah stop. Brain tidak perlu menebak.

Aturan (blueprint §6-ish):
- RULE-BASED dulu (cepat, offline, deterministik) — skor kata kunci.
- Jika skor ambigu (< threshold) → opsional LLM fallback (call_llm_text);
  gagal LLM → jujur "unknown" + saran tindakan, BUKAN mengarang intent.
- Stop phrase dicek lebih dulu via emergency_stop.matches_stop_phrase —
  keselamatan mengalahkan semua.

Pemakaian:
    from core.intent_classifier import classify
    r = classify("rapikan desktop ku")
    # {"intent": "task", "confidence": 0.9, "method": "rule", ...}
"""
from __future__ import annotations

import re

try:
    from skills.admin.emergency_stop import matches_stop_phrase as _stop_phrase
except Exception:
    def _stop_phrase(text: str) -> bool:     # type: ignore[misc]
        return False

# ── Pola rule-based (ID + EN) ────────────────────────────────────────────────
# Urutan = prioritas. (intent, pola, skor)

_TASK_PATTERNS = [
    (r"\b(rapikan|rapihin|rapikanlah)\b", 0.6),
    (r"\b(buat|bikin|buatkan|bikinkan)\b", 0.5),
    (r"\b(buka|bukain|jalankan|jalanin|run)\b", 0.5),
    (r"\b(tutup|matikan|close|kill)\b", 0.5),
    (r"\b(hapus|delete|bersihkan|clean)\b", 0.5),
    (r"\b(backup|cadangkan)\b", 0.7),
    (r"\b(kirim|send)\b", 0.5),
    (r"\b(cari|search|cariin)\b", 0.4),
    (r"\b(download|unduh)\b", 0.6),
    (r"\b(install|pasang)\b", 0.6),
    (r"\b(organize|organisir)\b", 0.6),
    (r"\b(screenshot|screen capture)\b", 0.7),
    (r"\b(ketik|type)\b", 0.5),
    (r"\b(jadwal(?:in|kan)?|schedule)\b", 0.6),
    (r"\b(setiap|every)\s+\w+\s*(menit|minute|jam|hour|hari|day)\b", 0.7),
    (r"\b(pukul|jam|at)\s+\d{1,2}[:.]\d{2}\b", 0.5),
    (r"\b(cek|check|scan|analisa|analisis|analyze)\b", 0.4),
    (r"\b(desktop|folder|file|window|aplikasi|app)\b.*\b(buka|rapikan|hapus|tutup|backup)\b", 0.6),
    (r"\b(buka|rapikan|hapus|tutup|backup)\b.*\b(desktop|folder|file|window|aplikasi|app)\b", 0.6),
    (r"\b(run|execute|eksekusi)\b", 0.5),
]

_CHAT_PATTERNS = [
    (r"^\s*(hai|hi|halo|hello|hey|woi|p|pagi|siang|sore|malam)\b", 0.8),
    (r"\b(apa kabar|how are you|gimana kabar)\b", 0.8),
    (r"\b(terima kasih|makasih|thanks|thank you)\b", 0.8),
    (r"\b(kamu bisa apa|bisa apa saja|what can you do)\b", 0.8),
    (r"\b(siapa (kamu|nama kamu)|who are you)\b", 0.7),
    (r"\b(cerita|gimana harimu|bosan)\b", 0.5),
    (r"^\s*(ok|oke|okay|sip|mantap|keren|nice|good)\s*[.!]?\s*$", 0.9),
]

_QUESTION_PATTERNS = [
    (r"\?\s*$", 0.5),                                  # diakhiri tanda tanya
    (r"^\s*(apa|apakah|siapa|kapan|dimana|di mana|kenapa|mengapa|gimana|bagaimana|berapa)\b", 0.6),
    (r"^\s*(what|who|when|where|why|how|which|is|are|do|does|can)\b", 0.5),
    (r"\b((?:kamu|lo|elu|anda)\s+bisa(?:kan)?|bisa(?:kan)?\s+(?:kamu|lo|elu|anda))\b", 0.5),
    (r"\b(berapa|berapa lama|how much|how many)\b", 0.6),
]

AMBIGUOUS_THRESHOLD = 0.5


def _rule_score(text: str) -> tuple[str, float]:
    """Return (intent, skor tertinggi) dari rule-based match."""
    t = (text or "").lower().strip()
    if not t:
        return "unknown", 0.0
    # Sapaan kuat → chat LANGSUNG (meski ada "?" — "apa kabar?" tetap obrolan,
    # jangan kalah sama akumulasi pola question)
    for pat, w in _CHAT_PATTERNS:
        if w >= 0.8 and re.search(pat, t):
            return "chat", w
    best = ("unknown", 0.0)
    for name, group in (("task", _TASK_PATTERNS), ("chat", _CHAT_PATTERNS),
                        ("question", _QUESTION_PATTERNS)):
        score = 0.0
        for pat, w in group:
            if re.search(pat, t):
                score += w
        if score > best[1]:
            best = (name, round(min(score, 1.0), 2))
    return best


_LLM_SYS = ("Kamu pengklasifikasi niat Neira. Balas HANYA SATU kata dari: "
            "task | chat | question. "
            "'task' = perintah melakukan sesuatu di PC. "
            "'chat' = obrolan santai/sapaan. "
            "'question' = pertanyaan informasi.")


def _llm_classify(text: str) -> str:
    try:
        from core.llm_client import call_llm_text
        out = str(call_llm_text(
            f'Niat user: "{text[:200]}"\nBalas SATU kata: task|chat|question',
            system=_LLM_SYS, timeout=20)).strip().lower()
        if out in ("task", "chat", "question"):
            return out
    except Exception:
        pass
    return ""


def classify(text: str, use_llm: bool = True) -> dict:
    """Klasifikasi niat user. Return dict intent/confidence/method/backup."""
    t = str(text or "").strip()
    if not t:
        return {"intent": "unknown", "confidence": 0.0, "method": "rule",
                "is_stop": False, "suggest": "teks kosong"}

    # 1) Keselamatan dulu: stop phrase mengalahkan semuanya
    is_stop = _stop_phrase(t)

    intent, score = _rule_score(t)
    method = "rule"
    if is_stop:
        return {"intent": "stop", "confidence": 1.0, "method": "rule",
                "is_stop": True, "suggest": "jalankan emergency_stop"}

    # 2) Ambigu → LLM fallback (jika boleh & tersedia)
    if score < AMBIGUOUS_THRESHOLD and use_llm:
        llm = _llm_classify(t)
        if llm:
            return {"intent": llm, "confidence": 0.7, "method": "llm",
                    "is_stop": False, "suggest": ""}
        # LLM gagal → jujur ambiguous, sarankan jalur aman
        return {"intent": "unknown", "confidence": score, "method": "rule",
                "is_stop": False,
                "suggest": "tanya user: obrolan atau tugas? (atau perlakukan "
                           "sebagai question — jalur paling aman)"}

    return {"intent": intent, "confidence": score, "method": "rule",
            "is_stop": False, "suggest": ""}


def is_task(text: str) -> bool:
    """Shortcut: niat tugas nyata? (skor ≥ threshold)"""
    return classify(text, use_llm=False).get("intent") == "task"


def fmt_result(r: dict, text: str) -> str:
    icons = {"task": "🛠", "chat": "💬", "question": "❓", "stop": "⛔",
             "unknown": "🤷"}
    icon = icons.get(r.get("intent", "unknown"), "•")
    lines = [f"{icon} Intent: {r.get('intent', '?').upper()} "
             f"(keyakinan {r.get('confidence', 0):.0%}, via {r.get('method', '?')})"]
    if r.get("is_stop"):
        lines.append("Perintah STOP terdeteksi — keselamatan prioritas.")
    if r.get("suggest"):
        lines.append(f"Saran: {r['suggest']}")
    return "\n".join(lines)


# ── Handler TOOL ─────────────────────────────────────────────────────────────

def intent_classifier(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "classify").lower().strip()
    text = str(p.get("text") or "").strip()

    try:
        if cmd == "classify":
            if not text:
                return "Sebutkan teks user. Contoh: {\"cmd\": \"classify\", \"text\": \"rapikan desktop\"}"
            r = classify(text, use_llm=bool(p.get("use_llm", True)))
            return fmt_result(r, text)

        if cmd == "is_task":
            return "YA — tugas nyata." if is_task(text) else "BUKAN — obrolan/pertanyaan/ambigu."

        return ("Intent Classifier — cmd: classify (text) | is_task (text). "
                "Rule-based offline + LLM fallback opsional. Read-only.")
    except Exception as e:
        return f"intent_classifier gagal: {e}"


TOOL = {
    "name": "intent_classifier",
    "description": (
        "Klasifikasi niat user sebelum routing: task (tugas nyata di PC), "
        "chat (obrolan), question (pertanyaan), stop (perintah berhenti), "
        "unknown (ambigu — tanyakan ulang)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING", "description": "classify | is_task"},
            "text": {"type": "STRING", "description": "Teks/niat user"},
            "use_llm": {"type": "BOOLEAN",
                        "description": "Fallback LLM saat ambigu (default true)"},
        },
        "required": [],
    },
    "handler": intent_classifier,
}
