"""
Reddit Fetch — ambil konten Reddit via API JSON-nya.

Diadaptasi dari skill `reddit-fetch` repo github.com/ykdojo/claude-code-tips.
Repo aslinya pakai "DuckDuckGo-hop" lewat Playwright karena curl kena 403;
di sini dicoba bertingkat: UA browser + www.reddit.com → old.reddit.com →
kalau semua 403, JATUH ke sesi browser Playwright milik skill browser_control
(buka halaman reddit.com dulu, lalu fetch() .json dari dalam halaman —
cookie & sesi sah dipakai, persis strategi hop pada repo aslinya tapi otomatis).

Auto-discovered oleh core/action_loader.py dan core/skill_hub.py via TOOL dict.
"""
from __future__ import annotations

import html
import json
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": _UA,
    "Accept": "application/json",
}
_TIMEOUT = 10
_LIMIT = 15
_MAX_BODY = 300


def _looks_json(text: str) -> bool:
    """True bila body halaman berupa teks JSON mentah (bukan HTML aplikasi)."""
    return bool(text) and text.lstrip()[:1] in ("{", "[")


_JS_FETCH = """async (u) => {
    try {
        const r = await fetch(u, {credentials: 'include',
            headers: {'Accept': 'application/json'}});
        const t = await r.text();
        return {ok: r.ok, status: r.status, text: t.slice(0, 2000000)};
    } catch (e) { return {ok: false, status: 0, text: String(e)}; }
}"""


def _browser_try(urls: List[str]) -> Tuple[Optional[Any], str]:
    """Fallback: ambil JSON dari dalam sesi browser Playwright milik browser_control.

    Bukan navigasi langsung ke URL .json (rawan ERR_ABORTED), tapi:
    1. buka halaman HTML reddit.com dulu (cookie + sesi sah terbentuk),
    2. jalankan fetch() di dalam halaman itu (same-origin, credentials include)
       → melewati blokir 403 yang mengenangi requests polos.

    Mengembalikan (data, "") bila sukses, atau (None, alasan) bila gagal.
    Reuse sesi aktif bila ada; kalau belum ada, sesi baru dibuat otomatis.
    """
    try:
        from skills.admin.browser_control import _registry
    except Exception as e:
        return None, f"browser_control tidak bisa diimpor: {e}"
    try:
        sess = _registry.get(None)
    except Exception as e:
        return None, f"sesi browser gagal dibuka: {e}"

    async def _fetch_in_page(url: str) -> str:
        page = await sess._get_page()
        host = url.split("/")[2]
        try:
            cur = page.url or ""
        except Exception:
            cur = ""
        if f"//{host}/" not in cur:          # buka halaman HTML reddit dulu
            await sess.go_to(f"https://{host}/")
        res = await page.evaluate(_JS_FETCH, url)
        if not isinstance(res, dict) or not res.get("ok"):
            st = (res or {}).get("status") if isinstance(res, dict) else "?"
            body = (res or {}).get("text", "")[:80] if isinstance(res, dict) else ""
            raise RuntimeError(f"HTTP {st} via browser fetch: {body}")
        return res.get("text") or ""

    last = ""
    for url in urls:
        try:
            txt = sess.run(_fetch_in_page(url), timeout=45)
            if _looks_json(txt):
                return json.loads(txt), ""
            last = f"bukan JSON ({(txt or '')[:70]!r}) dari {url}"
        except Exception as e:
            last = f"{e} [{url}]"
    return None, last


def _try_get(urls: List[str]) -> Any:
    """Coba beberapa URL sampai ada yang balas 200 dengan JSON valid.

    Bertingkat: requests (UA browser) → sesi browser Playwright (cookie asli).
    """
    last = ""
    for url in urls:
        try:
            r = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT)
            if r.status_code == 403:
                last = f"403 (blocked) dari {url}"
                continue
            r.raise_for_status()
            return r.json()
        except Exception as e:
            last = f"{e} [{url}]"
    data, why = _browser_try(urls)
    if data is not None:
        return data
    raise RuntimeError(
        f"Semua upaya diblokir: requests ({last}); browser ({why}). "
        "Reddit sering memblokir akses otomatis — buka manual via "
        "skill browser_control bila perlu."
    )


def _listing(sub: str, kind: str, query: str, limit: int) -> str:
    sub = sub.strip().lstrip("/")
    if not sub.startswith("r/"):
        sub = f"r/{sub}"
    q = requests.utils.quote(query or "")
    if kind == "search":
        if not query:
            return "Butuh 'query' untuk search subreddit."
        urls = [
            f"https://www.reddit.com/{sub}/search.json?q={q}&restrict_sr=on&sort=new&limit={limit}",
            f"https://old.reddit.com/{sub}/search.json?q={q}&restrict_sr=on&sort=new&limit={limit}",
        ]
    else:
        t = "week" if kind == "top" else ""
        extra = f"&t={t}" if t else ""
        urls = [
            f"https://www.reddit.com/{sub}/{kind}.json?limit={limit}{extra}",
            f"https://old.reddit.com/{sub}/{kind}.json?limit={limit}{extra}",
        ]
    data = _try_get(urls)
    children = (data.get("data") or {}).get("children") or []
    if not children:
        return f"Reddit: tidak ada hasil dari {sub} ({kind})."
    lines = []
    for c in children[:limit]:
        d = c.get("data") or {}
        lines.append(
            f"- {d.get('title')} | {d.get('score')} pts | "
            f"{d.get('num_comments')} comments | u/{d.get('author')} | id {d.get('id')}\n"
            f"  https://www.reddit.com{(d.get('permalink') or '').split('?', 1)[0]}"
        )
    return f"[Reddit · {sub} · {kind}] {len(lines)} post:\n" + "\n".join(lines)


