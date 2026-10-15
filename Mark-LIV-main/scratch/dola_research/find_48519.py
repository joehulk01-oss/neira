import urllib.request
import re

url = "https://www.dola.com//sf-flow-web-cdn.ciciai.com/obj/ocean-flow-web-sg/dola_web/static/js/48519.a71eae48.js"
content = urllib.request.urlopen(url).read().decode("utf-8", errors="ignore")

matches = set(re.findall(r'["\'](/(?:im|chat|flow|message|conversation|api|v[0-9]|samantha)/[a-zA-Z0-9_/-]+)["\']', content))
print(f"Found {len(matches)} endpoints in 48519:")
for m in sorted(matches):
    print(" -", m)
