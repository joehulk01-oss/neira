import sys
import subprocess
import time
import json
import httpx
import websockets
import asyncio
import tempfile
import shutil

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

async def send_cmd(ws, msg_id, method, params=None):
    payload = {"id": msg_id, "method": method}
    if params:
        payload["params"] = params
    await ws.send(json.dumps(payload))
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        data = json.loads(raw)
        if data.get("id") == msg_id:
            return data

async def main():
    print("Testing Edge CDP with event filtering...", flush=True)
    temp_dir = tempfile.mkdtemp(prefix="test_cdp_")
    proc = subprocess.Popen([
        EDGE_PATH,
        "--remote-debugging-port=9227",
        f"--user-data-dir={temp_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--headless=new",
        "https://www.dola.com"
    ])
    try:
        client = httpx.AsyncClient()
        page_ws = None
        for _ in range(20):
            try:
                r = await client.get("http://127.0.0.1:9227/json", timeout=1.0)
                if r.status_code == 200:
                    targets = r.json()
                    pages = [t for t in targets if t.get("type") == "page"]
                    if pages:
                        page_ws = pages[0].get("webSocketDebuggerUrl")
                        break
            except Exception:
                pass
            await asyncio.sleep(0.5)
        
        print("Page WS:", page_ws, flush=True)
        if page_ws:
            async with websockets.connect(page_ws) as ws:
                await send_cmd(ws, 1, "Network.enable")
                res = await send_cmd(ws, 2, "Network.getCookies", {"urls": ["https://www.dola.com"]})
                cookies = res.get("result", {}).get("cookies", [])
                print(f"SUCCESS! Retrieved {len(cookies)} cookies!", flush=True)
                for c in cookies[:5]:
                    print(f" - {c.get('name')}: {c.get('value')[:15]}...", flush=True)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("Cleaned up.", flush=True)

asyncio.run(main())
