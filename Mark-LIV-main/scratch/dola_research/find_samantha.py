import urllib.request
import re

url = "https://www.dola.com//sf-flow-web-cdn.ciciai.com/obj/ocean-flow-web-sg/dola_web/static/js/chat.778b7987.js"
content = urllib.request.urlopen(url).read().decode("utf-8", errors="ignore")

matches = set(re.findall(r'["\'](/(?:samantha|alice)/[a-zA-Z0-9_/]+)["\']', content))
print(f"Found {len(matches)} samantha/alice endpoints:")
for m in sorted(matches):
    print(" -", m)
