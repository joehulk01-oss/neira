import asyncio
import sys
from pathlib import Path
from abigail.client import ImageClient

async def test_image():
    print("--- [TEST 3: IMAGE CLIENT] ---", flush=True)
    out_dir = Path("workspace/images")
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # Test image generation with timeout
    try:
        print("Connecting to ImageClient (Perchance)...", flush=True)
        async with ImageClient(request_timeout=60.0, max_retries=1, headless=True) as client:
            print("Requesting image generation for prompt: 'cute robotic cat mascot'...", flush=True)
            res = await client.generate_image("cute robotic cat mascot", resolution="512x512")
            print(f"[OK] Image generation finished! Provider: {res.provider}, Images count: {len(res.images)}")
            for idx, img in enumerate(res.images):
                save_path = out_dir / f"test_img_{idx+1}.png"
                if hasattr(img, "save"):
                    img.save(str(save_path))
                    print(f"Saved image to: {save_path} (Size: {save_path.stat().st_size} bytes)")
                elif hasattr(img, "data") and img.data:
                    save_path.write_bytes(img.data)
                    print(f"Saved image to: {save_path} (Size: {save_path.stat().st_size} bytes)")
                elif hasattr(img, "url") and img.url:
                    print(f"Image URL: {img.url}")
            return True
    except Exception as e:
        print(f"[FAILED] Image Generation Error: {e}", flush=True)
        return False

if __name__ == "__main__":
    asyncio.run(test_image())
