"""
Dola AI HTTP client — klien resmi untuk otak Dola (dola.com).

Arsitektur 3 lapis (berdasarkan riset `scratch/dola_research/`):
  1. REPLAY LANGSUNG  : POST /chat/completion dengan cookie akun dari
                        core/dola_pool.py + payload template yang pernah
                        di-sniff (config/dola_payload.json). Tercepat.
  2. SIGNED BROWSER   : fetch() dari DALAM halaman dola.com (headless Edge,
                        cookie akun disuntik via CDP). SDK keamanan situs
                        (byted_acrawler / bdms) menandatangani request secara
                        otomatis — melewati penolakan a_bogus/X-Bogus.
  3. Pesan error jelas: kalau sesi login habis → arahkan ke
                        skill dola_chat(action="setup").

Riset: endpoint /chat/completion, /chat/async/chunk_stream, /chat/new-thread,
plus mode khusus (/chat/search, /chat/write, /chat/translate, /chat/coding,
/chat/music, /chat/create-image, /chat/read-web, /chat/deep-search,
/chat/academic-search, /chat/chat-with-doc, /chat/edu-exercise).

Payload asli per-endpoint TIDAK diajarkan di bundle statis (ada di chunk
malas + dilindungi tanda tangan), jadi bentuk payload asli diambil lewat
workflow sniff (lihat skills/konten/dola_chat.py action="sniff"/"setup").
"""
from __future__ import annotations

import asyncio
import json
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import httpx

from core.dola_pool import DolaAccountPool, dola_pool

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
TEMPLATE_FILE = CONFIG_DIR / "dola_payload.json"

PROMPT_TOKEN = "{{PROMPT}}"
# Teks panduan yang diketik user saat sniff — diganti jadi PROMPT_TOKEN.
SAMPLE_TEXT = "NEIRA-TEST-1"

BASE_URL = "https://www.dola.com"
CHAT_HOME = f"{BASE_URL}/chat/"

# Mode percakapan khusus (endpoint hasil riset find_all_chat_endpoints.py)
MODE_PATHS: Dict[str, str] = {
    "completion": "/chat/completion",
    "search": "/chat/search",
    "deep_search": "/chat/deep-search",
    "write": "/chat/write",
    "translate": "/chat/translate",
    "coding": "/chat/coding",
    "music": "/chat/music",
    "image": "/chat/create-image",
    "read_web": "/chat/read-web",
    "academic": "/chat/academic-search",
    "doc": "/chat/chat-with-doc",
    "edu": "/chat/edu-exercise",
}

_BROWSER_CANDIDATES = (
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
)

_DEFAULT_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Payload cadangan bila belum ada template sniff. Bentuk ini perkiraan —
# jalankan dola_chat(action="setup") sekali untuk mengganti dengan bentuk asli.
def _fallback_payload(prompt: str) -> Dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": prompt, "content_type": "text"}],
        "model": "",
        "skill": "chat",
        "stream": False,
    }


# --------------------------------------------------------------------------- #
# Error
# --------------------------------------------------------------------------- #
class DolaError(Exception):
    """Base error klien Dola."""


class DolaAuthError(DolaError):
    """Sesi login tidak sah / kadaluarsa — akun perlu di-capture ulang."""


class DolaAPIError(DolaError):
    """Request gagal di semua lapis (replay + signed browser)."""


# --------------------------------------------------------------------------- #
# Payload template (hasil sniff)
# --------------------------------------------------------------------------- #
def load_payload_template(path: Optional[Path] = None) -> Optional[Dict[str, Any]]:
    """Muat template payload hasil sniff (config/dola_payload.json)."""
    p = Path(path) if path else TEMPLATE_FILE
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def save_payload_template(record: Dict[str, Any], path: Optional[Path] = None) -> Path:
    """Simpan template payload hasil sniff."""
    p = Path(path) if path else TEMPLATE_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)
    return p


