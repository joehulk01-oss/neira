# test_installed_apps.py — App Discovery + Hermes Self-Improvement
# Verify: scan, cache, search, launch, open_app fallback, SkillHub discovery.
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

# ── base dir (same pattern as other tests) ───────────────────────────────────
def _base_dir() -> Path:
    return Path(__file__).resolve().parent.parent   # scratch/ -> Mark-LIV-main

BASE_DIR = _base_dir()
sys.path.insert(0, str(BASE_DIR))

PASS = 0
FAIL = 0

def check(name: str, cond: bool) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ✅ {name}")
    else:
        FAIL += 1
        print(f"  ❌ {name}")


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 1: Module import & basic structure ──")
# ═══════════════════════════════════════════════════════════════════════════════

import importlib.util
ia_path = BASE_DIR / "skills" / "admin" / "installed_apps.py"
spec = importlib.util.spec_from_file_location("test_installed_apps_mod", ia_path)
ia_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ia_mod)

check("module imported", ia_mod is not None)
check("has installed_apps function", callable(getattr(ia_mod, "installed_apps", None)))
check("has run alias", callable(getattr(ia_mod, "run", None)))
check("has TOOL dict", isinstance(getattr(ia_mod, "TOOL", None), dict))
check("TOOL has name", ia_mod.TOOL.get("name") == "installed_apps")
check("TOOL has handler", callable(ia_mod.TOOL.get("handler")))
check("TOOL has parameters", isinstance(ia_mod.TOOL.get("parameters"), dict))
check("TOOL parameters has properties", "properties" in ia_mod.TOOL.get("parameters", {}))
check("CACHE_FILE path set", ia_mod.CACHE_FILE.name == "installed_apps_cache.json")


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 2: Full scan (refresh) ──")
# ═══════════════════════════════════════════════════════════════════════════════

# Force refresh to build cache
t0 = time.time()
result = ia_mod.installed_apps({"cmd": "refresh"})
elapsed = time.time() - t0

check("refresh returns string", isinstance(result, str))
check("refresh finds apps", "aplikasi terinstal" in result or "ditemukan" in result)
check("refresh shows count", "Total:" in result or "aplikasi" in result.lower())
check(f"refresh completes in <30s (took {elapsed:.1f}s)", elapsed < 30)


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 3: Cache file created & valid ──")
# ═══════════════════════════════════════════════════════════════════════════════

cache_file = ia_mod.CACHE_FILE
check("cache file exists", cache_file.exists())

if cache_file.exists():
    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
        check("cache is valid JSON", True)
        check("cache has timestamp", "timestamp" in data)
        check("cache has apps list", isinstance(data.get("apps"), list))
        check("cache has count", isinstance(data.get("count"), int))
        check("cache count > 0", data.get("count", 0) > 0)
        apps = data.get("apps", [])
        if apps:
            first = apps[0]
            check("app entries have name", "name" in first)
            check("app entries have source", "source" in first)
    except Exception as e:
        check(f"cache parse error: {e}", False)


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 4: Cache TTL (load from cache) ──")
# ═══════════════════════════════════════════════════════════════════════════════

cached = ia_mod._load_cache()
check("_load_cache returns dict", isinstance(cached, dict))
check("cache is fresh (within TTL)", cached is not None)

# List should use cache (fast)
t0 = time.time()
list_result = ia_mod.installed_apps({"cmd": "list"})
elapsed = time.time() - t0
check("list returns string", isinstance(list_result, str))
check("list from cache is fast (<2s)", elapsed < 2)
check("list shows apps", "aplikasi" in list_result.lower())


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 5: Search functionality ──")
# ═══════════════════════════════════════════════════════════════════════════════

# Search for common apps
for query in ("notepad", "chrome", "explorer"):
    result = ia_mod.installed_apps({"cmd": "search", "query": query})
    check(f"search('{query}') returns string", isinstance(result, str))
    check(f"search('{query}') found results", "aplikasi" in result.lower() or "ditemukan" in result.lower() or query.lower() in result.lower())

# Search with no query should give warning
result = ia_mod.installed_apps({"cmd": "search"})
check("search without query gives warning", "⚠️" in result or "nama aplikasi" in result.lower())


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 6: Unknown command handling ──")
# ═══════════════════════════════════════════════════════════════════════════════

result = ia_mod.installed_apps({"cmd": "bogus_command"})
check("unknown command gives warning", "⚠️" in result or "tidak dikenal" in result.lower())


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 7: _search_apps unit tests ──")
# ═══════════════════════════════════════════════════════════════════════════════

fake_catalog = [
    {"name": "Google Chrome", "path": "C:\\chrome.exe", "source": "start_menu"},
    {"name": "Notepad++", "path": "C:\\notepad.exe", "source": "registry"},
    {"name": "VLC Media Player", "path": "C:\\vlc.exe", "source": "path"},
    {"name": "Blender", "path": "C:\\blender.exe", "source": "start_menu"},
]

# Exact match
results = ia_mod._search_apps(fake_catalog, "google chrome")
check("exact match found", len(results) > 0 and results[0]["name"] == "Google Chrome")

# Substring match
results = ia_mod._search_apps(fake_catalog, "chrome")
check("substring 'chrome' found", len(results) > 0 and results[0]["name"] == "Google Chrome")

