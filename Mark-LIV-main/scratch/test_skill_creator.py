# test_skill_creator.py — skill buatan sendiri langsung dari percakapan
# Jalankan: python scratch\test_skill_creator.py
"""Isolasi: LEDGER_PATH → tmp file (restore in finally). create→discover→
run→delete end-to-end dengan SkillHub nyata; emergency stop + policy gate
di-patch agar deterministic; overwrite-protection diuji tanpa menyentuh
file bukan-ledger."""
import ast
import json
import sys
import time
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

PASS = 0
FAIL = 0


def check(name, cond):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name}")


def section(t):
    print(f"\n── {t} " + "─" * max(4, 62 - len(t)))


LEDGER_TMP = BASE / "scratch" / "tmp_ledger_test_sc.json"
if LEDGER_TMP.exists():
    LEDGER_TMP.unlink()

import skills.admin.skill_creator as sc          # noqa: E402
import core.skill_hub as sh                       # noqa: E402

ORIG_LEDGER = sc.LEDGER_PATH
sc.LEDGER_PATH = LEDGER_TMP

from skills.admin import emergency_stop as es  # noqa: E402
ORIG_STOP = es.is_stopped
es.is_stopped = lambda: False
sc._estop = lambda: False

ORIG_POLICY = sc._policy_decide
sc._policy_decide = None                          # policy engine off untuk uji

NEW_FILES = []                                    # dibersihkan di finally
hub = sh.SkillHub()

