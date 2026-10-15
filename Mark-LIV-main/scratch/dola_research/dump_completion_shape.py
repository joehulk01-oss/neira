"""Dump wider context around /chat/completion & chunk_stream call sites to learn the request payload shape."""
import urllib.request

url = "https://www.dola.com//sf-flow-web-cdn.ciciai.com/obj/ocean-flow-web-sg/dola_web/static/js/chat.778b7987.js"
content = urllib.request.urlopen(url).read().decode("utf-8", errors="ignore")
print("bundle size:", len(content))

for needle in ("/chat/completion", "/chat/async/chunk_stream", "/chat/new-thread"):
    print("\n" + "#" * 70)
    print("NEEDLE:", needle)
    idx = content.find(needle)
    n = 0
    while idx != -1 and n < 6:
        n += 1
        print(f"\n--- match {n} at {idx} ---")
        print(content[max(0, idx - 800):min(len(content), idx + 1200)])
        idx = content.find(needle, idx + 1)

# Also hunt for likely payload keys near 'completion'
for key in ("local_message_id", "thread_id", "prompt", "messages", "chat_type", "model", "skill", "action_name"):
    cnt = content.count(key)
    print(f"key {key!r}: {cnt} occurrences")
