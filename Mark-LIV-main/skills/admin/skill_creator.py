# skill_creator.py
"""
skill_creator.py — Neira buat skill BARU langsung dari percakapan.

User bilang "Neira, buatin skill X" → otak (Gemini/Hermes) memanggil skill ini
→ file skill ditulis ke skills/<kategori>/<nama>.py → [SkillHub.ensure_fresh()]
meload-nya otomatis TANPA restart → skill langsung dipakai di kalimat berikutnya.

Dua cara membuat (parameters):
  1. steps  — skill alur: daftar langkah yang memanggil skill lain yang sudah
              ada, urut. Cocok untuk rutinitas ("buka chrome lalu list app").
  2. code   — kode Python lengkap berisi TOOL dict + handler (dipakai otak
              untuk skill berlogika). Divalidasi AST+compile dulu; gagal parse
              = ditolak, tidak ada file rusak.

Perintah (parameters["cmd"]):
  create — buat skill (wajib: name; lalu steps ATAU code; opsional:
           description, category, input_hint, overwrite)
  list   — daftar skill yang pernah saya buat lewat skill ini (+status live)
  delete — hapus skill buatan saya (hanya yang tercatat di ledger — skill
           tulisan tangan TIDAK bisa dihapus lewat sini)
  help   — panduan singkat format code

Keamanan:
  - Nama divalidasi identifier Python; kategori harus folder skills/ yang ada.
  - kode di-validate ast.parse + compile in-memory sebelum ditulis.
  - overwrite hanya boleh untuk file yang MEMANG dibuat skill_creator (ledger).
  - Semua aksi lewat policy gate + audit log + emergency stop (3 gerbang sama
    seperti skill admin lain).
  - Ledger: shared/memory/created_skills.json

Auto-discovered by core/skill_hub.py via TOOL dict — langsung terlihat oleh
kedua otak. Setelah create, SkillHub memuat file baru otomatis (ensure_fresh).
"""
from __future__ import annotations

import ast
import json
import keyword
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    from core.policy_engine import decide as _policy_decide
except Exception:
    _policy_decide = None
try:
    from core.audit_logger import log_event as _audit_log
except Exception:
    def _audit_log(event):                       # type: ignore[misc]
        return False
try:
    from skills.admin.emergency_stop import is_stopped as _estop
except Exception:
    def _estop() -> bool:                        # type: ignore[misc]
        return False


def _base_dir() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    # admin/ -> skills/ -> root (Mark-LIV-main)
    return Path(__file__).resolve().parent.parent.parent


BASE_DIR = _base_dir()
SKILLS_DIR = BASE_DIR / "skills"
LEDGER_PATH = BASE_DIR / "shared" / "memory" / "created_skills.json"

_NAME_RE = re.compile(r"^[a-z_][a-z0-9_]{2,47}$")
_DEFAULT_CATEGORIES = ("admin", "general", "dev", "konten")

_BANNED_NAMES = {
    "skill_creator", "app_manager", "window_manager", "open_app",
    "list_open_windows", "deep_think", "emergency_stop",
    "remote_approval_skill",
}


def _categories() -> List[str]:
    cats = [p.name.lower() for p in SKILLS_DIR.iterdir() if p.is_dir()
            and not p.name.startswith(("_", "."))]
    # Kategori default selalu tersedia — folder dibuat otomatis saat create.
    for d in _DEFAULT_CATEGORIES:
        if d not in cats:
            cats.append(d)
    return cats


def _load_ledger() -> List[dict]:
    try:
        return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_ledger(rows: List[dict]) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(json.dumps(rows, indent=2, ensure_ascii=False),
                           encoding="utf-8")