def build_payload(prompt: str, template: Optional[Dict[str, Any]] = None) -> Any:
    """Bangun payload request dari template sniff, ganti PROMPT_TOKEN → prompt.

    - Bila template punya string `{{PROMPT}}` di mana pun (string / nested),
      seluruh kemunculannya diganti dengan teks pertanyaan.
    - Bila token tidak ketemu tapi payload punya `messages` (list), pesan
      user terakhir disuntik.
    - Tanpa template → payload cadangan.
    """
    tpl = template if template is not None else load_payload_template()
    if not tpl or "payload" not in tpl:
        return _fallback_payload(prompt)

    payload = json.loads(json.dumps(tpl["payload"]))  # deep copy aman JSON

    if isinstance(payload, str):
        return payload.replace(PROMPT_TOKEN, prompt).replace(SAMPLE_TEXT, prompt)

    def _swap(node: Any) -> Any:
        if isinstance(node, str):
            return node.replace(PROMPT_TOKEN, prompt).replace(SAMPLE_TEXT, prompt)
        if isinstance(node, list):
            return [_swap(x) for x in node]
        if isinstance(node, dict):
            return {k: _swap(v) for k, v in node.items()}
        return node

    payload = _swap(payload)
    dumped = json.dumps(payload, ensure_ascii=False)
    if PROMPT_TOKEN in dumped or SAMPLE_TEXT in dumped:
        return payload  # swap sudah beres (defensive)

    # Token tidak ada — coba suntik ke messages / prompt / content.
    if isinstance(payload, dict):
        if isinstance(payload.get("messages"), list):
            payload["messages"].append(
                {"role": "user", "content": prompt, "content_type": "text"}
            )
            return payload
        for key in ("prompt", "content", "text", "query"):
            if key in payload and isinstance(payload[key], str):
                payload[key] = prompt
                return payload
    return payload


# --------------------------------------------------------------------------- #
# Parser respons (toleran: bentuk JSON apa pun + SSE)
# --------------------------------------------------------------------------- #
def _extract_text(obj: Any, depth: int = 0) -> str:
    """Cari teks jawaban dari struktur JSON respons yang tidak diketahui bentuknya."""
    if depth > 6:
        return ""
    if isinstance(obj, str):
        return obj.strip()
    if isinstance(obj, (int, float, bool)) or obj is None:
        return ""
    if isinstance(obj, list):
        parts = [t for t in (_extract_text(x, depth + 1) for x in obj) if t]
        return "\n".join(parts)
    if isinstance(obj, dict):
        # OpenAI-style choices
        choices = obj.get("choices")
        if isinstance(choices, list) and choices:
            first = choices[0]
            if isinstance(first, dict):
                msg = first.get("message") or first.get("delta") or first
                t = _extract_text(msg, depth + 1)
                if t:
                    return t
        for key in (
            "reply", "answer", "text", "content", "output",
            "result", "message", "data", "response", "completion",
        ):
            if key in obj:
                t = _extract_text(obj[key], depth + 1)
                if t:
                    return t
    return ""


def _parse_body_text(raw: str) -> str:
    """Ekstrak teks jawaban dari body mentah (JSON atau SSE)."""
    if not raw:
        return ""
    text = raw.strip()
    if text.startswith("data:") or "\ndata:" in text[:200]:
        parts = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if not chunk or chunk == "[DONE]":
                continue
            try:
                obj = json.loads(chunk)
            except Exception:
                parts.append(chunk)
                continue
            t = _extract_text(obj)
            if t:
                parts.append(t)
        if parts:
            return "\n".join(parts)
    try:
        obj = json.loads(text)
    except Exception:
        return text[:8000]
    t = _extract_text(obj)
    return t if t else text[:8000]


def _cookie_header(cookies: Dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in cookies.items())


def _looks_auth_error(status: int, body: str) -> bool:
    if status in (401, 403):
        return True
    low = (body or "").lower()
    return any(m in low for m in ("not login", "unauthorized", "login required", "please login", "session expired"))


