import urllib.request
import re

req = urllib.request.Request("https://www.dola.com/chat/", headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
html = urllib.request.urlopen(req).read().decode("utf-8")
scripts = re.findall(r'src="([^"]+\.js)"', html)

for s in scripts:
    if not s.startswith("http"):
        s = "https://www.dola.com" + s
    content = urllib.request.urlopen(s, timeout=5).read().decode("utf-8", errors="ignore")
    if "/chat/completion" in content or "completion" in content:
        print("Found in script:", s)
        # Find context around completion
        for match in re.finditer(r'(/chat/completion[a-zA-Z0-9_/]*)', content):
            start = max(0, match.start() - 200)
            end = min(len(content), match.end() + 200)
            print("--- Snippet ---")
            print(content[start:end])
            print("---------------")