def _norm_name(raw: str, check_banned: bool = True) -> Tuple[Optional[str], Optional[str]]:
    n = (raw or "").strip().lower().replace("-", "_").replace(" ", "_")
    n = re.sub(r"[^a-z0-9_]", "", n)
    if not n:
        return None, "Nama skill kosong setelah dibersihkan."
    if n[0].isdigit():
        n = "sk_" + n
    if keyword.iskeyword(n):
        n += "_sk"
    if len(n) > 48:
        n = n[:48]
    if not _NAME_RE.match(n):
        return None, (f"Nama '{n}' tidak valid. Pakai 3–48 huruf/angka/garis "
                      "bawah, diawali huruf.")
    if check_banned and n in _BANNED_NAMES:
        return None, f"Nama '{n}' dipakai skill bawaan — pilih nama lain."
    return n, None


def _validate_code(code: str) -> Tuple[Optional[ast.Module], Optional[str]]:
    if not code or not code.strip():
        return None, "Kode kosong."
    if len(code) > 60_000:
        return None, "Kode terlalu besar (maks 60.000 karakter)."
    try:
        tree = ast.parse(code)
    except SyntaxError as e:
        return None, f"Kode gagal parse (baris {e.lineno}): {e.msg}"
    try:
        compile(tree, "<skill_creator>", "exec")
    except Exception as e:
        return None, f"Kode gagal compile: {e}"
    has_tool = any(isinstance(n, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == "TOOL" for t in n.targets)
                   for n in tree.body)
    has_run = any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and
                  n.name == "run" for n in tree.body)
    if not has_tool or not has_run:
        return None, ("Kode wajib punya dict TOOL (berisi name/description/"
                      "parameters) DAN fungsi 'run(parameters, **kwargs)'. "
                      "Panggil cmd=help untuk contoh kerangka.")
    return tree, None


def _steps_template(name: str, desc: str, input_hint: str,
                    steps: List[dict]) -> str:
    tool = {
        "name": name,
        "description": desc or f"Skill alur buatan Neira: {name}.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "input": {"type": "STRING",
                          "description": input_hint or "Input bebas untuk skill ini"}
            },
        },
    }
    header = (
        f"# {name}.py\n"
        f"# Dibuat otomatis oleh Neira (skill_creator) pada "
        f"{time.strftime('%Y-%m-%d %H:%M')}.\n"
        f'"""{desc or name}\n\n'
        "Skill hasil percakapan (auto-generated). Boleh diubah manual;\n"
        "SkillHub memuat ulang otomatis tanpa restart.\n"
        '"""\n'
        "from __future__ import annotations\n\n"
        f"STEPS = {steps!r}\n\n"
        f"TOOL = {tool!r}\n\n\n"
    )
    body = (
        "def run(parameters=None, **kwargs):\n"
        "    params = dict(parameters or {})\n"
        "    params.setdefault('input', '')\n"
        "    from core.skill_hub import skill_hub\n"
        "    lines = []\n"
        "    for i, step in enumerate(STEPS, 1):\n"
        "        skill_name = step.get('skill', '')\n"
        "        step_params = {}\n"
        "        for k, v in (step.get('params') or {}).items():\n"
        "            try:\n"
        "                step_params[k] = v.format_map(params) if isinstance(v, str) else v\n"
        "            except Exception:\n"
        "                step_params[k] = v\n"
        "        rec = skill_hub.get(skill_name)\n"
        "        if not rec or not callable(getattr(rec.handler, '__call__', None)):\n"
        "            lines.append(f'[{i}] GAGAL: skill {skill_name!r} tidak tersedia')\n"
        "            continue\n"
        "        try:\n"
        "            out = rec.handler(step_params)\n"
        "        except Exception as e:\n"
        "            out = f'ERROR: {e}'\n"
        "        lines.append(f'[{i}] {skill_name} > {out}')\n"
        "    return chr(10).join(lines)\n"
    )
    return header + body


def _register_ledger(name: str, category: str, desc: str, kind: str) -> None:
    rows = _load_ledger()
    rows = [r for r in rows if r.get("name") != name]
    rows.insert(0, {
        "name": name,
        "category": category,
        "kind": kind,
        "description": desc,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    })
    _save_ledger(rows)


