# task_planner.py — Blueprint Tahap 8
"""
Task Planner: terjemahan niat user → daftar langkah JSON yang VALID.

Prinsip blueprint:
- Planner hanya MERANCANG; eksekusi tetap lewat jarvis_orchestrator.run()
  (policy/verify/fallback tetap aktif per langkah — tanpa jalan pintas).
- Sumber kebenaran daftar skill = skill_hub (get_tool_declarations), bukan
  daftar ngarang — skill yang tidak terdaftar otomatis ditolak validasi.
- Kegagalan LLM jujur dilaporkan (anti-bohong): tidak ada plan palsu.

Pemakaian:
    plan(goal)                     → niat → steps (butuh LLM lokal)
    validate(steps)                → cek skill ada + aksi policy dikenal
    fmt_plan(steps)                → teks plan utk user
    execute(goal, steps, confirm)  → jalankan lewat orchestrator
"""
from __future__ import annotations

import json
import re

try:
    from core.llm_client import call_llm_text as _llm_text
except Exception:
    _llm_text = None

try:
    from core.policy_engine import decide as _decide
except Exception:
    _decide = None

try:
    from core import jarvis_orchestrator as _orch
except Exception:
    _orch = None


MAX_STEPS = 10


# ── Katalog skill (compact) ──────────────────────────────────────────────────

def _hub():
    try:
        from core.skill_hub import skill_hub as _h
        return _h
    except Exception:
        return None


def skill_catalog() -> str:
    """Katalog ringkas skill name + deskripsi utk prompt planner."""
    hub = _hub()
    if hub is None:
        return ""
    decls = hub.get_tool_declarations()
    lines = []
    for d in decls:
        props = (d.get("parameters") or {}).get("properties") or {}
        args = ", ".join(props.keys()) if props else "tanpa parameter"
        lines.append(f"- {d['name']}({args}): {d['description'][:90]}")
    return "\n".join(lines)


# ── Parse & validasi ─────────────────────────────────────────────────────────

_PLANNER_SYS = (
    "Kamu task planner Neira. Terjemahkan niat user menjadi LANGKAH-LANGKAH "
    "JSON MURNI tanpa teks lain. Format:\n"
    '{"steps":[{"skill":"<nama skill>","params":{...}}]}\n'
    "Aturan: maksimal 5 langkah, urut logis, hanya skill dari daftar, "
    "params sesuai deskripsi. Jika niat tidak butuh langkah apapun, "
    'balas {"steps":[]}.'
)


def parse_plan_json(text: str) -> list[dict] | None:
    """Ekstrak {"steps":[...]} dari balasan LLM. None = gagal parse (jujur)."""
    if not text:
        return None
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        return None
    steps = data.get("steps") if isinstance(data, dict) else None
    if not isinstance(steps, list):
        return None
    return steps


def _normalize_step(raw) -> dict | None:
    """Satu langkah mentah → dict bersih, atau None jika bentuknya salah."""
    if not isinstance(raw, dict):
        return None
    skill = str(raw.get("skill") or "").strip()
    if not skill:
        return None
    params = raw.get("params") or raw.get("parameters") or {}
    if not isinstance(params, dict):
        params = {}
    step: dict = {"skill": skill, "params": params}
    if raw.get("expect"):
        step["expect"] = str(raw["expect"])[:120]
    if raw.get("policy_action"):
        step["policy_action"] = str(raw["policy_action"]).strip()
    return step


def validate_steps(steps: list) -> tuple[list[dict], list[str]]:
    """Validasi daftar langkah → (steps_bersih, errors).
    Cek: bentuk, jumlah, skill terdaftar di skill_hub, policy_action dikenal."""
    hub = _hub()
    errors: list[str] = []
    clean: list[dict] = []
    if not isinstance(steps, list) or not steps:
        return [], ["plan kosong / bukan daftar"]
    if len(steps) > MAX_STEPS:
        return [], [f"terlalu banyak langkah ({len(steps)} > {MAX_STEPS})"]
    for i, raw in enumerate(steps):
        st = _normalize_step(raw)
        if st is None:
            errors.append(f"langkah {i + 1}: bentuk tidak valid")
            continue
        if hub is not None and not hub.has(st["skill"]):
            errors.append(f"langkah {i + 1}: skill '{st['skill']}' tidak terdaftar")
            continue
        act = st.get("policy_action") or ""
        if act and _decide is not None:
            d = _decide(act)
            # aksi tak terdaftar → reason "tidak terdaftar di policy (default)"
            if "tidak terdaftar" in str(d.get("reason", "")):
                errors.append(f"langkah {i + 1}: policy_action '{act}' tidak dikenal")
                continue
        clean.append(st)
    if not clean and not errors:
        errors.append("tidak ada langkah valid")
    return clean, errors


