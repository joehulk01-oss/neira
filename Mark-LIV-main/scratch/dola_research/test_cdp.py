import subprocess
import time
import json
import asyncio
import httpx
import websockets

EDGE_PATH = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"

async def test():
    print("Launching test Edge instance...")
    import tempfile
    temp_dir = tempfile.mkdtemp(prefix="test_cdp_")
    proc = subprocess.Popen([
        EDGE_PATH,
        "--remote-debugging-port=9223",
        f"--user-data-dir={temp_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "--headless=new",
        "https://www.dola.com"
    ])
    try:
        await asyncio.sleep(2)
        async with httpx.AsyncClient() as client:
            resp = await client.get("http://127.0.0.1:9223/json")
            pages = resp.json()
            print("CDP targets found:", len(pages))
            if pages:
                ws_url = pages[0].get("webSocketDebuggerUrl")
                print("Target WS:", ws_url)
                if ws_url:
                    async with websockets.connect(ws_url) as ws:
                        # Request cookies
                        await ws.send(json.dumps({"id": 1, "method": "Network.getCookies", "params": {"urls": ["https://www.dola.com"]}}))
                        res = await ws.recv()
                        data = json.loads(res)
                        cookies = data.get("result", {}).get("cookies", [])
                        print(f"Retrieved {len(cookies)} cookies via CDP!")
                        for c in cookies[:5]:
                            print(f" - {c.get('name')}: {c.get('value')[:15]}...")
                        # Close browser
                        await ws.send(json.dumps({"id": 2, "method": "Browser.close"}))
                        print("Browser close requested.")
    finally:
        try:
            proc.terminate()
            proc.wait(timeout=3)
        except Exception:
            pass
        print("Done test.")

asyncio.run(test())
