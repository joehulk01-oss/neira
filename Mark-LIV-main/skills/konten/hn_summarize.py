"""
HN Summarize — ambil & rangkum berita Hacker News.

Diadaptasi dari skill `hn-summarize` repo github.com/ykdojo/claude-code-tips
(menggunakan API resmi Firebase + Algolia yang mengembalikan JSON polos).

Auto-discovered oleh core/action_loader.py dan core/skill_hub.py via TOOL dict.
"""
from __future__ import annotations

import html
import re
import sys
from typing import Any, Dict, List

import requests

for _stream in ("stdout", "stderr"):
    try:
        _s = getattr(sys, _stream, None)
        if _s is not None and hasattr(_s, "reconfigure"):
            _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

_FB = "https://hacker-news.firebaseio.com/v0"
_ALG = "https://hn.algolia.com/api/v1"
_UA = {"User-Agent": "Mozilla/5.0 (Neira HN skill)"}
_TIMEOUT = 8


def _get_json(url: str) -> Any:
    r = requests.get(url, headers=_UA, timeout=_TIMEOUT)
    r.raise_for_status()
    return r.json()


def _clean(text: str) -> str:
    """Strip HN HTML entities/tags jadi teks biasa."""
    t = html.unescape(text or "")
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _top(n: int) -> str:
    ids = _get_json(f"{_FB}/topstories.json")[: max(1, min(n, 30))]
    lines: list[str] = []
    for i, sid in enumerate(ids, 1):
        try:
            d = _get_json(f"{_FB}/item/{sid}.json") or {}
        except Exception:
            continue
        score = d.get("score", 0)
        comments = d.get("descendants", 0)
        url = d.get("url", "(text post)")
        lines.append(
            f"{i}. {d.get('title')} | {score} pts | {comments} comments | id {sid}\n   {url}"
        )
    if not lines:
        return "HN: gagal mengambil top stories."
    return f"[HN · top {len(lines)}]\n" + "\n".join(lines)


def _search(query: str, limit: int) -> str:
    data = _get_json(f"{_ALG}/search?query={requests.utils.quote(query)}&tags=story")
    hits = (data.get("hits") or [])[: max(1, min(limit, 20))]
    if not hits:
        return f"HN: tidak ada hasil untuk '{query}'."
    lines = []
    for h in hits:
        lines.append(
            f"- {h.get('title')} | {h.get('points') or 0} pts | "
            f"{h.get('num_comments') or 0} comments | id {h.get('objectID')}\n"
            f"  {h.get('url') or '(text post)'}"
        )
    return f"[HN · search '{query}'] {len(lines)} hasil:\n" + "\n".join(lines)


def _story(query: str, top_comments: int) -> str:
    """Cari story dari query lalu tarik pohon komentarnya (cara Algolia items)."""
    data = _get_json(f"{_ALG}/search?query={requests.utils.quote(query)}&tags=story")
    hits = data.get("hits") or []
    if not hits:
        return f"HN: story '{query}' tidak ditemukan."
    best = max(hits, key=lambda h: (h.get("points") or 0) + (h.get("num_comments") or 0))
    oid = best.get("objectID")
    item = _get_json(f"{_ALG}/items/{oid}")
    out = [
        f"[HN · story] {item.get('title')}",
        f"url: {item.get('url') or '(text post)'} | points: {item.get('points')} | "
        f"author: {item.get('author')} | id: {oid}",
    ]
    story_text = item.get("story_text")
    if story_text:
        out.append("post: " + _clean(story_text)[:600])
    kids = item.get("children") or []
    if kids:
        out.append(f"--- komentar teratas ({min(top_comments, len(kids))}) ---")
    for c in kids[: max(1, min(top_comments, 25))]:
        txt = _clean(c.get("text") or "")
        if txt:
            out.append(f"{c.get('author')}: {txt[:550]}")
            out.append("·")
    return "\n".join(out)


def hn_summarize(parameters: Dict[str, Any] = None, **kwargs) -> str:
    """Ambil top stories / cari / buka story + komentar Hacker News."""
    p = parameters or {}
    action = str(p.get("action", "top")).strip().lower()
    query = str(p.get("query", "")).strip()
    limit = int(p.get("limit", 10) or 10)
    top_comments = int(p.get("top_comments", 8) or 8)

    try:
        if action == "top":
            return _top(limit)
        if action == "search":
            if not query:
                return "Butuh 'query' untuk search (mis.: rust, ai agents)."
            return _search(query, limit)
        if action == "story":
            if not query:
                return "Butuh 'query' = judul/topik story yang mau dibuka."
            return _story(query, top_comments)
        return "Aksi tidak dikenal. Pilihan action: top | search | story."
    except Exception as e:
        return f"HN summarize error: {e}"


TOOL: Dict[str, Any] = {
    "name": "hn_summarize",
    "description": (
        "Fetch and summarize Hacker News: top front-page stories, keyword search, "
        "or a single story plus its top comment thread (official Firebase + Algolia JSON APIs)."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "top = berita depan; search = cari topik; story = buka story + komentar.",
                "enum": ["top", "search", "story"],
            },
            "query": {
                "type": "STRING",
                "description": "Kata kunci / judul story (wajib utk search & story).",
            },
            "limit": {
                "type": "INTEGER",
                "description": "Jumlah hasil top/search (default 10, maks 30).",
            },
            "top_comments": {
                "type": "INTEGER",
                "description": "Jumlah komentar teratas untuk action=story (default 8).",
            },
        },
        "required": ["action"],
    },
    "handler": hn_summarize,
    "behavior": "NON_BLOCKING",
}