# ── Plan (LLM) ───────────────────────────────────────────────────────────────

def plan(goal: str) -> tuple[list[dict], str]:
    """Niat → steps. Return (steps, pesan). steps=[] + pesan = jujur gagal."""
    if _llm_text is None:
        return [], "LLM client tidak tersedia — plan tidak bisa dibuat"
    goal = (goal or "").strip()
    if not goal:
        return [], "goal kosong"
    catalog = skill_catalog()
    if not catalog:
        return [], "skill_hub tidak tersedia — tidak ada skill untuk direncanakan"
    prompt = f"# DAFTAR SKILL\n{catalog}\n\n# NIAT USER\n{goal}\n\nBalas JSON langkah saja."
    try:
        raw = _llm_text(prompt, system=_PLANNER_SYS, timeout=90)
    except Exception as e:
        return [], f"LLM gagal: {e}"
    steps = parse_plan_json(raw)
    if steps is None:
        return [], "balasan LLM bukan JSON langkah yang valid"
    clean, errors = validate_steps(steps)
    if errors:
        return clean, "plan LLM ditolak validasi: " + "; ".join(errors[:3])
    return clean, "plan valid"


# ── Formatter ────────────────────────────────────────────────────────────────

def fmt_plan(steps: list[dict]) -> str:
    """Plan dalam bentuk teks yang enak dibaca user."""
    if not steps:
        return "(plan kosong)"
    lines = ["🧭 PLAN (" + str(len(steps)) + " langkah):"]
    for i, st in enumerate(steps, 1):
        params = ", ".join(f"{k}={str(v)[:40]}" for k, v in (st.get("params") or {}).items())
        lines.append(f"  {i}. {st['skill']}({params})")
    return "\n".join(lines)


# ── Execute (satu pintu: orchestrator) ───────────────────────────────────────

def execute(goal: str, steps: list[dict], confirm: bool = False,
            risk_level: str = "medium") -> str:
    """Jalankan plan. TANPA jalan pintas — lewat jarvis_orchestrator.run()."""
    if _orch is None:
        return "failed: orchestrator tidak tersedia"
    clean, errors = validate_steps(steps)
    if errors:
        return "failed: plan tidak valid — " + "; ".join(errors[:3])
    if not clean:
        return "failed: plan kosong setelah validasi"
    return _orch.run(goal=f"[planner] {goal[:150]}", steps=clean,
                     confirm=confirm, risk_level=risk_level)


# ── Handler (TOOL) ───────────────────────────────────────────────────────────

def task_planner(parameters: dict = None, params: dict = None, **kwargs) -> str:
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "help").lower().strip()

    try:
        if cmd == "plan":
            steps, msg = plan(str(p.get("goal") or ""))
            if not steps:
                return f"❌ {msg}"
            return f"✅ {msg}\n{fmt_plan(steps)}\n" \
                   'Jalankan: {"action":"task_planner","cmd":"execute","goal":...,"confirm":true}'

        if cmd == "validate":
            clean, errors = validate_steps(p.get("steps") or [])
            if errors:
                return "❌ Validasi gagal:\n- " + "\n- ".join(errors)
            return "✅ Plan valid:\n" + fmt_plan(clean)

        if cmd == "execute":
            goal = str(p.get("goal") or "tanpa judul")
            steps, errors = validate_steps(p.get("steps") or [])
            if errors:
                return "❌ Plan ditolak: " + "; ".join(errors[:3])
            if not steps:
                return "❌ steps kosong — sertakan langkah yang sudah divalidasi"
            confirm = bool(p.get("confirm"))
            if not confirm:
                return "⚠️ Plan siap dieksekusi:\n" + fmt_plan(steps) + \
                       '\n\nPanggil ulang dengan "confirm": true untuk mengeksekusi.'
            return execute(goal, steps, confirm=True)

        return ("Task Planner — cmd: plan (niat→langkah via LLM) | validate "
                "(cek daftar steps) | execute (jalankan lewat orchestrator, "
                'butuh "confirm": true).')
    except Exception as e:
        return f"task_planner gagal: {e}"


TOOL = {
    "name": "task_planner",
    "description": (
        "Ubah niat user menjadi rencana langkah lalu eksekusi. plan=niat→"
        "langkah (LLM), validate=cek steps, execute=jalankan lewat "
        "orchestrator (policy+verifikasi tetap aktif per langkah, butuh "
        "confirm=true)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "plan | validate | execute (default: help)"},
            "goal": {"type": "STRING", "description": "Niat user, contoh: cek kesehatan repo"},
            "steps": {"type": "ARRAY",
                      "description": "Daftar langkah utk validate/execute: [{skill, params}]"},
            "confirm": {"type": "BOOLEAN",
                        "description": "true untuk benar-benar mengeksekusi plan"},
        },
        "required": [],
    },
    "handler": task_planner,
}
