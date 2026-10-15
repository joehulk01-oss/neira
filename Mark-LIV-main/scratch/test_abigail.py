import asyncio
import sys
from abigail.client import ChatClient, ImageClient
from abigail.types.capabilities import Capability

async def test_chat():
    print("--- [TEST 1: CHAT CLIENT] ---", flush=True)
    async with ChatClient(request_timeout=30.0, max_retries=1) as client:
        # Test default auto provider
        try:
            print("Sending prompt to ChatClient...", flush=True)
            res = await client.chat("Halo! Jawab hanya dengan 1 kata: 'OK'.")
            print(f"Chat Result: Provider={res.provider}, Model={res.model}")
            print(f"Response: {res.text.strip()[:100]}", flush=True)
            return True
        except Exception as e:
            print(f"Chat Error: {e}", flush=True)
            return False

async def test_providers_individually():
    print("\n--- [TEST 2: PROVIDERS PROBE] ---", flush=True)
    providers = ["deepai", "heckai", "notrack", "quillbot", "unlimitedai"]
    for prov in providers:
        print(f"Testing provider '{prov}'...", end=" ", flush=True)
        try:
            async with ChatClient(request_timeout=15.0, max_retries=1) as client:
                res = await client.chat("Halo", provider=prov)
                print(f"[OK] Response: {res.text.strip()[:50]}")
        except Exception as e:
            print(f"[FAILED] {e}")

async def main():
    chat_ok = await test_chat()
    await test_providers_individually()

if __name__ == "__main__":
    asyncio.run(main())
