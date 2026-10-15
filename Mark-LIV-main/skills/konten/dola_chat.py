"""
Dola Chat — tanya jawab lewat otak Dola (dola.com) + kelola pool akun.

Dibangun dari riset `scratch/dola_research/` (endpoint /chat/completion,
/chat/async/chunk_stream, /chat/new-thread, mode khusus /chat/search,
/chat/write, /chat/translate, /chat/coding, /chat/music, /chat/create-image,
/chat/read-web, /chat/deep-search, /chat/academic-search, /chat/chat-with-doc,
/chat/edu-exercise).

Aksi:
  chat    : kirim pertanyaan → jawaban (rotasi akun otomatis via core/dola_pool.py).
  setup   : workflow sekali jalan — buka browser, user login, cookie akun disimpan
            ke pool + payload chat ASLI di-sniff otomatis (Network CDP) → template
            disimpan ke config/dola_payload.json.
  sniff   : sniff payload chat saja (akun sudah login di pool) — isi template.
  accounts: lihat / hapus akun di pool.

Endpoint dilindungi SDK keamanan situs (byted_acrawler/bdms) — request polos
pasti ditolak. Karena itu core/dola_client.py memakai 2 lapis: replay template
hasil sniff (cepat) dan fetch dari dalam halaman (SDK menandatangani sendiri).

Auto-discovered oleh core/action_loader.py dan core/skill_hub.py via TOOL dict.
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, List, Optional

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    from core.dola_client import (
        BASE_URL, CHAT_HOME, SAMPLE_TEXT, DolaAPIError, DolaAuthError,
        _CDP, _parse_body_text, dola_client, find_browser, free_port,
        load_payload_template, save_payload_template, wait_page_ws,
    )
    from core.dola_pool import dola_pool
except Exception as _e:  # pragma: no cover - import guard
    dola_client = None
    _IMPORT_ERR = _e
else:
    _IMPORT_ERR = None

_SNIFF_WAIT = 45.0  # detik menunggu user menekan kirim saat sniff


# --------------------------------------------------------------------------- #
# Setup: login + capture cookie + sniff payload
# --------------------------------------------------------------------------- #
async def _setup_async(name: str, headless: bool, sniff: bool) -> str:
    import websockets

    browser = find_browser()
    if not browser:
        return "Edge/Chrome tidak ditemukan — setup butuh browser terpasang."
    port = free_port()
    tmp = tempfile.mkdtemp(prefix="dola_setup_")
    args = [
        browser,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={tmp}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    if headless:
        args.append("--headless=new")
    args.append(CHAT_HOME)
    proc = subprocess.Popen(args)
    log: List[str] = []
    try:
        ws_url = wait_page_ws(port, timeout=30.0)
        if not ws_url:
            return "Browser CDP tidak siap (timeout 30 dtk)."
        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            cdp = _CDP(ws)
            await cdp.call("Network.enable")
            await cdp.call("Page.enable")

            if not headless and sniff:
                log.append(
                    f"Browser terbuka di {CHAT_HOME}. LOGIN (Google/HP/email) lalu "
                    f"ketik pesan '{SAMPLE_TEXT}' dan TEKAN KIRIM. Menunggu request "
                    f"chat tertangkap (maks {int(_SNIFF_WAIT)} dtk)…"
                )
                captured = await _sniff_payload(cdp, _SNIFF_WAIT)
                if captured:
                    path = save_payload_template(captured)
                    log.append(f"Payload chat ASLI tertangkap → template disimpan di {path}.")
                else:
                    log.append(
                        "Payload chat TIDAK tertangkap (mungkin belum login / pesan belum "
                        "terkirim). Template lama tetap dipakai; jalankan action='sniff' "
                        "setelah login berhasil."
                    )
            elif not headless:
                log.append(
                    f"Browser terbuka di {CHAT_HOME}. Silakan LOGIN sampai masuk ke halaman "
                    "chat, lalu balas prompt ini (atau tunggu ~60 dtk) — cookie akan saya ambil."
                )
                await cdp.pump(60.0)
            else:
                await cdp.pump(3.0)

            # Ambil cookie sesi
            res = await cdp.call("Network.getCookies", {"urls": [BASE_URL]})
            cookies = {
                c["name"]: c["value"]
                for c in res.get("result", {}).get("cookies", [])
                if c.get("name")
            }
            if not cookies:
                return "\n".join(log + ["Gagal mengambil cookie (browser belum membuka situs)."])

            ua = await cdp.evaluate("navigator.userAgent") or ""
            session_id = cookies.get("sessionid") or cookies.get("sid_tt") or ""
            if not session_id and not any("token" in k.lower() or "sid" in k.lower() for k in cookies):
                log.append(
                    "PERINGATAN: cookie sesi login tidak terlihat — kemungkinan belum login. "
                    "Akun tetap disimpan, tapi chat bisa ditolak."
                )

            acc = dola_pool.add_account(
                name=name or f"dola_{int(time.time())}",
                cookies=cookies,
                user_agent=ua,
            )
            log.append(
                f"Akun disimpan ke pool: id={acc.get('id')} ({len(cookies)} cookie)."
            )
            return "\n".join(log)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


async def _sniff_payload(cdp: "_CDP", wait: float) -> Optional[Dict[str, Any]]:
    """Pantau Network events sampai request chat POST tertangkap → rekam bentuk payload asli."""
    end = time.time() + wait
    while time.time() < end:
        await cdp.pump(1.0)
        for ev in list(cdp.events):
            if ev.get("method") != "Network.requestWillBeSent":
                continue
            req = ev.get("params", {}).get("request", {})
            url = req.get("url", "")
            method = req.get("method", "")
            if method != "POST":
                continue
            if not any(p in url for p in ("/chat/completion", "/chat/async/chunk_stream",
                                          "/chat/search", "/chat/write", "/chat/translate",
                                          "/chat/coding", "/chat/music", "/chat/create-image")):
                continue
            from urllib.parse import urlparse
            parsed = urlparse(url)
            body = req.get("postData", "") or ""
            try:
                payload: Any = json.loads(body) if body else {}
            except Exception:
                payload = body
            headers = {
                k: v for k, v in (req.get("headers") or {}).items()
                if k.lower() not in ("cookie", "content-length")
            }
            record = {
                "captured_at": time.time(),
                "path": parsed.path,
                "query": parsed.query,
                "method": method,
                "headers": headers,
                "payload": payload,
                "note": f"Hasil sniff otomatis — token teks user diganti {SAMPLE_TEXT} → {{{{PROMPT}}}}.",
            }
            # Ganti teks contoh user jadi token
            dumped = json.dumps(record["payload"], ensure_ascii=False)
            if SAMPLE_TEXT in dumped:
                record["payload"] = json.loads(dumped.replace(SAMPLE_TEXT, "{{PROMPT}}"))
            return record
    return None


# --------------------------------------------------------------------------- #
# Handler skill
# --------------------------------------------------------------------------- #
def dola_chat(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Tanya jawab via Dola AI, atau kelola pool akun (setup/sniff/accounts)."""
    if _IMPORT_ERR is not None:
        return f"Skill dola_chat tidak bisa diimpor: {_IMPORT_ERR}"

    p = parameters or {}
    action = str(p.get("action", "chat")).strip().lower()
    prompt = str(p.get("prompt", "")).strip()
    mode = str(p.get("mode", "completion")).strip().lower()
    account_id = str(p.get("account_id", "")).strip() or None

    try:
        if action == "chat":
            if not prompt:
                return "Butuh 'prompt' (pertanyaan yang mau dikirim ke Dola)."
            return dola_client.chat(prompt, mode=mode, account_id=account_id)

        if action == "setup":
            name = str(p.get("name", "")).strip()
            headless = bool(p.get("headless", False))
            sniff = bool(p.get("sniff", True))
            return asyncio.run(_setup_async(name, headless, sniff))

        if action == "sniff":
            return _sniff_only()

        if action == "accounts":
            target = str(p.get("account_id", "")).strip()
            if target:
                ok = dola_pool.remove_account(target)
                return f"Akun '{target}' dihapus." if ok else f"Akun '{target}' tidak ditemukan."
            return dola_client.account_summary()

        return (
            "Aksi tidak dikenal. Pilihan action: chat | setup | sniff | accounts "
            "(param: prompt, mode, account_id, name, headless, sniff)."
        )
    except DolaAuthError as e:
        return f"[Dola] {e}"
    except DolaAPIError as e:
        return f"[Dola] Gagal: {e}"
    except Exception as e:
        return f"[Dola] Error tak terduga: {e}"


