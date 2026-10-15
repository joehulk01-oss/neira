# test_otak.py — Otak Dola: brain skill Neira terhubung ke chat.dola.com
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  - {name}")
    else:
        FAIL += 1
        print(f"  FAIL - {name}")


# ── 1. Module import & AST ──────────────────────────────────────────────────
print("== 1. Module import & AST ==")
import ast
otak_path = ROOT / "skills" / "konten" / "otak.py"
check("otak.py exists", otak_path.exists())
try:
    ast.parse(otak_path.read_text(encoding="utf-8"))
    check("otak.py AST valid", True)
except SyntaxError as e:
    check(f"otak.py AST valid (err: {e})", False)

import importlib.util as _ilu
spec = _ilu.spec_from_file_location("_neira_otak_test", otak_path)
otak_mod = _ilu.module_from_spec(spec)
spec.loader.exec_module(otak_mod)
check("otak module loads", otak_mod is not None)

# ── 2. TOOL dict structure ──────────────────────────────────────────────────
print("== 2. TOOL dict structure ==")
TOOL = getattr(otak_mod, "TOOL", None)
check("TOOL dict exists", TOOL is not None)
check("TOOL has name", TOOL and TOOL.get("name") == "otak")
check("TOOL has description", TOOL and len(TOOL.get("description", "")) > 20)
check("TOOL has parameters", TOOL and "parameters" in TOOL)
check("TOOL has handler", TOOL and callable(TOOL.get("handler")))
check("TOOL has run alias", hasattr(otak_mod, "run") and callable(otak_mod.run))
params = TOOL.get("parameters", {})
props = params.get("properties", {})
check("TOOL has action param", "action" in props)
check("TOOL has prompt param", "prompt" in props)
check("TOOL has mode param", "mode" in props)
check("action enum has ask", "ask" in props.get("action", {}).get("enum", []))
check("action enum has setup", "setup" in props.get("action", {}).get("enum", []))
check("action enum has status", "status" in props.get("action", {}).get("enum", []))
check("action enum has modes", "modes" in props.get("action", {}).get("enum", []))

# ── 3. DOLA_MODES ───────────────────────────────────────────────────────────
print("== 3. DOLA_MODES ==")
DOLA_MODES = otak_mod.DOLA_MODES
check("DOLA_MODES has 12 modes", len(DOLA_MODES) == 12)
check("completion mode exists", "completion" in DOLA_MODES)
check("search mode exists", "search" in DOLA_MODES)
check("deep_search mode exists", "deep_search" in DOLA_MODES)
check("write mode exists", "write" in DOLA_MODES)
check("translate mode exists", "translate" in DOLA_MODES)
check("coding mode exists", "coding" in DOLA_MODES)
check("music mode exists", "music" in DOLA_MODES)
check("image mode exists", "image" in DOLA_MODES)
check("read_web mode exists", "read_web" in DOLA_MODES)
check("academic mode exists", "academic" in DOLA_MODES)
check("doc mode exists", "doc" in DOLA_MODES)
check("edu mode exists", "edu" in DOLA_MODES)

# ── 4. _detect_mode ─────────────────────────────────────────────────────────
print("== 4. _detect_mode ==")
_detect = otak_mod._detect_mode
check("default mode = completion", _detect("halo apa kabar") == "completion")
check("search detected", _detect("cari harga laptop terbaru") == "search")
check("write detected", _detect("tulis artikel tentang AI") == "write")
check("translate detected", _detect("terjemah ini ke bahasa inggris") == "translate")
check("coding detected", _detect("debug kode python ini") == "coding")
check("music detected", _detect("cari lirik lagu indonesia") in ("music", "search"))
check("image detected", _detect("buat gambar ilustrasi pemandangan") == "image")
check("deep_search detected", _detect("riset mendalam tentang ekonomi") == "deep_search")

# ── 5. otak() action=status ─────────────────────────────────────────────────
print("== 5. otak() action=status ==")
result = otak_mod.otak({"action": "status"})
check("status returns string", isinstance(result, str))
check("status mentions akun", "akun" in result.lower() or "Akun" in result)
check("status mentions template", "template" in result.lower() or "Template" in result)
check("status mentions mode", "mode" in result.lower() or "Mode" in result)

# ── 6. otak() action=modes ──────────────────────────────────────────────────
print("== 6. otak() action=modes ==")
result = otak_mod.otak({"action": "modes"})
check("modes returns string", isinstance(result, str))
check("modes lists completion", "completion" in result)
check("modes lists search", "search" in result)
check("modes lists translate", "translate" in result)
check("modes lists 12 modes", result.count("- ") >= 12 or "12" in result)

# ── 7. otak() action=ask (no prompt) ────────────────────────────────────────
print("== 7. otak() action=ask (no prompt) ==")
result = otak_mod.otak({"action": "ask"})
check("ask without prompt returns error", "prompt" in result.lower() or "butuh" in result.lower())

# ── 8. otak() unknown action ────────────────────────────────────────────────
print("== 8. otak() unknown action ==")
result = otak_mod.otak({"action": "nonexistent"})
check("unknown action returns help", "action" in result.lower() or "aksi" in result.lower())

# ── 9. config/dola_payload.json exists & valid ──────────────────────────────
print("== 9. config/dola_payload.json ==")
payload_path = ROOT / "config" / "dola_payload.json"
check("dola_payload.json exists", payload_path.exists())
try:
    tpl = json.loads(payload_path.read_text(encoding="utf-8"))
    check("dola_payload.json valid JSON", True)
    check("template has path", "path" in tpl)
    check("template has payload", "payload" in tpl)
    check("template has {{PROMPT}} token", "{{PROMPT}}" in json.dumps(tpl))