def _check_gates(action: str, detail: str) -> Optional[str]:
    """Return pesan penolakan atau None bila lolos 3 gerbang."""
    if _estop():
        return "⛔ Emergency stop aktif — skill Creator tidak menjalankan apa pun."
    if _policy_decide is not None:
        try:
            decision = _policy_decide("skill.manage", action)
            if isinstance(decision, dict) and decision.get("decision") == "deny":
                return f"⛔ Ditolak policy: {decision.get('reason', 'skill.manage')}"
        except Exception:
            pass
    return None


def skill_creator(parameters: Dict[str, Any] = None, **kwargs) -> str:
    params = dict(parameters or {})
    cmd = (params.get("cmd") or "help").strip().lower()

    # ── LIST ────────────────────────────────────────────────────────────────
    if cmd == "list":
        rows = _load_ledger()
        if not rows:
            return ("Belum ada skill yang saya buat lewat skill_creator. "
                    "Minta saya: 'buatin skill <nama>' — saya tulis langsung.")
        from core.skill_hub import skill_hub as _hub
        lines = ["🛠️ Skill buatan saya (skill_creator):"]
        for r in rows[:20]:
            live = _hub.has(r["name"])
            status = "✅ live" if live else "❌ tidak termuat"
            lines.append(f"• {r['name']} [{r['category']}/{r['kind']}] — "
                         f"{r.get('description', '')[:60]} — {status}")
        return "\n".join(lines)

    # ── DELETE ──────────────────────────────────────────────────────────────
    if cmd == "delete":
        # Delete tidak pakai cek banned — proteksi cukup lewat ledger:
        # skill bawaan tidak pernah tercatat, jadi pasti ditolak di bawah.
        name, err = _norm_name(params.get("name", ""), check_banned=False)
        if err:
            return f"⚠️ {err}"
        gate = _check_gates("delete", name)
        if gate:
            return gate
        rows = _load_ledger()
        row = next((r for r in rows if r["name"] == name), None)
        if not row:
            return (f"⚠️ Skill '{name}' tidak ada di daftar buatan saya — "
                    "skill tulisan tangan tidak boleh dihapus lewat sini.")
        fpath = SKILLS_DIR / row["category"] / f"{name}.py"
        try:
            if fpath.exists():
                fpath.unlink()
        except Exception as e:
            return f"⚠️ Gagal menghapus file: {e}"
        _save_ledger([r for r in rows if r["name"] != name])
        _audit_log({"event": "skill.manage", "action": "delete",
                    "target": name, "params": {}})
        return (f"🗑️ Skill '{name}' sudah saya hapus. "
                "SkillHub otomatis mencabutnya tanpa restart.")

    # ── HELP ────────────────────────────────────────────────────────────────
    if cmd == "help":
        return (
            "🛠️ Skill Creator — saya bisa menulis skill baru langsung.\n"
            "Cara termudah: sebut nama + langkahnya, contoh:\n"
            "  create {name:'pagi_pintar', steps:[{skill:'open_app',"
            " params:{app:'chrome'}}, {skill:'app_manager', params:{cmd:'list'}}]}\n"
            "Untuk skill berlogika, kirim cmd=create + code berisi kerangka:\n"
            "  TOOL = {'name': 'nama', 'description': '...'}\n"
            "  def run(parameters=None, **kwargs):\n"
            "      return 'hasil'\n"
            "Kategori tersedia: " + ", ".join(_categories())
        )

    # ── CREATE ──────────────────────────────────────────────────────────────
    if cmd == "create":
        name, err = _norm_name(params.get("name", ""))
        if err:
            return f"⚠️ {err}"
        desc = (params.get("description") or "").strip()
        category = (params.get("category") or "general").strip().lower()
        if category not in _categories():
            return (f"⚠️ Kategori '{category}' tidak dikenal. Pakai salah satu: "
                    + ", ".join(_categories()))
        gate = _check_gates("create", name)
        if gate:
            return gate

        cat_dir = SKILLS_DIR / category
        fpath = cat_dir / f"{name}.py"
        overwrite = bool(params.get("overwrite"))
        ledger_names = {r["name"] for r in _load_ledger()}
        if fpath.exists() and not overwrite:
            if name in ledger_names:
                return (f"⚠️ Skill '{name}' sudah ada (buatan saya). Ulangi "
                        "dengan overwrite=true untuk menggantinya.")
            return (f"⚠️ File skills/{category}/{name}.py sudah ada dan bukan "
                    "buatan skill_creator — saya tidak berani menimpanya. "
                    "Pilih nama lain.")
        if fpath.exists() and overwrite and name not in ledger_names:
            return (f"⛔ Menolak menimpa skills/{category}/{name}.py — file itu "
                    "bukan hasil skill_creator.")

        steps = params.get("steps")
        code = params.get("code")
        if steps:
            if not isinstance(steps, list) or not steps:
                return "⚠️ 'steps' harus array berisi minimal 1 langkah."
            norm_steps: List[dict] = []
            for st in steps:
                if not isinstance(st, dict) or not st.get("skill"):
                    return "⚠️ Setiap langkah butuh field 'skill'."
                norm_steps.append({"skill": str(st["skill"]),
                                   "params": st.get("params") or {}})
            content = _steps_template(name, desc,
                                      str(params.get("input_hint") or ""),
                                      norm_steps)
            kind = "steps"
        elif code:
            _, err = _validate_code(code)
            if err:
                return f"⚠️ Kode ditolak — {err}"
            content = code
            kind = "code"
        else:
            return ("⚠️ Saya butuh 'steps' (alur dari skill lain) atau 'code' "
                    "(Python lengkap). Panggil cmd=help untuk format.")

        try:
            cat_dir.mkdir(parents=True, exist_ok=True)
            fpath.write_text(content, encoding="utf-8")
        except Exception as e:
            return f"⚠️ Gagal menulis file skill: {e}"

        _register_ledger(name, category, desc or kind, kind)
        _audit_log({"event": "skill.manage", "action": "create",
                    "target": name,
                    "params": {"category": category, "kind": kind}})
        return (f"✅ Skill '{name}' sudah saya buat di skills/{category}/{name}.py"
                f" (mode {kind}). SkillHub memuatnya otomatis — TANPA restart. "
                f"Sekarang bisa dipanggil: {name}. Minta saya tes bila mau.")

    return ("Perintah skill_creator: cmd=create | list | delete | help. "
            "Contoh: 'Neira, buatin skill buka_chrome_lalu_list'.")


TOOL = {
    "name": "skill_creator",
    "description": ("Buat / daftar / hapus skill baru langsung saat percakapan "
                    "TANPA restart. cmd=create butuh 'name' + ('steps' alur "
                    "dari skill lain ATAU 'code' Python berisi TOOL+run)."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "cmd": {"type": "STRING",
                    "description": "create | list | delete | help"},
            "name": {"type": "STRING", "description": "Nama skill (identifier)"},
            "description": {"type": "STRING", "description": "Deskripsi singkat"},
            "category": {"type": "STRING",
                         "description": "admin | general | dev | konten"},
            "input_hint": {"type": "STRING",
                           "description": "Hint input untuk mode steps"},
            "overwrite": {"type": "BOOLEAN",
                          "description": "Timpa skill buatan skill_creator?"},
            "steps": {"type": "ARRAY",
                      "description": "Mode steps: [{skill, params}] urut"},
            "code": {"type": "STRING",
                     "description": "Mode code: Python lengkap (TOOL + run)"},
        },
        "required": ["cmd"],
    },
    "handler": skill_creator,
}


def run(parameters=None, **kwargs):
    """Alias handler agar ter-discover SkillHub & action_loader."""
    return skill_creator(parameters, **kwargs)