def _sniff_only() -> str:
    """Sniff payload chat dari browser headless dengan cookie pool (tanpa login ulang)."""
    accounts = dola_pool.list_accounts()
    if not accounts:
        return "Pool kosong — jalankan action='setup' dulu (login sekali)."
    acc = accounts[0]
    browser = find_browser()
    if not browser:
        return "Edge/Chrome tidak ditemukan."
    port = free_port()
    tmp = tempfile.mkdtemp(prefix="dola_sniff_")
    proc = subprocess.Popen([
        browser, "--headless=new", f"--remote-debugging-port={port}",
        f"--user-data-dir={tmp}", "--no-first-run", "--no-default-browser-check",
        CHAT_HOME,
    ])
    try:
        result = asyncio.run(_sniff_only_async(port, acc))
        return result
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        shutil.rmtree(tmp, ignore_errors=True)


async def _sniff_only_async(port: int, account: Dict[str, Any]) -> str:
    import websockets
    ws_url = wait_page_ws(port, timeout=25.0)
    if not ws_url:
        return "Browser CDP tidak siap."
    async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
        cdp = _CDP(ws)
        await cdp.call("Network.enable")
        await cdp.call("Network.setCookies", {
            "cookies": [
                {"name": k, "value": v, "url": BASE_URL}
                for k, v in (account.get("cookies") or {}).items()
            ]
        })
        await cdp.call("Page.enable")
        await cdp.call("Page.navigate", {"url": CHAT_HOME})
        for _ in range(15):
            await asyncio.sleep(1.0)
            if await cdp.evaluate("document.readyState") == "complete":
                break
        # Coba kirim pesan contoh lewat UI (teksarea + Enter) supaya request asli muncul
        js_type = (
            "(function(){var t=document.querySelector('textarea');"
            "if(!t)return false;t.focus();"
            f"t.value={json.dumps(SAMPLE_TEXT)};"
            "t.dispatchEvent(new Event('input',{bubbles:true}));return true;})()"
        )
        typed = await cdp.evaluate(js_type)
        if typed:
            await cdp.evaluate(
                "(function(){var t=document.querySelector('textarea');"
                "if(!t)return false;t.dispatchEvent(new KeyboardEvent('keydown',"
                "{key:'Enter',code:'Enter',keyCode:13,bubbles:true}));return true;})()"
            )
        captured = await _sniff_payload(cdp, 20.0)
        if not captured:
            return (
                "Payload chat tidak tertangkap (UI berubah / butuh login). "
                "Jalankan action='setup' dengan sniff=true di browser tampil."
            )
        path = save_payload_template(captured)
        return f"Payload chat tertangkap → template disimpan di {path} (path={captured['path']})."