except Exception as e:
    check(f"dola_payload.json valid JSON (err: {e})", False)

# ── 10. config/dola_pool.json exists ────────────────────────────────────────
print("== 10. config/dola_pool.json ==")
pool_path = ROOT / "config" / "dola_pool.json"
check("dola_pool.json exists", pool_path.exists())

# ── 11. brain_router.py Dola integration ────────────────────────────────────
print("== 11. brain_router.py Dola integration ==")
br_path = ROOT / "router" / "brain_router.py"
br_src = br_path.read_text(encoding="utf-8")
check("brain_router has DOLA_KEYWORDS", "DOLA_KEYWORDS" in br_src)
check("brain_router has _ask_dola", "_ask_dola" in br_src)
check("brain_router routes to DOLA", '"DOLA"' in br_src)
check("brain_router has Dola fallback", "Dola encountered an error" in br_src or "Dola" in br_src)

# ── 12. brain_hub.py mode auto-detect ───────────────────────────────────────
print("== 12. brain_hub.py mode auto-detect ==")
bh_path = ROOT / "core" / "brain_hub.py"
bh_src = bh_path.read_text(encoding="utf-8")
check("brain_hub has _detect_dola_mode", "_detect_dola_mode" in bh_src)
check("brain_hub _dola_ask uses mode", "mode=mode" in bh_src or "mode=" in bh_src)

# ── 13. prompt.txt routing ──────────────────────────────────────────────────
print("== 13. prompt.txt routing ==")
prompt_src = (ROOT / "core" / "prompt.txt").read_text(encoding="utf-8")
check("prompt.txt mentions otak", "otak" in prompt_src)
check("prompt.txt mentions OTAK DOLA", "OTAK DOLA" in prompt_src)
check("prompt.txt mentions otak(action=ask)", "otak(action=ask)" in prompt_src or "otak (action=ask)" in prompt_src)

# ── 14. SkillHub discovers otak ─────────────────────────────────────────────
print("== 14. SkillHub discovers otak ==")
try:
    from core.skill_hub import SkillHub
    hub = SkillHub(skills_dir=ROOT / "skills")
    hub.discover(force_reload=True)
    check("SkillHub discovers otak", hub.has("otak"))
    rec = hub.get("otak")
    check("otak record exists", rec is not None)
    check("otak record has fields", rec is not None and hasattr(rec, "name"))
except Exception as e:
    check(f"SkillHub discovers otak (err: {e})", False)

# ── 15. ActionLoader discovers otak ─────────────────────────────────────────
print("== 15. ActionLoader discovers otak ==")
try:
    from core.action_loader import discover_actions
    actions = discover_actions(ROOT / "skills")
    check("ActionLoader discover works", actions is not None)
    decls = actions.get_tool_declarations()
    names = [d.get("name") for d in decls]
    check("ActionLoader finds otak", "otak" in names)
except Exception as e:
    check(f"ActionLoader discovers otak (err: {e})", False)

# ── 16. brain_hub skill (skills/konten/brain_hub.py) ────────────────────────
print("== 16. brain_hub skill ==")
bh_skill_path = ROOT / "skills" / "konten" / "brain_hub.py"
check("brain_hub skill exists", bh_skill_path.exists())
bh_skill_src = bh_skill_path.read_text(encoding="utf-8")
check("brain_hub skill has TOOL", "TOOL" in bh_skill_src)
check("brain_hub skill has handler", "handler" in bh_skill_src)

# ── 17. dola_client.py MODE_PATHS ───────────────────────────────────────────
print("== 17. dola_client.py MODE_PATHS ==")
try:
    from core.dola_client import MODE_PATHS
    check("MODE_PATHS has 12 modes", len(MODE_PATHS) == 12)
    check("completion → /chat/completion", MODE_PATHS.get("completion") == "/chat/completion")
    check("search → /chat/search", MODE_PATHS.get("search") == "/chat/search")
    check("translate → /chat/translate", MODE_PATHS.get("translate") == "/chat/translate")
    check("image → /chat/create-image", MODE_PATHS.get("image") == "/chat/create-image")
except Exception as e:
    check(f"MODE_PATHS import (err: {e})", False)

# ── 18. dola_pool.py ────────────────────────────────────────────────────────
print("== 18. dola_pool.py ==")
try:
    from core.dola_pool import DolaAccountPool, dola_pool
    check("DolaAccountPool importable", True)
    check("dola_pool singleton exists", dola_pool is not None)
    check("dola_pool has list_accounts", hasattr(dola_pool, "list_accounts"))
    check("dola_pool has get_active_account", hasattr(dola_pool, "get_active_account"))
except Exception as e:
    check(f"dola_pool import (err: {e})", False)

# ── 19. build_payload with default template ─────────────────────────────────
print("== 19. build_payload with default template ==")
try:
    from core.dola_client import build_payload, load_payload_template
    tpl = load_payload_template()
    check("load_payload_template returns dict", tpl is not None)
    p = build_payload("test prompt otak", tpl)
    check("build_payload returns payload", p is not None)
    check("prompt injected into payload", "test prompt otak" in json.dumps(p))
except Exception as e:
    check(f"build_payload (err: {e})", False)

# ── Summary ─────────────────────────────────────────────────────────────────
print(f"\n{'='*50}")
print(f"TOTAL: {PASS + FAIL} | PASS: {PASS} | FAIL: {FAIL}")
if FAIL == 0:
    print("ALL TESTS PASSED ✅")
else:
    print(f"❌ {FAIL} TEST(S) FAILED")
sys.exit(1 if FAIL else 0)
