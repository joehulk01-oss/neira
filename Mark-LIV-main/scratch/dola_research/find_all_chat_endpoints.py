import urllib.request
import re

url = "https://www.dola.com//sf-flow-web-cdn.ciciai.com/obj/ocean-flow-web-sg/dola_web/static/js/chat.778b7987.js"
content = urllib.request.urlopen(url).read().decode("utf-8", errors="ignore")

# Find all url paths starting with /
matches = set(re.findall(r'["\'](/(?:im|chat|flow|message|conversation|api|v[0-9])/[a-zA-Z0-9_/-]+)["\']', content))
print(f"Found {len(matches)} chat endpoints:")
for m in sorted(matches):
    print(" -", m)
