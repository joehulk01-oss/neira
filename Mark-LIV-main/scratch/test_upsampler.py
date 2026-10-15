import asyncio
from abigail.client import VideoClient

async def test_video():
    print("Testing VideoClient (Upsampler HuggingFace Gradio)...", flush=True)
    try:
        async with VideoClient(request_timeout=60.0, max_retries=1) as client:
            print("Sending prompt to VideoClient...", flush=True)
            res = await client.generate_video("a drone flying over green mountains", duration=3.0)
            print(f"[OK] Video Generation Success! Provider: {res.provider}")
            print(f"Video URL: {res.url}")
            return True
    except Exception as e:
        print(f"[FAILED] Video Error: {e}", flush=True)
        return False

if __name__ == "__main__":
    asyncio.run(test_video())
