import asyncio
from pathlib import Path
from abigail.client import VideoClient

async def main():
    print("Testing Video generation and saving MP4...", flush=True)
    out_dir = Path("workspace/videos")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    async with VideoClient(request_timeout=90.0, max_retries=1) as client:
        res = await client.generate_video("cinematic sunset over ocean waves", duration=3.0)
        print(f"Video generated! Provider: {res.provider}, Videos: {len(res.videos)}")
        if res.videos:
            v = res.videos[0]
            save_path = out_dir / "ocean_sunset.mp4"
            save_path.write_bytes(v.video_bytes)
            print(f"[SUCCESS] Saved MP4 to: {save_path} (Size: {len(v.video_bytes)} bytes)")

if __name__ == "__main__":
    asyncio.run(main())
