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

async def main():
    print("Testing Edge CDP Page target...", flush=True)
    temp_dir = tempfile.mkdtemp(prefix="test_cdp_")
    proc = subprocess.Popen([
        EDGE_PATH,
        "--remote-debugging-port=9226",
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
                r = await client.get("http://127.0.0.1:9226/json", timeout=1.0)
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
                # Enable Network
                await ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
                r1 = await asyncio.wait_for(ws.recv(), timeout=5.0)
                print("Network.enable response:", r1, flush=True)
                
                # Get cookies
                await ws.send(json.dumps({"id": 2, "method": "Network.getCookies", "params": {"urls": ["https://www.dola.com"]}}))
                r2 = await asyncio.wait_for(ws.recv(), timeout=5.0)
                data = json.loads(r2)
                cookies = data.get("result", {}).get("cookies", [])
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
