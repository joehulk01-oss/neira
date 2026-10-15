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
    print("Testing Edge CDP...", flush=True)
    temp_dir = tempfile.mkdtemp(prefix="test_cdp_")
    proc = subprocess.Popen([
        EDGE_PATH,
        "--remote-debugging-port=9225",
        f"--user-data-dir={temp_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--headless=new",
        "https://www.dola.com"
    ])
    try:
        # Wait for port to be ready
        client = httpx.AsyncClient()
        version_data = None
        for _ in range(10):
            try:
                r = await client.get("http://127.0.0.1:9225/json/version", timeout=1.0)
                if r.status_code == 200:
                    version_data = r.json()
                    break
            except Exception:
                await asyncio.sleep(0.5)
        
        print("Version data:", version_data, flush=True)
        if version_data:
            browser_ws = version_data.get("webSocketDebuggerUrl")
            print("Connecting to browser ws:", browser_ws, flush=True)
            async with websockets.connect(browser_ws) as ws:
                # Storage.getCookies returns all cookies
                await ws.send(json.dumps({"id": 1, "method": "Storage.getCookies"}))
                resp = await asyncio.wait_for(ws.recv(), timeout=5.0)
                cookies = json.loads(resp).get("result", {}).get("cookies", [])
                print(f"Retrieved {len(cookies)} cookies!", flush=True)
                for c in cookies[:3]:
                    print("Cookie:", c.get("name"), flush=True)
                
                # Close browser cleanly
                await ws.send(json.dumps({"id": 2, "method": "Browser.close"}))
                print("Sent Browser.close", flush=True)
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        shutil.rmtree(temp_dir, ignore_errors=True)
        print("Cleaned up.", flush=True)

asyncio.run(main())
