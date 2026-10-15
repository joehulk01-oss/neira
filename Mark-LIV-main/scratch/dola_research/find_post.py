import urllib.request
import re

url = "https://www.dola.com//sf-flow-web-cdn.ciciai.com/obj/ocean-flow-web-sg/dola_web/static/js/chat.778b7987.js"
content = urllib.request.urlopen(url).read().decode("utf-8", errors="ignore")

# Find occurrences of "/api/" or "method:"
matches = re.finditer(r'method:\s*["\']POST["\']', content)
count = 0
for m in matches:
    count += 1
    if count <= 10:
        print(f"Match {count} at {m.start()}:")
        print(content[max(0, m.start()-150):min(len(content), m.end()+250)])
        print("-" * 50)
print(f"Total POST matches: {count}")