# --------------------------------------------------------------------------- #
# Util browser CDP (dipakai fallback signed & skill setup)
# --------------------------------------------------------------------------- #
def find_browser() -> Optional[str]:
    """Cari executable Edge/Chrome di Windows."""
    for cand in _BROWSER_CANDIDATES:
        if Path(cand).exists():
            return cand
    return None


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def wait_page_ws(port: int, timeout: float = 30.0) -> Optional[str]:
    """Tunggu target page muncul di endpoint /json CDP, kembalikan webSocketDebuggerUrl."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"http://127.0.0.1:{port}/json", timeout=1.5)
            if r.status_code == 200:
                targets = r.json()
                for t in targets:
                    if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                        return t["webSocketDebuggerUrl"]
        except Exception:
            pass
        time.sleep(0.5)
    return None


class _CDP:
    """Klien CDP kecil: call() untuk command, pump() untuk menampung event."""

    def __init__(self, ws: Any):
        self.ws = ws
        self._id = 0
        self.events: list = []

    async def call(self, method: str, params: Optional[Dict[str, Any]] = None,
                   timeout: float = 15.0) -> Dict[str, Any]:
        self._id += 1
        mid = self._id
        await self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
            data = json.loads(raw)
            if data.get("id") == mid:
                return data
            if "method" in data:
                self.events.append(data)

    async def pump(self, seconds: float) -> None:
        end = time.time() + seconds
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(self.ws.recv(), timeout=max(0.1, end - time.time()))
            except asyncio.TimeoutError:
                break
            data = json.loads(raw)
            if "method" in data:
                self.events.append(data)

    async def evaluate(self, expression: str, timeout: float = 30.0) -> Any:
        res = await self.call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
            timeout=timeout,
        )
        return res.get("result", {}).get("result", {}).get("value")


_JS_PAGE_FETCH = """(async () => {
  const P = __PAYLOAD__;
  const PATH = __PATH__;
  try {
    const r = await fetch(PATH, {
      method: 'POST', credentials: 'include',
      headers: {'Content-Type': 'application/json',
                'Accept': 'application/json, text/event-stream'},
      body: (typeof P === 'string') ? P : JSON.stringify(P)
    });
    const t = await r.text();
    return JSON.stringify({ok: r.ok, status: r.status, text: t.slice(0, 2000000)});
  } catch (e) { return JSON.stringify({ok: false, status: 0, text: String(e)}); }
})()"""


# --------------------------------------------------------------------------- #
# Klien utama
# --------------------------------------------------------------------------- #
class DolaClient:
    """Klien chat Dola dengan rotasi akun (dola_pool) + fallback browser bertanda tangan."""

    def __init__(self, pool: Optional[DolaAccountPool] = None,
                 session: Optional[httpx.Client] = None,
                 allow_browser_fallback: bool = True):
        self.pool = pool or dola_pool
        self._http = session or httpx.Client(timeout=45.0, follow_redirects=True)
        self.allow_browser_fallback = allow_browser_fallback

    # ---- request headers -------------------------------------------------- #
    def _headers(self, account: Dict[str, Any], template: Optional[Dict[str, Any]]) -> Dict[str, str]:
        headers = {
            "User-Agent": account.get("user_agent") or _DEFAULT_UA,
            "Cookie": _cookie_header(account.get("cookies") or {}),
            "Origin": BASE_URL,
            "Referer": CHAT_HOME,
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
        }
        if template:
            for k, v in (template.get("headers") or {}).items():
                lk = k.lower()
                if lk in ("cookie", "user-agent", "content-type", "content-length"):
                    continue
                headers[k] = v
        return headers

    def _pick_account(self, account_id: Optional[str]) -> Dict[str, Any]:
        if account_id:
            for acc in self.pool.list_accounts():
                if acc.get("id") == account_id:
                    return acc
            raise DolaAuthError(f"Akun '{account_id}' tidak ada di pool.")
        acc = self.pool.get_active_account()
        if not acc:
            raise DolaAuthError(
                "Belum ada akun Dola di pool. Jalankan skill dola_chat(action='setup') "
                "untuk login sekali — cookie akun otomatis disimpan."
            )
        return acc

    # ---- API utama -------------------------------------------------------- #
    def chat(self, prompt: str, mode: str = "completion",
             account_id: Optional[str] = None, timeout: float = 90.0) -> str:
        """Kirim pertanyaan ke Dola, kembalikan teks jawaban.

        Prioritas: replay langsung (cepat) → signed browser fetch (andal).
        """
        if not (prompt or "").strip():
            raise DolaAPIError("Pertanyaan kosong.")
        template = load_payload_template()
        payload = build_payload(prompt, template)
        path = (template or {}).get("path") or MODE_PATHS.get(mode, MODE_PATHS["completion"])

        last_err: Optional[Exception] = None
        tried_ids = set()
        for _ in range(2):  # maks 2 akun berbeda
            account = self._pick_account(account_id if not tried_ids else None)
            tried_ids.add(account.get("id"))
            try:
                text = self._replay(account, path, payload, template, timeout)
                self.pool.report_usage(account.get("id", ""), True)
                return text
            except DolaAuthError as e:
                last_err = e
                self.pool.report_usage(account.get("id", ""), False, str(e))
                if account_id:
                    break  # akun eksplisit — jangan ganti akun
                continue
            except DolaAPIError as e:
                self.pool.report_usage(account.get("id", ""), False, str(e))
                if self.allow_browser_fallback:
                    try:
                        text = self._browser_chat(account, path, payload, timeout)
                        self.pool.report_usage(account.get("id", ""), True)
                        return text
                    except Exception as be:
                        last_err = be
                        continue
                last_err = e
                continue

        raise DolaAPIError(
            f"Chat Dola gagal di semua lapis. Penyebab terakhir: {last_err}"
        )

    def _replay(self, account: Dict[str, Any], path: str, payload: Any,
                template: Optional[Dict[str, Any]], timeout: float) -> str:
        """Lapis 1: POST langsung dengan cookie + template sniff."""
        url = f"{BASE_URL}{path}"
        headers = self._headers(account, template)
        try:
            if isinstance(payload, str):
                resp = self._http.post(url, content=payload.encode("utf-8"),
                                       headers=headers, timeout=timeout)
            else:
                resp = self._http.post(url, json=payload, headers=headers, timeout=timeout)
        except httpx.HTTPError as e:
            raise DolaAPIError(f"Koneksi gagal: {e}") from e

        body = resp.text or ""
        if _looks_auth_error(resp.status_code, body):
            raise DolaAuthError(
                f"Sesi login Dola ditolak (HTTP {resp.status_code}) — jalankan "
                "dola_chat(action='setup') ulang."
            )
        if resp.status_code >= 400:
            raise DolaAPIError(f"HTTP {resp.status_code}: {body[:300]}")

        text = _parse_body_text(body)
        if not text:
            raise DolaAPIError("Respons Dola kosong / bentuk tak dikenal.")
        return text

    def _browser_chat(self, account: Dict[str, Any], path: str, payload: Any,
                      timeout: float) -> str:
        """Lapis 2: fetch() dari dalam halaman dola.com — SDK situs menandatangani request."""
        browser = find_browser()
        if not browser:
            raise DolaAPIError("Edge/Chrome tidak ditemukan untuk fallback browser.")
        port = free_port()
        tmp = tempfile.mkdtemp(prefix="dola_fb_")
        proc = subprocess.Popen(
            [
                browser,
                "--headless=new",
                f"--remote-debugging-port={port}",
                f"--user-data-dir={tmp}",
                "--no-first-run",
                "--no-default-browser-check",
                CHAT_HOME,
            ]
        )
        try:
            return asyncio.run(
                self._browser_chat_async(port, account, path, payload, timeout)
            )
        finally:
            try:
                proc.terminate()
            except Exception:
                pass
            import shutil
            shutil.rmtree(tmp, ignore_errors=True)

    async def _browser_chat_async(self, port: int, account: Dict[str, Any],
                                  path: str, payload: Any, timeout: float) -> str:
        import websockets

        ws_url = wait_page_ws(port, timeout=25.0)
        if not ws_url:
            raise DolaAPIError("Browser CDP tidak siap (timeout).")
        async with websockets.connect(ws_url, max_size=20 * 1024 * 1024) as ws:
            cdp = _CDP(ws)
            await cdp.call("Network.enable")
            await cdp.call("Emulation.setUserAgentOverride",
                           {"userAgent": account.get("user_agent") or _DEFAULT_UA})
            cookies = account.get("cookies") or {}
            await cdp.call("Network.setCookies", {
                "cookies": [
                    {"name": k, "value": v, "url": BASE_URL}
                    for k, v in cookies.items()
                ]
            })
            await cdp.call("Page.enable")
            await cdp.call("Page.navigate", {"url": CHAT_HOME})

            # Tunggu halaman + SDK keamanan siap (maks ~20 dtk).
            ready = False
            for _ in range(20):
                await asyncio.sleep(1.0)
                state = await cdp.evaluate("document.readyState")
                if state == "complete":
                    ready = True
                    break
            if not ready:
                raise DolaAPIError("Halaman chat Dola gagal dimuat.")

            js = _JS_PAGE_FETCH.replace("__PAYLOAD__", json.dumps(payload, ensure_ascii=False)) \
                               .replace("__PATH__", json.dumps(path))
            raw = await cdp.evaluate(js, timeout=timeout)
            if not raw:
                raise DolaAPIError("Fallback browser tidak mengembalikan hasil.")
            data = json.loads(raw)
            if not data.get("ok"):
                status = data.get("status", 0)
                if _looks_auth_error(status, data.get("text", "")):
                    raise DolaAuthError(
                        "Sesi login Dola ditolak di browser — jalankan "
                        "dola_chat(action='setup') ulang."
                    )
                raise DolaAPIError(f"Fetch dalam halaman gagal: {data.get('text', '')[:300]}")
            text = _parse_body_text(data.get("text", ""))
            if not text:
                raise DolaAPIError("Respons Dola kosong / bentuk tak dikenal.")
            return text

    # ---- util akun -------------------------------------------------------- #
    def account_summary(self) -> str:
        accounts = self.pool.list_accounts()
        if not accounts:
            return "Pool akun Dola kosong (jalankan dola_chat action='setup')."
        lines = [f"Akun Dola: {len(accounts)}"]
        for acc in accounts:
            lines.append(
                f"- id={acc.get('id')} nama={acc.get('name')} status={acc.get('status')} "
                f"dipakai={acc.get('usage_count', 0)}x error={acc.get('error_count', 0)}"
            )
        return "\n".join(lines)


# Global instance
dola_client = DolaClient()