def _thread(url_or_id: str, top: int) -> str:
    """Buka satu thread: post + komentar teratas."""
    s = (url_or_id or "").strip()
    if not s:
        return "Butuh 'query' = permalink/id post Reddit."
    if s.startswith("http"):
        base = s.split("?")[0].rstrip("/")
        if not base.endswith(".json"):
            url = base + ".json"
        else:
            url = base
        urls = [url, url.replace("www.", "old.", 1)]
    else:
        # id pendek / permalink relatif
        p = s if "/" in s else f"comments/{s}"
        p = p if p.startswith("/") else "/" + p
        urls = [
            f"https://www.reddit.com{p}.json?limit={_LIMIT}&sort=top",
            f"https://old.reddit.com{p}.json?limit={_LIMIT}&sort=top",
        ]
    data = _try_get(urls)
    if not isinstance(data, list) or not data:
        return "Reddit: bentuk respons thread tidak dikenal."
    post = ((data[0].get("data") or {}).get("children") or [{}])[0].get("data") or {}
    out = [
        f"[Reddit · thread] {post.get('title')}",
        f"r/{post.get('subreddit')} | {post.get('score')} pts | "
        f"{post.get('num_comments')} comments | u/{post.get('author')}",
        f"https://www.reddit.com{post.get('permalink')}",
    ]
    if post.get("selftext"):
        out.append("post: " + post["selftext"][:600].replace("\n", " "))
    out.append("--- komentar teratas ---")
    kids = ((data[1].get("data") or {}).get("children") or []) if len(data) > 1 else []
    n = 0
    for c in kids:
        if c.get("kind") != "t1" or n >= max(1, min(top, 25)):
            continue
        d = c.get("data") or {}
        body = html.unescape(d.get("body") or "").replace("\n", " ")
        if not body:
            continue
        out.append(f"{d.get('author')} ({d.get('score')} pts): {body[:_MAX_BODY]}")
        out.append("·")
        n += 1
    if n == 0:
        out.append("(tidak ada komentar teratas yang terbaca)")
    return "\n".join(out)


def reddit_fetch(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Ambil listing post Reddit (hot/top/new/search) atau satu thread + komentarnya."""
    p = parameters or {}
    action = str(p.get("action", "hot")).strip().lower()
    subreddit = str(p.get("subreddit", "")).strip()
    query = str(p.get("query", "")).strip()
    limit = int(p.get("limit", _LIMIT) or _LIMIT)
    top_comments = int(p.get("top_comments", 10) or 10)

    try:
        if action == "thread":
            return _thread(query, top_comments)
        if not subreddit:
            return "Butuh 'subreddit' (mis.: technology, programming) — tulis tanpa awalan 'r/'."
        if action in ("hot", "top", "new"):
            return _listing(subreddit, action, "", limit)
        if action == "search":
            return _listing(subreddit, "search", query, limit)
        return (
            "Aksi tidak dikenal. Pilihan action: hot | top | new | search | thread "
            "(param: subreddit, query, limit, top_comments)."
        )
    except Exception as e:
        return f"Reddit fetch error: {e}"


TOOL: Dict[str, Any] = {
    "name": "reddit_fetch",
    "description": (
        "Fetch Reddit content via its JSON API: hot/top/new listings, search inside a "
        "subreddit, or open one thread with its top comments. Handles 403 blocks: "
        "browser-UA requests first, then falls back to the Playwright session of browser_control."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "hot | top | new = listing subreddit; search = cari dalam subreddit; "
                    "thread = buka post + komentar (pakai 'query' = permalink/id)."
                ),
                "enum": ["hot", "top", "new", "search", "thread"],
            },
            "subreddit": {
                "type": "STRING",
                "description": "Nama subreddit tanpa 'r/' (mis.: technology). Wajib utk hot/top/new/search.",
            },
            "query": {
                "type": "STRING",
                "description": "Kata kunci search, atau permalink/id post utk action=thread.",
            },
            "limit": {"type": "INTEGER", "description": "Jumlah post (default 15, maks 50)."},
            "top_comments": {"type": "INTEGER", "description": "Jumlah komentar thread (default 10)."},
        },
        "required": ["action"],
    },
    "handler": reddit_fetch,
    "behavior": "NON_BLOCKING",
}
