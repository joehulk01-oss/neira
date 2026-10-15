# -*- coding: utf-8 -*-
"""
Test adopsi Brahma-Echo ke Neira (offline, hermetic — semua file state diarahkan
ke direktori temporary lewat monkeypatch).

Cek:
  1. core/task_queue.py       — submit non-blocking, prioritas, cancel, gagal, on_complete
  2. core/brain_hub.py        — cooldown rate-limit per otak + fallback + anti-lockout
  3. core/hermes_remediator.py + core/boot_sentry.py — sandbox AST, backup, rollback,
     pemulihan boot setelah crash-setelah-patch
  4. core/learned_rules.py    — add/dedup/toggle/delete + injeksi prompt
  5. Wiring main.py + py_compile semua file yang diubah

Jalankan:  .venv\\Scripts\\python.exe scratch\\test_brahma_adoptions.py
"""
import sys
import time
import threading
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))


def wait_status(q, tid, want, timeout=6.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        st = q.get_status(tid)
        if st and st["status"] == want:
            return st
        if st and want == "completed" and st["status"] in ("failed", "cancelled"):
            return st
        time.sleep(0.02)
    return q.get_status(tid)


# =========================================================================== #
print("== 1. core/task_queue.py — antrean tugas async ==")
# =========================================================================== #
from core.task_queue import TaskQueue, TaskPriority, get_queue  # noqa: E402

q = TaskQueue(max_concurrent=1)

# submit non-blocking (tugas lambat tetap balik cepat)
slow_done = []


def slow_fn(cancel):
    time.sleep(1.0)
    slow_done.append(True)
    return "hasil-lambat"


t0 = time.time()
tid_slow = q.submit(slow_fn, label="tugas lambat")
elapsed = time.time() - t0
check("submit() non-blocking (balik < 0.3s)", elapsed < 0.3, f"{elapsed:.2f}s")
check("submit() memberi task_id", isinstance(tid_slow, str) and len(tid_slow) == 8)
q.start()  # worker q harus hidup supaya tugas lambat benar-benar dieksekusi

# prioritas: HIGH dulu, lalu NORMAL, lalu LOW (submit sebelum start)
order = []


def mk(label, delay=0.02):
    def fn(cancel):
        order.append(label)
        time.sleep(delay)
        return label
    return fn


q2 = TaskQueue(max_concurrent=1)
q2.submit(mk("low"), label="low", priority=TaskPriority.LOW)
q2.submit(mk("high"), label="high", priority=TaskPriority.HIGH)
q2.submit(mk("norm"), label="norm", priority=TaskPriority.NORMAL)
q2.start()
t0 = time.time()
while len(order) < 3 and time.time() - t0 < 6:
    time.sleep(0.02)
check("urutan prioritas HIGH > NORMAL > LOW", order == ["high", "norm", "low"], str(order))

# on_complete callback
cb_result = {}
tid_cb = q2.submit(lambda cancel: "ok-bro", label="cb",
                   on_complete=lambda tid, res: cb_result.update({"tid": tid, "res": res}))
st = wait_status(q2, tid_cb, "completed")
check("status completed + result tersimpan",
      st and st["status"] == "completed" and st["result"] == "ok-bro", str(st))
check("on_complete dipanggil dengan hasil",
      cb_result.get("res") == "ok-bro" and cb_result.get("tid") == tid_cb, str(cb_result))

# cancel
cancel_cb = {"called": False}


def long_fn(cancel):
    t0 = time.time()
    while not cancel.is_set() and time.time() - t0 < 5:
        time.sleep(0.02)
    return "selesai"


tid_c = q2.submit(long_fn, label="panjang",
                  on_complete=lambda tid, res: cancel_cb.update(called=True))
time.sleep(0.1)
ok_cancel = q2.cancel(tid_c)
st = wait_status(q2, tid_c, "cancelled")
check("cancel() mengembalikan True", ok_cancel is True)
check("status jadi cancelled", st and st["status"] == "cancelled", str(st))
check("on_complete TIDAK dipanggil saat batal", cancel_cb["called"] is False)

# gagal
def boom_fn(cancel):
    raise RuntimeError("boom-x")


tid_f = q2.submit(boom_fn, label="gagal")
st = wait_status(q2, tid_f, "failed")
check("tugas gagal → status failed + error tercatat",
      st and st["status"] == "failed" and "boom-x" in (st["error"] or ""), str(st))

all_st = q2.get_all_statuses()
check("get_all_statuses() berisi semua tugas", len(all_st) >= 4, str(len(all_st)))
check("pending_count() callable", isinstance(q2.pending_count(), int))

tid_missing = q2.cancel("tidaktidak")
check("cancel id palsu → False", tid_missing is False)
check("get_status id palsu → None", q2.get_status("tidaktidak") is None)

st = wait_status(q, tid_slow, "completed")
check("tugas lambat pertama tetap selesai", st and st["status"] == "completed", str(st))
q.stop()
q2.stop()
check("get_queue() singleton hidup", get_queue() is get_queue())

# =========================================================================== #
print("== 2. core/brain_hub.py — cooldown rate-limit per otak ==")
# =========================================================================== #
import core.brain_hub as bh  # noqa: E402
from core.brain_hub import Brain, BrainError, BrainHub, BrainNotReady  # noqa: E402

hub = BrainHub()
calls = {"a": 0, "b": 0, "c": 0}


def a_fail(prompt):
    calls["a"] += 1
    raise BrainError("429 rate-limited (pura-pura)")


def b_ok(prompt):
    calls["b"] += 1
    return "jawaban-dari-b"


def c_not_ready(prompt):
    calls["c"] += 1
    raise BrainNotReady("konektor belum ada")


hub.register(Brain(key="a", label="A", ask_fn=a_fail))
hub.register(Brain(key="b", label="B", ask_fn=b_ok))
hub.register(Brain(key="c", label="C", ask_fn=c_not_ready))

# rantai dikontrol test: a gagal → fallback ke b
# (ROUTE_MAP/_KEYWORDS dikosongkan supaya konektor asli TIDAK tersentuh)
_old_chain = bh._DEFAULT_CHAIN
_old_route = bh.ROUTE_MAP
_old_kw = bh._KEYWORDS
bh._DEFAULT_CHAIN = ["a", "b", "c"]
bh.ROUTE_MAP = {}
bh._KEYWORDS = {}
try:
    r1 = hub.ask_best("halo")
    check("fallback: otak a gagal → dijawab otak b",
          r1.get("answer") == "jawaban-dari-b" and r1.get("brain") == "b", str(r1))
    check("attempts mencatat kegagalan a", any(t.startswith("a:") for t in r1.get("attempts", [])),
          str(r1.get("attempts")))

    check("otak a masuk cooldown setelah gagal", hub.is_rate_limited("a") is True)

    calls["b"] = 0
    r2 = hub.ask_best("halo lagi")
    check("otak cooldown dilewati (a tidak dipanggil ulang)", calls["a"] == 1, str(calls))
    check("catatan attempts menyebut cooldown",
          any("cooldown" in t for t in r2.get("attempts", [])), str(r2.get("attempts")))
    check("otak b tetap menjawab", r2.get("answer") == "jawaban-dari-b")

    # BrainNotReady TIDAK di-cooldown
    hub.ask_best  # noqa
    hub2 = BrainHub()
    hub2.register(Brain(key="c", label="C", ask_fn=c_not_ready))
    bh._DEFAULT_CHAIN = ["c"]
    r3 = hub2.ask_best("tes")
    check("BrainNotReady tidak membuat cooldown",
          hub2.is_rate_limited("c") is False and r3.get("answer") == "", str(r3))

    # anti-lockout: semua otak cooldown tetap dicoba
    bh._DEFAULT_CHAIN = ["a", "b"]
    hub.mark_rate_limited("a")
    hub.mark_rate_limited("b")
    before_a = calls["a"]
    r4 = hub.ask_best("tes lockout")
    check("anti-lockout: semua cooldown tetap dicoba",
          calls["a"] > before_a and r4.get("answer") == "jawaban-dari-b", str(r4))

    # force=True mengabaikan cooldown
    hub.clear_rate_limited("a")
    hub.mark_rate_limited("a")
    before_a = calls["a"]
    r5 = hub.ask_best("tes force", force=True)
    check("force=True mengabaikan cooldown", calls["a"] > before_a, str(calls))

    # clear saat sukses + kedaluwarsa cooldown
    hub.clear_rate_limited("a")
    check("clear_rate_limited() menghapus cooldown", hub.is_rate_limited("a") is False)
    hub.mark_rate_limited("a")
    hub._rate_limited["a"] = time.time() - (bh.RATE_LIMIT_COOLDOWN + 5)
    check("cooldown kedaluwarsa otomatis", hub.is_rate_limited("a") is False)

    # status_report menandai cooldown
    hub.mark_rate_limited("b")
    report = hub.status_report()
    check("status_report menandai otak cooldown",
          "cooldown" in report and "B" in report, report[:200])
    hub.clear_rate_limited("b")

    # force flag tidak merusak API lama (tanpa argumen tetap jalan)
    bh._DEFAULT_CHAIN = ["b"]
    r6 = hub.ask_best("halo")
    check("API lama ask_best(prompt) tetap jalan", r6.get("answer") == "jawaban-dari-b", str(r6))
finally:
    bh._DEFAULT_CHAIN = _old_chain
    bh.ROUTE_MAP = _old_route
    bh._KEYWORDS = _old_kw

# =========================================================================== #
print("== 3. Patch sandbox + boot_sentry — anti-brick ==")
# =========================================================================== #
import core.hermes_remediator as hr  # noqa: E402
import core.boot_sentry as bs  # noqa: E402

tmp = Path(tempfile.mkdtemp(prefix="neira_test_"))
try:
    # monkeypatch path state boot_sentry ke temp (hermetic)
    bs.CRASH_LOG = tmp / "FATAL_CRASH.log"
    bs.CRASH_ARCHIVE = tmp / "FATAL_CRASH_RECOVERED.log"
    bs.PATCH_HISTORY_FILE = tmp / "patch_history.json"

    ok, err = hr.validate_code("x = 1\ny = x + 1\n")
    check("validate_code menerima kode valid", ok is True, str(err))
    ok, err = hr.validate_code("def broken(:\n    pass\n")
    check("validate_code menolak sintaks rusak", ok is False and err, str(err))

    # immune file ditolak
    immune_target = tmp / "boot_sentry.py"
    res = hr.apply_patch_safely(immune_target, "print('hi')\n", patch_id="p-immune")
    check("file immune ditolak", res["success"] is False and "immune" in res["detail"], str(res))

    # kode invalid ditolak — file tidak tersentuh
    target = tmp / "mod.py"
    target.write_text("OLD = 1\n", encoding="utf-8")
    res = hr.apply_patch_safely(target, "def rusak(:\n", patch_id="p-bad")
    check("kode invalid ditolak sebelum menyentuh disk",
          res["success"] is False and target.read_text(encoding="utf-8") == "OLD = 1\n", str(res))

    # patch valid: backup .bak + tulis atomik + riwayat
    res = hr.apply_patch_safely(target, "NEW = 2\n", patch_id="p-good")
    bak = tmp / "mod.py.bak"
    check("patch valid diterapkan", res["success"] is True, str(res))
    check("isi file = kode baru", target.read_text(encoding="utf-8") == "NEW = 2\n")
    check("backup .bak berisi kode lama",
          bak.exists() and bak.read_text(encoding="utf-8") == "OLD = 1\n")
    history = bs.load_patch_history()
    check("riwayat patch mencatat p-good (status applied)",
          any(h.get("patch_id") == "p-good" and h.get("status") == "applied" for h in history),
          str(history))

    # rollback manual per patch_id
    res = hr.rollback_patch("p-good")
    check("rollback_patch() sukses", res["success"] is True, str(res))
    check("file kembali ke kode lama", target.read_text(encoding="utf-8") == "OLD = 1\n")
    history = bs.load_patch_history()
    check("riwayat ditandai rolled_back",
          any(h.get("patch_id") == "p-good" and h.get("status") == "rolled_back" for h in history),
          str(history))

    # skenario boot sentry: patch → crash → boot berikutnya auto-rollback
    res = hr.apply_patch_safely(target, "NEWR = 3\n", patch_id="p-crash")
    check("patch p-crash diterapkan", res["success"] is True, str(res))
    bs.mark_crash("Traceback (pura-pura): RuntimeError: crash setelah patch")
    check("crash log tertulis", bs.CRASH_LOG.exists())
    recovered = bs.check_and_recover_on_boot()
    check("check_and_recover_on_boot() melakukan rollback", recovered is True)
    check("file dipulihkan ke isi sebelum patch",
          target.read_text(encoding="utf-8") == "OLD = 1\n")
    check("crash log diarsipkan",
          not bs.CRASH_LOG.exists() and bs.CRASH_ARCHIVE.exists())
    history = bs.load_patch_history()
    check("riwayat ditandai rolled_back_on_boot",
          any(h.get("patch_id") == "p-crash" and h.get("status") == "rolled_back_on_boot"
              for h in history), str(history))

    # tanpa crash log → tidak ada rollback
    check("tanpa crash log → tidak ada pemulihan",
          bs.check_and_recover_on_boot() is False)
finally:
    shutil.rmtree(tmp, ignore_errors=True)

# =========================================================================== #
print("== 4. core/learned_rules.py — aturan belajar + injeksi prompt ==")
# =========================================================================== #
import core.learned_rules as lr  # noqa: E402

tmp2 = Path(tempfile.mkdtemp(prefix="neira_rules_"))
try:
    lr.RULES_FILE = tmp2 / "learned_rules.json"

    res = lr.learned_rules.add_rule("jawab selalu singkat dan to the point", category="habit")
    check("add_rule sukses", res.get("success") is True, str(res))
    res2 = lr.learned_rules.add_rule("jawab selalu singkat dan to the point")
    check("rule duplikat didedup (tidak dobel)",
          res2.get("success") is True and len(lr.learned_rules.list_rules()) == 1, str(res2))

    lr.learned_rules.add_rule("sebut user 'Mark'", category="general")
    check("dua aturan tersimpan", len(lr.learned_rules.list_rules()) == 2)

    inj = lr.learned_rules.get_prompt_injections()
    check("injeksi prompt memuat semua aturan aktif",
          "singkat" in inj and "Mark" in inj and "PREFERENSI USER" in inj, inj[:120])

    rid = lr.learned_rules.list_rules()[0]["id"]
    lr.learned_rules.toggle_rule(rid)
    inj2 = lr.learned_rules.get_prompt_injections()
    check("rule nonaktif tidak ikut diinjeksi",
          "singkat" not in inj2 and "Mark" in inj2, inj2[:120])
    lr.learned_rules.toggle_rule(rid)
    check("toggle balik → aktif lagi", "singkat" in lr.learned_rules.get_prompt_injections())

    ok_del = lr.learned_rules.delete_rule(rid)
    check("delete_rule menghapus",
          ok_del.get("success") is True and len(lr.learned_rules.list_rules()) == 1)
    check("hapus id palsu → gagal", lr.learned_rules.delete_rule("xyz")["success"] is False)
    check("rule kosong ditolak", lr.learned_rules.add_rule("   ")["success"] is False)

    # kosong = injeksi string kosong (aman ditambahkan ke prompt)
    for r in list(lr.learned_rules.list_rules()):
        lr.learned_rules.delete_rule(r["id"])
    check("tanpa aturan → injeksi kosong", lr.learned_rules.get_prompt_injections() == "")
finally:
    shutil.rmtree(tmp2, ignore_errors=True)

# =========================================================================== #
print("== 5. Wiring main.py + py_compile ==")
# =========================================================================== #
import py_compile  # noqa: E402

main_src = (ROOT / "main.py").read_text(encoding="utf-8", errors="replace")
check("main.py memanggil boot_sentry saat startup", "from core import boot_sentry" in main_src)
check("main.py menandai crash fatal", "boot_sentry.mark_crash" in main_src)
check("main.py menginjeksi learned rules ke prompt",
      "learned_rules.get_prompt_injections()" in main_src)

for rel in [
    "main.py",
    "core/task_queue.py",
    "core/brain_hub.py",
    "core/boot_sentry.py",
    "core/learned_rules.py",
    "core/hermes_remediator.py",
]:
    try:
        py_compile.compile(str(ROOT / rel), doraise=True)
        check(f"py_compile {rel}", True)
    except Exception as e:
        check(f"py_compile {rel}", False, str(e))

# import bersih semua modul adopsi
for mod in ("core.task_queue", "core.brain_hub", "core.boot_sentry",
            "core.learned_rules", "core.hermes_remediator"):
    try:
        __import__(mod)
        check(f"import {mod}", True)
    except Exception as e:
        check(f"import {mod}", False, str(e))

# =========================================================================== #
print(f"\n=== HASIL: {PASS} PASS / {FAIL} FAIL ===")
sys.exit(1 if FAIL else 0)
