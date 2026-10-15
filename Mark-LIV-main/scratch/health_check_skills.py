# health_check_skills.py — Full skill health check
# AST parse every .py in skills/ + actions/, then SkillHub discover, report errors.
import ast
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

PASS = 0
FAIL = 0
errors = []


def check(label, ok, detail=""):
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        print(f"  [FAIL] {label}  {detail}")
        errors.append(f"{label}: {detail}")


# ── 1. AST parse all skill files ──────────────────────────────────────────
print("\n── AST Parse: skills/ ──────────────────────────────────────────")
skills_dir = BASE / "skills"
for py in sorted(skills_dir.rglob("*.py")):
    if py.name.startswith(("_", ".")):
        continue
    rel = py.relative_to(BASE)
    try:
        src = py.read_text(encoding="utf-8")
        ast.parse(src)
        check(str(rel), True)
    except SyntaxError as e:
        check(str(rel), False, f"SyntaxError line {e.lineno}: {e.msg}")
    except Exception as e:
        check(str(rel), False, str(e))

print("\n── AST Parse: actions/ ─────────────────────────────────────────")
actions_dir = BASE / "actions"
if actions_dir.exists():
    for py in sorted(actions_dir.rglob("*.py")):
        if py.name.startswith(("_", ".")):
            continue
        rel = py.relative_to(BASE)
        try:
            src = py.read_text(encoding="utf-8")
            ast.parse(src)
            check(str(rel), True)
        except SyntaxError as e:
            check(str(rel), False, f"SyntaxError line {e.lineno}: {e.msg}")
        except Exception as e:
            check(str(rel), False, str(e))

# ── 2. SkillHub discover ─────────────────────────────────────────────────
print("\n── SkillHub Discovery ──────────────────────────────────────────")
try:
    from core.skill_hub import SkillHub
    hub = SkillHub()
    hub.discover(force_reload=True)

    total = 0
    valid = 0
    invalid_skills = []
    for name, rec in sorted(hub._skills.items()):
        total += 1
        if rec.valid:
            valid += 1
            check(f"skill '{name}' [{rec.category}]", True)
        else:
            invalid_skills.append((name, rec.error or "unknown"))
            check(f"skill '{name}' [{rec.category}]", False, rec.error or "unknown")

    print(f"\n  Hub total: {total} skills, {valid} valid, {total - valid} invalid")
except Exception as e:
    check("SkillHub discover", False, str(e))

# ── 3. action_loader discover ────────────────────────────────────────────
print("\n── ActionLoader Discovery ──────────────────────────────────────")
try:
    from core.action_loader import discover_actions
    registry = discover_actions(actions_dir)
    decls = registry.get_tool_declarations()
    print(f"  Actions loaded: {len(decls)}")
    for d in decls:
        check(f"action '{d['name']}'", True)
except Exception as e:
    check("action_loader discover", False, str(e))

# ── 4. Check TOOL dict presence in skill files ───────────────────────────
print("\n── TOOL/PLUGIN dict check ──────────────────────────────────────")
for py in sorted(skills_dir.rglob("*.py")):
    if py.name.startswith(("_", ".")):
        continue
    rel = py.relative_to(BASE)
    try:
        src = py.read_text(encoding="utf-8")
        tree = ast.parse(src)
        has_tool = any(
            isinstance(n, ast.Assign) and
            any(isinstance(t, ast.Name) and t.id in ("TOOL", "PLUGIN") for t in n.targets)
            for n in tree.body
        )
        has_run = any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run"
            for n in tree.body
        )
        if has_tool and has_run:
            check(f"{rel}: TOOL+run", True)
        elif has_tool:
            check(f"{rel}: TOOL but no run()", False, "missing run() function")
        elif has_run:
            # Some files may have run() without TOOL — check if they have handler in TOOL
            pass  # Not necessarily an error
        else:
            # __init__.py and helper files won't have TOOL — skip silently
            pass
    except Exception:
        pass  # Already caught in AST section

# ── Summary ──────────────────────────────────────────────────────────────
print(f"\n{'=' * 64}")
print(f"TOTAL: {PASS} PASS, {FAIL} FAIL dari {PASS + FAIL} cek")
if errors:
    print(f"\n⚠️  Daftar error:")
    for e in errors:
        print(f"  • {e}")
sys.exit(1 if FAIL else 0)
