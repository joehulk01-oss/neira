# context_engine.py — Blueprint Tahap 10 (§5.4)
"""
Context Engine: SATU modul yang merangkai semua sumber konteks Neira menjadi
satu blok teks siap-prompt dengan token budget — menggantikan rangkaian
manual yang tersebar di main.py.

Sumber (semua read-only):
- computer_awareness.awareness_text()  → kondisi PC saat ini
- metrics.format_stats()               → metrik anti-bohong
- memory.recent_tasks_for_prompt()     → tugas nyata yang pernah dieksekusi
- memory.search_memory(query)          → memori relevan dgn niat user
- memory.format_sessions_block()       → riwayat sesi multi-hari

Aturan:
- Budget total default 4000 char (≈ PROMPT_CORE_CHARS lama), dibagi proporsional
- Setiap seksi dipotong di batasnya — total TIDAK PERNAH melebihi budget
- Jujur: seksi gagal dilaporkan "(tidak tersedia)" di report, bukan diam-diam
"""
from __future__ import annotations

try:
    from core.audit_logger import log_event as _audit
except Exception:
    _audit = None

DEFAULT_BUDGET = 4000

# (nama, proporsi budget, pengambil data)
# query dipakai utk memori; bagian lain abaikan.
_SECTIONS = [
    ("awareness", 0.30, lambda q: _awareness()),
    ("tasks", 0.25, lambda q: _tasks()),
    ("memory", 0.25, lambda q: _memory(q)),
    ("sessions", 0.10, lambda q: _sessions()),
    ("metrics", 0.10, lambda q: _metrics()),
]


# ── Pengambil per sumber (aman, jujur gagal) ─────────────────────────────────

def _awareness() -> str:
    try:
        from core.computer_awareness import awareness_text
        return awareness_text()
    except Exception as e:
        return f"(tidak tersedia: {e})"


def _tasks() -> str:
    try:
        from memory.memory_manager import recent_tasks_for_prompt
        return recent_tasks_for_prompt() or "(belum ada riwayat tugas)"
    except Exception as e:
        return f"(tidak tersedia: {e})"


def _memory(query: str) -> str:
    try:
        from memory.memory_manager import search_memory
        q = (query or "").strip()
        if not q:
            from memory.memory_manager import format_memory_for_prompt, load_memory
            return format_memory_for_prompt(load_memory())
        return search_memory(q)
    except Exception as e:
        return f"(tidak tersedia: {e})"


def _sessions() -> str:
    try:
        from memory.memory_manager import format_sessions_block, load_memory
        mem = load_memory()
        sessions = (mem.get("sessions") or []) if isinstance(mem, dict) else []
        if not sessions:
            return "(belum ada sesi tercatat)"
        return format_sessions_block(sessions)
    except Exception as e:
        return f"(tidak tersedia: {e})"


def _metrics() -> str:
    try:
        from core.metrics import format_stats
        return format_stats()
    except Exception as e:
        return f"(tidak tersedia: {e})"


# ── Pemotong aman (jangan putus di tengah baris) ────────────────────────────

_SUFFIX = "\n…(dipotong agar muat budget)"


def _clip(text: str, limit: int) -> str:
    text = str(text or "").strip()
    if len(text) <= limit:
        return text
    # Suffix ikut dihitung — hasil TIDAK PERNAH melebihi limit.
    budget = max(1, limit - len(_SUFFIX))
    cut = text[:budget]
    nl = cut.rfind("\n")
    if nl > budget * 0.6:
        cut = cut[:nl]
    return cut + _SUFFIX


# ── Bangun konteks ───────────────────────────────────────────────────────────

def build(query: str = "", max_chars: int = DEFAULT_BUDGET) -> tuple[str, dict]:
    """Rangkai konteks. Return (teks, report). Total ≤ max_chars selalu."""
    try:
        max_chars = max(600, int(max_chars))
    except Exception:
        max_chars = DEFAULT_BUDGET

    parts: list[str] = []
    report: dict = {"total_chars": 0, "budget": max_chars, "sections": {}}
    used = 0

    for name, ratio, getter in _SECTIONS:
        limit = int(max_chars * ratio)
        try:
            raw = getter(query)
        except Exception as e:
            raw = f"(tidak tersedia: {e})"
        raw = str(raw or "")
        ok = not raw.startswith("(tidak tersedia")
        body = _clip(raw, limit) if ok else raw
        header = {"awareness": "KONDISI PC", "tasks": "TUGAS TERAKHIR",
                  "memory": "MEMORI RELEVAN", "sessions": "SESI SEBELUMNYA",
                  "metrics": "METRIK SISTEM"}[name]
        section = f"=== {header} ===\n{body}"
        parts.append(section)
        used += len(section)
        report["sections"][name] = {
            "included": ok, "chars": len(section), "budget": limit,
        }

    text = "\n\n".join(parts)
    # Garansi keras: total tak boleh tembus budget
    if len(text) > max_chars:
        text = _clip(text, max_chars)
    report["total_chars"] = len(text)
    return text, report


def format_report(report: dict) -> str:
    """Report dict → teks ringkas utk user/otak."""
    lines = [f"Konteks {report['total_chars']}/{report['budget']} char:"]
    for name, info in report["sections"].items():
        status = "ok" if info["included"] else "GAGAL"
        lines.append(f"  - {name}: {info['chars']} char [{status}]")
    return "\n".join(lines)


# ── Handler (TOOL) ───────────────────────────────────────────────────────────

def context_engine(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "build").lower().strip()

    try:
        if cmd == "build":
            text, report = build(str(p.get("query") or ""),
                                 max_chars=p.get("max_chars") or DEFAULT_BUDGET)
            if _audit:
                _audit({"skill": "context_engine", "action": "context.build",
                        "result": "success", "total_chars": report["total_chars"]})
            return text + f"\n\n---\n{format_report(report)}"

        if cmd == "stats":
            text, report = build("", max_chars=600)
            return format_report(report)

        return ("Context Engine — cmd: build (rangkai konteks siap-prompt, "
                "opsional query + max_chars) | stats (ringkasan seksi). "
                "Read-only.")
    except Exception as e:
        return f"context_engine gagal: {e}"


TOOL = {
    "name": "context_engine",
    "description": (
        "Rangkai kondisi PC + metrik + tugas terakhir + memori relevan + "
        "sesi sebelumnya menjadi satu blok konteks siap-prompt dengan token "
        "budget. Read-only."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING", "description": "build | stats (default: build)"},
            "query": {"type": "STRING",
                      "description": "Niat user utk memilih memori relevan"},
            "max_chars": {"type": "INTEGER",
                          "description": "Budget total karakter (default 4000, min 600)"},
        },
        "required": [],
    },
    "handler": context_engine,
}