TOOL: Dict[str, Any] = {
    "name": "dola_chat",
    "description": (
        "Chat with the Dola AI brain (dola.com) using a rotating pool of accounts: "
        "ask a question and get an answer (action=chat, modes: completion/search/"
        "deep_search/write/translate/coding/music/image/read_web/academic/doc/edu). "
        "Also manages accounts: action=setup (one-time login + auto payload sniff), "
        "action=sniff (capture the real chat payload), action=accounts (list/delete)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "chat = tanya jawab; setup = login + simpan akun; sniff = tangkap payload; accounts = lihat/hapus akun.",
                "enum": ["chat", "setup", "sniff", "accounts"],
            },
            "prompt": {"type": "STRING", "description": "Pertanyaan untuk Dola (wajib utk action=chat)."},
            "mode": {
                "type": "STRING",
                "description": "Mode percakapan (default completion).",
                "enum": ["completion", "search", "deep_search", "write", "translate",
                         "coding", "music", "image", "read_web", "academic", "doc", "edu"],
            },
            "account_id": {"type": "STRING", "description": "Pakai akun tertentu (opsional), atau id akun utk dihapus (action=accounts)."},
            "name": {"type": "STRING", "description": "Nama akun saat action=setup."},
            "headless": {"type": "BOOLEAN", "description": "action=setup: true = tanpa jendela browser (tanpa login manual)."},
            "sniff": {"type": "BOOLEAN", "description": "action=setup: true (default) = sekalian sniff payload chat asli."},
        },
        "required": ["action"],
    },
    "handler": dola_chat,
    "behavior": "NON_BLOCKING",
}
