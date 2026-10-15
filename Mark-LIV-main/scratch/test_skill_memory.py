# -*- coding: utf-8 -*-
"""Smoke test — shared skill memory Neira + Hermes (katalog live + routing kategori).

Run: cd Mark-LIV-main && .venv\\Scripts\\python.exe scratch\\test_skill_memory.py
"""
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ok: list[str] = []
fail: list[str] = []


def check(label: str, cond: bool, extra: str = ""):
    (ok if cond else fail).append(label)
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f" — {extra}" if extra and not cond else ""))


# ── 1. SkillHub: katalog + routing map live, semua skill lama+baru ──────────
print("\n== 1. SkillHub live catalog ==")
from core.skill_hub import skill_hub

n = len(skill_hub._skills)
check("hub discovers >= 25 skills", n >= 25, f"got {n}")

cat = skill_hub.get_hermes_catalog()
check("hermes catalog mentions KONTEN", "## Kategori: KONTEN" in cat)
check("hermes catalog mentions ADMIN", "## Kategori: ADMIN" in cat)
check("hermes catalog has web_search", "web_search" in cat)
check("hermes catalog has manage_skills", "manage_skills" in cat)

route = skill_hub.get_routing_guide()
check("routing guide has map header", "SKILL ROUTING MAP" in route)
check("routing guide lists KONTEN skills", "- KONTEN:" in route and "web_search" in route)
check("routing guide lists ADMIN skills", "- ADMIN:" in route and "open_app" in route)
check("routing guide has routing rule", "Routing rule:" in route)

decls = skill_hub.get_tool_declarations()
tagged = [d for d in decls if str(d.get("description", "")).startswith("[")]
check("all hub decls carry [CATEGORY] tag", len(tagged) == len(decls) and len(decls) > 0)

# ── 2. Skill BARU langsung terlihat kedua otak (auto-refresh) ───────────────
print("\n== 2. New skill auto-refresh ==")
# Nama TIDAK boleh diawali '_' — discover() melewati file '_'/'.' secara sengaja.
new_skill = ROOT / "skills" / "konten" / "tmp_probe_skill_zz.py"
new_skill.write_text(
    'TOOL = {\n'
    '    "name": "probe_skill_xyz",\n'
    '    "description": "Probe skill sementara untuk uji memori bersama.",\n'
    '    "parameters": {"type": "object", "properties": {}},\n'
    '    "handler": lambda parameters=None, **kw: "probe ok",\n'
    '}\n',
    encoding="utf-8",
)
try:
    time.sleep(0.05)
    check("new skill visible in hub", skill_hub.has("probe_skill_xyz"))
    cat2 = skill_hub.get_hermes_catalog()
    check("new skill in hermes catalog", "probe_skill_xyz" in cat2)
    route2 = skill_hub.get_routing_guide()
    check("new skill in routing map (KONTEN)", "- KONTEN:" in route2 and "probe_skill_xyz" in route2)
    r = skill_hub.run("probe_skill_xyz", {})
    check("new skill runs via hub", "probe ok" in str(r))
finally:
    new_skill.unlink(missing_ok=True)
time.sleep(0.05)
check("deleted skill disappears (refresh)", not skill_hub.has("probe_skill_xyz"))

# ── 3. ActionRegistry: label kategori di deklarasi Neira ───────────────────
print("\n== 3. ActionRegistry category labels ==")
from core.action_loader import discover_actions

reg = discover_actions(actions_dir=ROOT / "actions", reserved_names=set())
adecls = reg.get_tool_declarations()
check("action decls > 0", len(adecls) > 0)
bad = [d["name"] for d in adecls if not str(d.get("description", "")).startswith("[")]
check("all action decls carry [CATEGORY] tag", not bad, f"missing: {bad[:5]}")
web = next((d for d in adecls if d["name"] == "web_search"), None)
check("web_search tagged [KONTEN]", web is not None and web["description"].startswith("[KONTEN]"),
      web["description"][:30] if web else "not found")
oa = next((d for d in adecls if d["name"] == "open_app"), None)
check("open_app tagged [ADMIN]", oa is not None and oa["description"].startswith("[ADMIN]"),
      oa["description"][:30] if oa else "not found")

# ── 4. Prompt Neira: token {skill_routing} terisi, aturan routing ada ───────
print("\n== 4. Neira prompt routing ==")
from main import _render_prompt, _load_system_prompt, _describe_tools

tpl = _load_system_prompt()
check("prompt template has {skill_routing} token", "{skill_routing}" in tpl)
filled = _render_prompt(tpl, {
    "assistant_name": "Neira", "platform": "Windows 11",
    "capabilities": _describe_tools(adecls),
    "skill_routing": route,
    "limits": "- test",
})
check("prompt fills skill_routing", "SKILL ROUTING MAP" in filled)
check("prompt has category-first rule", "Route by category first" in filled)
check("prompt mentions butuh konten rule", "butuh konten" in filled)
check("capabilities carry [KONTEN] tag", "[KONTEN]" in filled)

# ── 5. Prompt Hermes: aturan routing kategori + katalog penuh ──────────────
print("\n== 5. Hermes prompt routing ==")
import inspect
from router.hermes_connector import HermesConnector

src = inspect.getsource(HermesConnector.process_heavy_task)
check("hermes prompt has KONTEN routing", "KONTEN = content creation" in src)
check("hermes prompt has ADMIN routing", "ADMIN  = system, browser" in src)
check("hermes prompt says butuh konten", "butuh konten" in src)
check("hermes prompt shares library w/ Neira", "SAME" in src and "Neira" in src)
check("hermes_connector imports re (regex fix)", "import re" in inspect.getsource(
    __import__("router.hermes_connector", fromlist=["x"])))

print(f"\nPASS {len(ok)} FAIL {len(fail)}")
if fail:
    print("FAILED:", *fail, sep="\n  - ")
    sys.exit(1)
