import urllib.request
import re

url = "https://www.dola.com//sf-flow-web-cdn.ciciai.com/obj/ocean-flow-web-sg/dola_web/static/js/chat.778b7987.js"
content = urllib.request.urlopen(url).read().decode("utf-8", errors="ignore")

idx = content.find("/chat/completion")
while idx != -1:
    print("Match at", idx)
    print(content[max(0, idx-300):min(len(content), idx+500)])
    print("="*60)
    idx = content.find("/chat/completion", idx+1)
