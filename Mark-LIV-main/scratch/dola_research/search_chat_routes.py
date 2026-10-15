import urllib.request
import re

url = "https://www.dola.com//sf-flow-web-cdn.ciciai.com/obj/ocean-flow-web-sg/dola_web/static/js/chat.778b7987.js"
content = urllib.request.urlopen(url).read().decode("utf-8", errors="ignore")

# Find occurrences of "/chat/"
matches = re.finditer(r'["\'](/chat/[a-zA-Z0-9_/]+)["\']', content)
for m in matches:
    path = m.group(1)
    if path not in ["/chat/completion", "/chat/async/chunk_stream"]:
        print(f"Path: {path} at {m.start()}")
        print("  Snippet:", content[max(0, m.start()-100):min(len(content), m.end()+150)])
        print("-" * 50)