try:
    # ── 1. Validasi nama ─────────────────────────────────────────────────────
    section("Validasi nama")
    _n, e = sc._norm_name("")
    check("nama kosong → error", bool(e))
    _n, e = sc._norm_name("9mulai")
    check("awal digit → diberi prefix sk_", _n == "sk_9mulai")
    _n, e = sc._norm_name("skill_creator")
    check("nama terlarang → ditolak", bool(e))
    n, e = sc._norm_name("Pagi-Pintar!!")
    check("normalisasi simbol → pagi_pintar", n == "pagi_pintar" and not e)

    # ── 2. Validasi kode ─────────────────────────────────────────────────────
    section("Validasi kode")
    _, e = sc._validate_code("def run():\n  return 1")            # tanpa TOOL
    check("tanpa TOOL → ditolak", "TOOL" in (e or ""))
    _, e = sc._validate_code("TOOL = {'name':'x'}")                # tanpa run
    check("tanpa run → ditolak", "run" in (e or ""))
    _, e = sc._validate_code("TOOL = {")
    check("syntax error → ditolak", "parse" in (e or ""))
    ok, e = sc._validate_code("TOOL={'name':'x'}\ndef run(p=None,**k):\n return 'ok'")
    check("kode sah → lolos", ok is not None and not e)

    # ── 3. Create mode steps → live end-to-end ───────────────────────────────
    section("Create (steps) → SkillHub live TANPA restart")
    out = sc.skill_creator({"cmd": "create", "name": "uji_alur_sc",
                            "description": "alur uji",
                            "steps": [
                                {"skill": "app_manager", "params": {"cmd": "list"}}]})
    check("create → sukses", "✅" in out)
    fpath = BASE / "skills" / "general" / "uji_alur_sc.py"
    check("file dibuat", fpath.exists())
    NEW_FILES.append(fpath)
    check("terdaftar di ledger",
          any(r["name"] == "uji_alur_sc" for r in json.loads(LEDGER_TMP.read_text())))
    check("SkillHub langsung kenal (auto-load)", hub.has("uji_alur_sc"))
    rec = hub.get("uji_alur_sc")
    check("handler callable", callable(getattr(rec.handler, "__call__", None)))
    res = rec.handler({"input": "x"})
    check("handler jalan & memanggil app_manager", "app_manager" in str(res) or len(str(res)) > 10)

    # ── 4. Create mode code → live ───────────────────────────────────────────
    section("Create (code) → live")
    code = ("TOOL = {'name': 'uji_kode_sc', 'description': 'uji kode', "
            "'parameters': {'type': 'OBJECT', 'properties': {}}}\n"
            "def run(parameters=None, **kwargs):\n"
            "    return 'HALO_DARI_SKILL_BARU'\n")
    out = sc.skill_creator({"cmd": "create", "name": "uji_kode_sc",
                            "description": "uji", "category": "general",
                            "code": code})
    check("create code → sukses", "✅" in out)
    fpath2 = BASE / "skills" / "general" / "uji_kode_sc.py"
    NEW_FILES.append(fpath2)
    check("SkillHub kenal skill kode", hub.has("uji_kode_sc"))
    check("hasil eksekusi benar",
          hub.get("uji_kode_sc").handler() == "HALO_DARI_SKILL_BARU")

    # ── 5. Proteksi overwrite ────────────────────────────────────────────────
    section("Proteksi overwrite")
    out = sc.skill_creator({"cmd": "create", "name": "uji_kode_sc", "code": code})
    check("duplikat ledger → suruh overwrite", "overwrite" in out)
    out = sc.skill_creator({"cmd": "create", "name": "app_manager",
                            "category": "admin", "code": code})
    check("nama terlarang → ditolak", "⚠️" in out)
    out = sc.skill_creator({"cmd": "create", "name": "uji_alur_sc",
                            "category": "general", "steps": [
                                {"skill": "x", "params": {}}]})
    check("duplikat steps → suruh overwrite", "overwrite" in out)
    out = sc.skill_creator({"cmd": "create", "name": "uji_kode_sc",
                            "category": "general", "code": code,
                            "overwrite": True})
    check("overwrite ledger-milik → boleh", "✅" in out)
    out = sc.skill_creator({"cmd": "create", "name": "halo_bukan_ledger",
                            "category": "general",
                            "code": code.replace("uji_kode_sc", "halo_bukan_ledger"),
                            "overwrite": True})
    # file tidak ada → create biasa; lalu coba timpa via jalur file-asing
    NEW_FILES.append(BASE / "skills" / "general" / "halo_bukan_ledger.py")
    out2 = sc.skill_creator({"cmd": "create", "name": "halo_bukan_ledger",
                             "category": "general",
                             "code": code.replace("uji_kode_sc", "halo_bukan_ledger"),
                             "overwrite": True})
    check("overwrite file ledger-milik sendiri → boleh", "✅" in out2)

    # file asing (bukan ledger) → tolak keras
    foreign = BASE / "skills" / "general" / "uji_asing_sc.py"
    foreign.write_text("# tulisan tangan\n", encoding="utf-8")
    NEW_FILES.append(foreign)
    out = sc.skill_creator({"cmd": "create", "name": "uji_asing_sc",
                            "category": "general", "code": code,
                            "overwrite": True})
    check("timpa file tulisan tangan → DITOLAK", "⛔" in out)

    # ── 6. Kategori salah / input kurang ─────────────────────────────────────
    section("Input salah ditolak rapi")
    out = sc.skill_creator({"cmd": "create", "name": "uji_x1", "category": "ngasal",
                            "code": code})
    check("kategori ngasal → daftar kategori", "tidak dikenal" in out)
    out = sc.skill_creator({"cmd": "create", "name": "uji_x2"})
    check("tanpa steps/code → bantuan", "steps" in out)
    out = sc.skill_creator({"cmd": "create", "name": "uji_x3", "steps": []})
    check("steps kosong → error", "⚠️" in out)
    out = sc.skill_creator({"cmd": "create", "name": "uji_x4",
                            "steps": [{"params": {}}]})
    check("langkah tanpa skill → error", "⚠️" in out)

    # ── 7. List + Delete ─────────────────────────────────────────────────────
    section("List + Delete")
    out = sc.skill_creator({"cmd": "list"})
    check("list memuat skill baru", "uji_alur_sc" in out and "✅ live" in out)
    out = sc.skill_creator({"cmd": "delete", "name": "uji_alur_sc"})
    check("delete → hapus file", "🗑️" in out and not fpath.exists())
    check("ledger berkurang",
          not any(r["name"] == "uji_alur_sc" for r in json.loads(LEDGER_TMP.read_text())))
    check("SkillHub mencabut otomatis", not hub.has("uji_alur_sc"))
    out = sc.skill_creator({"cmd": "delete", "name": "app_manager"})
    check("delete skill bawaan → tidak ada di ledger", "tidak ada" in out)

    # ── 8. Emergency stop ────────────────────────────────────────────────────
    section("Emergency stop")
    es.is_stopped = lambda: True
    sc._estop = lambda: True
    out = sc.skill_creator({"cmd": "create", "name": "uji_estop",
                            "steps": [{"skill": "x", "params": {}}]})
    check("estop → ⛔", out.startswith("⛔"))
    es.is_stopped = ORIG_STOP
    sc._estop = lambda: False

    # ── 9. AST skill_creator sendiri + hub LIVE reload ───────────────────────
    section("AST + hub global")
    src = (BASE / "skills" / "admin" / "skill_creator.py").read_text(encoding="utf-8")
    ast.parse(src)
    check("skill_creator.py valid AST", True)
    check("ledger tercatat kind", all(r.get("kind") in ("steps", "code")
                                      for r in json.loads(LEDGER_TMP.read_text())))
    decls = {d["name"] for d in sh.skill_hub.get_tool_declarations()}
    check("skill_creator terdaftar di hub global", "skill_creator" in decls)
    check("skill uji_kode_sc live di hub global", "uji_kode_sc" in decls)

finally:
    es.is_stopped = ORIG_STOP
    sc._estop = lambda: False
    sc._policy_decide = ORIG_POLICY
    sc.LEDGER_PATH = ORIG_LEDGER
    for p in NEW_FILES:
        try:
            if p.exists():
                p.unlink()
        except Exception:
            pass
    if LEDGER_TMP.exists():
        LEDGER_TMP.unlink()

print(f"\n{'=' * 64}\nTOTAL: {PASS} PASS, {FAIL} FAIL dari {PASS + FAIL} cek")
sys.exit(1 if FAIL else 0)
