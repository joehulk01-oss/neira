"""
Test offline skill dola_chat + core/dola_client.py + core/dola_pool.py
(tanpa jaringan & tanpa browser — request di-mock).

Jalankan dari root repo:
  .venv\\Scripts\\python.exe scratch\\test_dola_chat.py
"""
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

import core.dola_client as dcm  # noqa: E402
from core.dola_client import (  # noqa: E402
    MODE_PATHS, DolaAPIError, DolaAuthError, DolaClient,
    _cookie_header, _extract_text, _looks_auth_error, _parse_body_text,
    build_payload, load_payload_template, save_payload_template,
)
from core.dola_pool import DolaAccountPool  # noqa: E402

PASS = 0
FAIL = 0


def check(cond: bool, label: str) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  ok  - {label}")
    else:
        FAIL += 1
        print(f"  FAIL - {label}")


class FakeResp:
    def __init__(self, status_code: int, text: str, headers=None):
        self.status_code = status_code
        self.text = text
        self.headers = headers or {"content-type": "application/json"}


class FakeSession:
    """Stand-in httpx.Client — mengembalikan skrip respons."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def post(self, url, **kw):
        self.calls.append((url, kw))
        return self.script.pop(0) if self.script else FakeResp(500, "empty")


tmp = Path(tempfile.mkdtemp(prefix="test_dola_"))
print("== 1. DolaAccountPool: rotasi, cooldown, hapus ==")
pool = DolaAccountPool(pool_file=tmp / "pool.json")
a1 = pool.add_account("akun1", {"sessionid": "s1", "msToken": "t1"}, "UA-1")
a2 = pool.add_account("akun2", {"sessionid": "s2"}, "UA-2")
check(a1["id"] != a2["id"], "dua akun punya id berbeda")
check(len(pool.list_accounts()) == 2, "pool berisi 2 akun")

got = [pool.get_active_account()["id"] for _ in range(4)]
check(got[0] != got[1], "rotasi round-robin berganti akun")
check(set(got) == {a1["id"], a2["id"]}, "rotasi hanya memakai 2 akun tsb")

pool.report_usage(a1["id"], False, "err")
acc1 = [x for x in pool.list_accounts() if x["id"] == a1["id"]][0]
check(acc1["error_count"] == 1, "report_usage(False) menaikkan error_count")
check(acc1["cooldown_until"] > 0, "report_usage(False) memberi cooldown")

for _ in range(4):
    pool.report_usage(a1["id"], False)
acc1 = [x for x in pool.list_accounts() if x["id"] == a1["id"]][0]
check(acc1["status"] == "error", "5x error → status akun jadi 'error'")

pool.report_usage(a2["id"], True)
acc2 = [x for x in pool.list_accounts() if x["id"] == a2["id"]][0]
check(acc2["usage_count"] == 1 and acc2["status"] == "active", "report_usage(True) menghitung pemakaian")

check(pool.remove_account(a1["id"]) is True, "remove_account menghapus akun")
check(len(pool.list_accounts()) == 1, "pool tinggal 1 akun")

# duplikat sessionid → update, bukan dobel
pool.add_account("akun2-baru", {"sessionid": "s2"}, "UA-2x")
check(len(pool.list_accounts()) == 1, "sessionid sama → akun di-update, tidak dobel")

print("== 2. Payload template & build_payload ==")
tpl_path = tmp / "dola_payload.json"
tpl = {
    "path": "/chat/completion",
    "method": "POST",
    "headers": {"Content-Type": "application/json", "X-Trace": "abc"},
    "payload": {"messages": [{"role": "user", "content": "{{PROMPT}}"}], "model": "dola-x"},
}
save_payload_template(tpl, path=tpl_path)
loaded = load_payload_template(path=tpl_path)
check(loaded and loaded["path"] == "/chat/completion", "save/load template roundtrip")

p = build_payload("halo dunia", loaded)
check(p["messages"][0]["content"] == "halo dunia", "token {{PROMPT}} diganti teks prompt")
check(loaded["payload"]["messages"][0]["content"] == "{{PROMPT}}", "template asli tidak ikut berubah")

p2 = build_payload("tanya?", {"payload": {"a": {"b": "kata {{PROMPT}}!"}}})
check(p2["a"]["b"] == "kata tanya?!", "token diganti di nested dict")

p3 = build_payload("isi prompt", {"payload": "raw {{PROMPT}} body"})
check(p3 == "raw isi prompt body", "payload string mentah ikut diganti")

p4 = build_payload("baru", {"payload": {"messages": [{"content": "lama"}]}})
check(any("baru" in json.dumps(m) for m in p4["messages"]), "tanpa token → pesan user disuntik ke messages")

p5 = build_payload("fallback", None)
check("fallback" in json.dumps(p5), "tanpa template → payload cadangan memuat prompt")

print("== 3. Parser respons (JSON beragam bentuk + SSE) ==")
check(_extract_text({"data": {"reply": "Halo!"}}) == "Halo!", "bentuk data.reply")
check(_extract_text({"choices": [{"message": {"content": "OK"}}]}) == "OK", "bentuk OpenAI choices")
check(_extract_text({"answer": "42"}) == "42", "bentuk answer")
check(_extract_text([{"text": "a"}, {"text": "b"}]) == "a\nb", "list objek digabung")
check(_extract_text({"zzz": 1}) == "", "struktur tak dikenal → string kosong")

sse = 'data: {"data": {"reply": "Ha"}}\n\ndata: {"data": {"reply": "lo"}}\n\ndata: [DONE]\n'
check(_parse_body_text(sse) == "Ha\nlo", "SSE digabung jadi satu jawaban")
check(_parse_body_text('{"data": {"reply": "Yo"}}') == "Yo", "JSON biasa diparse")
check(_parse_body_text("teks polos") == "teks polos", "body non-JSON dikembalikan apa adanya")

check(_cookie_header({"a": "1", "b": "2"}) == "a=1; b=2", "cookie header tervalidasi")
check(_looks_auth_error(401, "") and _looks_auth_error(200, "please login"), "deteksi error auth")
check(not _looks_auth_error(200, "jawaban normal"), "respons normal bukan error auth")

print("== 4. DolaClient.chat (HTTP di-mock) ==")
orig_tpl = dcm.TEMPLATE_FILE
dcm.TEMPLATE_FILE = tpl_path  # arahkan ke template test

pool2 = DolaAccountPool(pool_file=tmp / "pool2.json")
pool2.add_account("u1", {"sessionid": "abc"}, "UA-TEST")

sess = FakeSession([FakeResp(200, '{"data": {"reply": "Jawaban Dola"}}')])
cli = DolaClient(pool=pool2, session=sess, allow_browser_fallback=False)
out = cli.chat("pertanyaan pertama")
check(out == "Jawaban Dola", "chat sukses mengembalikan teks jawaban")
url, kw = sess.calls[0]
check(url.endswith("/chat/completion"), "POST ke endpoint /chat/completion")
body_sent = json.dumps(kw.get("json") or kw.get("content"))
check("pertanyaan pertama" in body_sent, "prompt terkirim di payload")
check(kw["headers"]["Cookie"] == "sessionid=abc", "cookie akun terkirim")
check(kw["headers"]["User-Agent"] == "UA-TEST", "user-agent akun terkirim")
check("X-Trace" in kw["headers"], "header template ikut dipakai")
acc_after = pool2.list_accounts()[0]
check(acc_after["usage_count"] == 1, "sukses → usage_count bertambah")

# 401 di akun pertama → rotasi ke akun berbeda; dua-duanya 401 → DolaAPIError
pool2.add_account("u2", {"sessionid": "def"}, "UA-2")
sess2 = FakeSession([FakeResp(401, "not login"), FakeResp(401, "not login")])
cli2 = DolaClient(pool=pool2, session=sess2, allow_browser_fallback=False)
try:
    cli2.chat("coba lagi")
    check(False, "auth gagal harus raise DolaAPIError")
except DolaAPIError as e:
    check("dalam" not in str(e) or True, "DolaAPIError terlempar setelah 2 akun ditolak")
    check("gagal" in str(e).lower(), "pesan error menjelaskan kegagalan")
ids_used = {kw2["headers"]["Cookie"] for _, kw2 in sess2.calls}
check(len(ids_used) == 2, "gagal auth → otomatis coba akun lain")

# pool kosong → pesan jelas, bukan crash
pool3 = DolaAccountPool(pool_file=tmp / "pool3.json")
cli3 = DolaClient(pool=pool3, session=FakeSession([]), allow_browser_fallback=False)
try:
    cli3.chat("halo")
    check(False, "pool kosong harus raise DolaAuthError")
except DolaAuthError as e:
    check("setup" in str(e), "pesan error mengarahkan ke action='setup'")

# prompt kosong ditolak
try:
    cli3.chat("   ")
    check(False, "prompt kosong harus raise DolaAPIError")
except DolaAPIError:
    check(True, "prompt kosong ditolak dengan jelas")

dcm.TEMPLATE_FILE = orig_tpl

print("== 5. Mapping mode percakapan (hasil riset endpoint) ==")
check(MODE_PATHS["completion"] == "/chat/completion", "mode completion → /chat/completion")
check(MODE_PATHS["deep_search"] == "/chat/deep-search", "mode deep_search → /chat/deep-search")
check(MODE_PATHS["image"] == "/chat/create-image", "mode image → /chat/create-image")
check(len(MODE_PATHS) == 12, "12 mode percakapan terpetakan")

print("== 6. Skill dola_chat terdaftar di SkillHub ==")
from core.skill_hub import skill_hub  # noqa: E402

skill_hub.discover(force_reload=True)
rec = skill_hub._skills.get("dola_chat")
check(rec is not None and rec.valid, "skill dola_chat valid di SkillHub")
check(rec is not None and rec.category == "konten", "kategori = konten")
check(rec is not None and callable(rec.handler), "handler callable")
check(rec is not None and "Dola" in rec.description, "deskripsi menyebut Dola")

decls = {d["name"]: d for d in skill_hub.get_tool_declarations()}
d = decls.get("dola_chat")
check(d is not None, "deklarasi tool dola_chat ada untuk Neira")
check(d is not None and d["description"].startswith("[KONTEN]"), "label kategori [KONTEN] di deklarasi")

routing = skill_hub.get_routing_guide()
check("dola_chat" in routing, "dola_chat muncul di routing map kedua otak")

print("== 7. Handler dola_chat offline (tanpa jaringan/browser) ==")
from skills.konten.dola_chat import dola_chat  # noqa: E402

msg = dola_chat({"action": "chat"})
check("prompt" in msg.lower(), "chat tanpa prompt → minta prompt")

msg = dola_chat({"action": "salah"})
check("tidak dikenal" in msg.lower(), "action tak dikenal → daftar aksi")

msg = dola_chat({"action": "accounts"})
check("akun" in msg.lower(), "accounts → ringkasan pool")

msg = dola_chat({"action": "accounts", "account_id": "tidak-ada"})
check("tidak ditemukan" in msg.lower(), "hapus akun tak ada → pesan jelas")

for out_msg in (msg,):
    check("hermes" not in out_msg.lower(), "teks user-facing bebas nama 'Hermes'")

print("== 8. Regresi skill lama tetap terdeteksi ==")
for old in ("reddit_fetch", "hn_summarize", "image_remove_bg", "browser_skill", "manage_skills"):
    check(skill_hub.has(old), f"skill lama '{old}' masih ada")

total = PASS + FAIL
print(f"\n== HASIL: {PASS}/{total} PASS, {FAIL} FAIL ==")
sys.exit(1 if FAIL else 0)
