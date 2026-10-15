# intent_classifier_skill.py — Blueprint Tahap 13
"""
Wrapper skill utk core/intent_classifier.py — read-only murni, TAPI tetap
3 gerbang (estop → policy intent.classify → audit) supaya pola konsisten
dengan semua skill admin lain.

Pemakaian:
    {"action": "intent_classifier_skill", "cmd": "classify", "text": "rapikan desktop"}
    {"action": "intent_classifier_skill", "cmd": "is_task", "text": "halo apa kabar"}
"""
from __future__ import annotations

try:
    from core import intent_classifier as _ic
except Exception:
    _ic = None
try:
    from core.policy_engine import decide as _decide
except Exception:
    _decide = None
try:
    from core.audit_logger import log_event as _audit
except Exception:
    _audit = None
try:
    from skills.admin.emergency_stop import is_stopped
except Exception:
    def is_stopped() -> bool:            # type: ignore[misc]
        return False


def intent_classifier_skill(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "classify").lower().strip()
    text = str(p.get("text") or "").strip()

    try:
        # 1) Emergency stop (konsistensi pola — read-only tetap dicek)
        if is_stopped():
            return "⛔ EMERGENCY STOP aktif — intent_classifier diblokir."
        # 2) Policy gate
        if _decide is not None:
            d = _decide("intent.classify")
            if d.get("decision") == "deny":
                if _audit:
                    _audit({"skill": "intent_classifier_skill",
                            "action": "intent.classify", "decision": "deny",
                            "result": "denied"})
                return f"⛔ DITOLAK policy: {d.get('reason', '')}"
        # 3) Audit
        if _audit:
            _audit({"skill": "intent_classifier_skill",
                    "action": "intent.classify", "decision": "allow",
                    "result": "success"})

        if _ic is None:
            return "intent_classifier_skill failed: core module tidak tersedia"

        if cmd == "classify":
            if not text:
                return ("Sebutkan teks. Contoh: {\"cmd\": \"classify\", "
                        "\"text\": \"rapikan desktop\"}")
            return _ic.fmt_result(_ic.classify(text, use_llm=bool(p.get("use_llm", True))), text)

        if cmd == "is_task":
            if not text:
                return "Sebutkan teks untuk dicek."
            return "YA — tugas nyata." if _ic.is_task(text) else "BUKAN — obrolan/pertanyaan/ambigu."

        return ("Intent Classifier Skill — cmd: classify | is_task. "
                "Klasifikasi niat user: task/chat/question/stop/unknown. Read-only.")
    except Exception as e:
        return f"intent_classifier_skill gagal: {e}"


TOOL = {
    "name": "intent_classifier_skill",
    "description": (
        "Bedakan niat user sebelum routing: tugas nyata (task), obrolan (chat), "
        "pertanyaan (question), perintah stop, atau ambigu (unknown)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING", "description": "classify | is_task"},
            "text": {"type": "STRING", "description": "Teks user"},
        },
        "required": [],
    },
    "handler": intent_classifier_skill,
}
