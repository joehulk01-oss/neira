# workflow_engine.py
"""
workflow_engine.py — Workflow multi-langkah dari YAML (Blueprint Tahap 6).

Workflow = rangkaian steps yang DISIMPAN (bukan dirakit tiap kali) dan
dieksekusi lewat jalur yang SAMA dengan task biasa: jarvis_orchestrator.run()
→ policy gate → skill_hub → verifikasi expect → fallback self-healing.

Jadi tidak ada pintu pintas: workflow hanyalah "task panjang yang sudah
ditulis di muka" — keamanan tetap per langkah.

Struktur YAML:
    name: morning_briefing
    description: Ringkasan pagi hari
    risk_level: low            # default job risk_level (bisa dinaikkan)
    steps:
      - skill: computer_awareness
        params: {cmd: snapshot}
        policy_action: awareness.snapshot
        expect: "snapshot"     # opsional — verifikasi anti-bohong Tahap 4

Pemakaian dari Hermes/model:
    {"action": "workflow_manager", "cmd": "list"}
    {"action": "workflow_manager", "cmd": "show", "name": "morning_briefing"}
    {"action": "workflow_manager", "cmd": "run", "name": "morning_briefing"}
"""
from __future__ import annotations

from pathlib import Path

try:
    import yaml as _yaml
except Exception:
    _yaml = None

try:
    from core import jarvis_orchestrator as _orch
except Exception:
    _orch = None

WORKFLOW_DIR = Path(__file__).resolve().parent.parent / "workflows"


def _load_yaml(path: Path) -> dict:
    """Parse satu file workflow YAML → dict. Raise ValueError bila tidak valid."""
    if _yaml is None:
        raise RuntimeError("pyyaml tidak terpasang (pip install pyyaml)")
    raw = _yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"{path.name}: YAML root harus dict")
    name = str(raw.get("name") or "").strip()
    if not name:
        raise ValueError(f"{path.name}: field 'name' wajib")
    steps = raw.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError(f"{path.name}: 'steps' wajib berupa list non-kosong")
    for i, s in enumerate(steps):
        if not isinstance(s, dict) or not str(s.get("skill") or "").strip():
            raise ValueError(f"{path.name}: steps[{i}] butuh field 'skill'")
    return raw


def load(name: str) -> dict | None:
    """Muat workflow berdasar nama (tanpa / tanpa .yaml). None jika tidak ada."""
    name = (name or "").strip().strip("/").lower()
    if name.endswith(".yaml") or name.endswith(".yml"):
        name = name.rsplit(".", 1)[0]
    if not name or "/" in name or "\\" in name or ".." in name:
        return None                          # path traversal diblokir
    for ext in (".yaml", ".yml"):
        p = WORKFLOW_DIR / f"{name}{ext}"
        if p.exists():
            try:
                return _load_yaml(p)
            except Exception:
                return None
    return None


def list_workflows() -> list[dict]:
    """Semua workflow valid di workflows/. Return [{name, description, steps}]."""
    out: list[dict] = []
    if not WORKFLOW_DIR.exists():
        return out
    for p in sorted(WORKFLOW_DIR.glob("*.y*ml")):
        try:
            wf = _load_yaml(p)
            out.append({
                "name": wf["name"],
                "description": str(wf.get("description") or ""),
                "steps": len(wf["steps"]),
            })
        except Exception:
            continue                        # file rusak diabaikan, jangan crash
    return out


def fmt_list(items: list[dict]) -> str:
    if not items:
        return ("Belum ada workflow di workflows/. Contoh minimal:\n"
                "name: my_flow\nsteps:\n  - skill: computer_awareness\n    params: {cmd: snapshot}")
    lines = ["📋 Workflow tersedia:"]
    for w in items:
        lines.append(f"  • {w['name']} — {w['steps']} langkah"
                     + (f" — {w['description']}" if w['description'] else ""))
    return "\n".join(lines)


def fmt_show(wf: dict) -> str:
    lines = [f"🧾 {wf['name']}"
             + (f" — {wf.get('description')}" if wf.get("description") else ""),
             f"   risk_level: {wf.get('risk_level') or 'medium'}"]
    for i, s in enumerate(wf["steps"], 1):
        skill = s.get("skill")
        params = s.get("params") or {}
        expect = s.get("expect")
        act = s.get("policy_action") or ""
        line = f"   {i}. {skill}  params={params}"
        if act:
            line += f"  [{act}]"
        if expect:
            line += f"  expect='{expect}'"
        lines.append(line)
    return "\n".join(lines)


def run(name: str, confirm: bool = False) -> str:
    """Eksekusi workflow via orchestrator.run() — satu pintu eksekusi tetap."""
    if _orch is None:
        return "workflow failed: orchestrator tidak tersedia"
    try:
        wf = load(name)
    except Exception as e:
        return f"workflow failed: {e}"
    if wf is None:
        items = list_workflows()
        names = ", ".join(w["name"] for w in items) or "—"
        return f"⚠️ Workflow '{name}' tidak ditemukan. Tersedia: {names}"
    steps = []
    for s in wf["steps"]:
        st = {"skill": str(s["skill"]), "params": dict(s.get("params") or {})}
        if s.get("policy_action"):
            st["policy_action"] = str(s["policy_action"])
        if s.get("expect"):
            st["expect"] = str(s["expect"])
        steps.append(st)
    goal = f"[workflow:{wf['name']}] {wf.get('description') or wf['name']}"
    return _orch.run(goal, steps,
                     risk_level=str(wf.get("risk_level") or "medium"),
                     confirm=confirm)


# ── Tool declaration (auto-discovered kedua otak) ────────────────────────────
def workflow_engine(parameters: dict = None, params: dict = None, **kwargs) -> str:
    """Handler read-only: list | show. Eksekusi tetap lewat workflow_manager."""
    p = parameters if isinstance(parameters, dict) else (params or {})
    cmd = str(p.get("cmd") or "list").lower().strip()
    try:
        if cmd == "list":
            return fmt_list(list_workflows())
        if cmd == "show":
            wf = load(p.get("name", ""))
            if wf is None:
                return (f"⚠️ Workflow '{p.get('name', '')}' tidak ditemukan.\n"
                        + fmt_list(list_workflows()))
            return fmt_show(wf)
        return "cmd tidak dikenal. Gunakan: list | show"
    except Exception as e:
        return f"workflow_engine gagal: {e}"


TOOL = {
    "name": "workflow_engine",
    "description": (
        "Lihat workflow tersimpan: daftar (list) atau detail langkah (show). "
        "Eksekusi workflow lewat workflow_manager (cmd=run) — butuh konfirmasi."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING", "description": "list | show (default: list)"},
            "name": {"type": "STRING", "description": "Nama workflow (untuk show)"},
        },
        "required": [],
    },
    "handler": workflow_engine,
}
