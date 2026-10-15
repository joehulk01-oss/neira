import urllib.request
import re
import json

print("Fetching Dola chat script...")
req = urllib.request.Request("https://www.dola.com/chat/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
html = urllib.request.urlopen(req).read().decode("utf-8")
scripts = re.findall(r'src="([^"]+\.js)"', html)
print(f"Found {len(scripts)} scripts in HTML")

# Search for api endpoints
api_patterns = set()
for s in scripts:
    if not s.startswith("http"):
        s = "https://www.dola.com" + s
    try:
        content = urllib.request.urlopen(s, timeout=5).read().decode("utf-8", errors="ignore")
        # Look for /api/ or /im/ or /chat/
        matches = re.findall(r'["\'](/(?:api|im|chat|flow|conversation)/[^"\']+)["\']', content)
        for m in matches:
            if len(m) < 80 and not m.endswith(('.js', '.css', '.png', '.svg', '.json')):
                api_patterns.add(m)
    except Exception as e:
        pass

print("Discovered endpoints:")
for ep in sorted(api_patterns):
    print(" -", ep)
