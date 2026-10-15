"""Probe: mana yg bisa diambil reddit dari dalam sesi browser (in-page fetch)."""
import sys, json
for _s in ("stdout", "stderr"):
    try:
        _f = getattr(sys, _s, None)
        if _f is not None and hasattr(_f, "reconfigure"):
            _f.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
sys.path.insert(0, ".")
from skills.admin.browser_control import _registry

JS = """async (u) => {
    try {
        const r = await fetch(u, {credentials: 'include', redirect: 'follow'});
        const t = await r.text();
        return {ok: r.ok, status: r.status, url: r.url, text: t.slice(0, 300000)};
    } catch (e) { return {ok: false, status: 0, url: '', text: String(e)}; }
}"""

URLS = [
    "https://www.reddit.com/r/technology/hot.json?limit=3",
    "https://old.reddit.com/r/technology/hot/?limit=3",
    "https://www.reddit.com/r/technology/top.json?t=day&limit=3",
    "https://www.reddit.com/r/technology/",
]


def main():
    sess = _registry.get(None)

    async def probe():
        page = await sess._get_page()
        out = []
        for u in URLS:
            host = u.split("/")[2]
            try:
                cur = page.url or ""
            except Exception:
                cur = ""
            if f"//{host}/" not in cur:
                try:
                    await sess.go_to(f"https://{host}/")
                except Exception as e:
                    out.append(f"goto {host} ERR {e}")
            res = await page.evaluate(JS, u)
            txt = (res.get("text") or "").replace("\n", " ")
            out.append(
                f"{res.get('status')} ok={res.get('ok')} final={res.get('url')}\n"
                f"   head={txt[:180]!r}"
            )
        return "\n".join(out)

    print(sess.run(probe(), timeout=90))


if __name__ == "__main__":
    main()