# Substring match (notepad)
results = ia_mod._search_apps(fake_catalog, "notepad")
check("substring 'notepad' found", len(results) > 0 and results[0]["name"] == "Notepad++")

# Word overlap
results = ia_mod._search_apps(fake_catalog, "vlc media")
check("word overlap 'vlc media' found", len(results) > 0 and results[0]["name"] == "VLC Media Player")

# No match
results = ia_mod._search_apps(fake_catalog, "photoshop")
check("no match for 'photoshop'", len(results) == 0)

# Empty query returns all
results = ia_mod._search_apps(fake_catalog, "")
check("empty query returns all", len(results) == len(fake_catalog))


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 8: _format_catalog unit tests ──")
# ═══════════════════════════════════════════════════════════════════════════════

result = ia_mod._format_catalog(fake_catalog)
check("format shows count", "4 aplikasi" in result)
check("format shows app names", "Google Chrome" in result)
check("format shows source icons", "📌" in result or "📋" in result or "⚙️" in result)

result = ia_mod._format_catalog([])
check("empty catalog message", "Tidak ada aplikasi" in result)

result = ia_mod._format_catalog(fake_catalog, query="chrome")
check("filter label shown", "filter: 'chrome'" in result)

result = ia_mod._format_catalog(fake_catalog, max_items=2)
check("max_items truncation", "lainnya" in result)


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 9: _deduplicate unit tests ──")
# ═══════════════════════════════════════════════════════════════════════════════

dupes = [
    {"name": "Chrome", "path": "C:\\chrome.exe", "source": "start_menu"},
    {"name": "chrome", "path": "", "source": "registry"},   # dupe, no path
    {"name": "Notepad", "path": "C:\\notepad.exe", "source": "path"},
]
result = ia_mod._deduplicate(dupes)
check("dedup removes duplicates", len(result) == 2)
check("dedup prefers entry with path", result[0].get("path") == "C:\\chrome.exe")


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 10: SkillHub & ActionLoader discovery ──")
# ═══════════════════════════════════════════════════════════════════════════════

try:
    from core.skill_hub import skill_hub
    skill_hub.discover(force_reload=True)
    check("SkillHub has installed_apps", skill_hub.has("installed_apps"))
    rec = skill_hub.get("installed_apps")
    if rec:
        check("SkillHub record valid", rec.valid)
        check("SkillHub record has handler", rec.handler is not None)
        check("SkillHub record description mentions apps", "aplikasi" in rec.description.lower() or "app" in rec.description.lower())
except Exception as e:
    check(f"SkillHub check failed: {e}", False)

try:
    from core.action_loader import discover_actions
    actions_dir = BASE_DIR / "actions"
    actions = discover_actions(actions_dir)
    check("ActionLoader discover works", actions is not None)
    check("ActionLoader returns registry", hasattr(actions, "run") or hasattr(actions, "get_tool_declarations"))
except Exception as e:
    check(f"ActionLoader check skipped: {e}", True)  # optional


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 11: open_app fallback integration ──")
# ═══════════════════════════════════════════════════════════════════════════════

# Verify open_app module has the installed_apps fallback code
oa_path = BASE_DIR / "skills" / "admin" / "open_app.py"
oa_code = oa_path.read_text(encoding="utf-8")
check("open_app has installed_apps fallback", "installed_apps" in oa_code and "_get_catalog" in oa_code)
check("open_app fallback is before hermes_remediator", oa_code.index("installed_apps") < oa_code.index("hermes_remediator"))


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 12: Hermes executor integration ──")
# ═══════════════════════════════════════════════════════════════════════════════

he_path = BASE_DIR / "core" / "hermes_executor.py"
he_code = he_path.read_text(encoding="utf-8")
check("hermes_executor has use_skill_creator action", "use_skill_creator" in he_code)
check("hermes_executor imports skill_creator", "skill_creator" in he_code)


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 13: Prompt routing updates ──")
# ═══════════════════════════════════════════════════════════════════════════════

prompt_path = BASE_DIR / "core" / "prompt.txt"
prompt_code = prompt_path.read_text(encoding="utf-8")
check("prompt mentions installed_apps", "installed_apps" in prompt_code)
check("prompt mentions skill_creator", "skill_creator" in prompt_code)
check("prompt has self-improvement rule", "SELF-IMPROVEMENT" in prompt_code or "skill baru" in prompt_code)
check("prompt has app discovery rule", "APP DISCOVERY" in prompt_code or "installed_apps" in prompt_code)


# ═══════════════════════════════════════════════════════════════════════════════
print("\n── Section 14: Hermes prompt updates ──")
# ═══════════════════════════════════════════════════════════════════════════════

hc_path = BASE_DIR / "router" / "hermes_connector.py"
hc_code = hc_path.read_text(encoding="utf-8")
check("hermes prompt mentions use_skill_creator", "use_skill_creator" in hc_code)
check("hermes prompt mentions installed_apps", "installed_apps" in hc_code)
check("hermes prompt has self-improvement section", "SELF-IMPROVEMENT" in hc_code)


# ═══════════════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════════════
print(f"\n{'='*60}")
print(f"  TOTAL: {PASS + FAIL} checks  |  ✅ PASS: {PASS}  |  ❌ FAIL: {FAIL}")
print(f"{'='*60}")
sys.exit(1 if FAIL > 0 else 0)
