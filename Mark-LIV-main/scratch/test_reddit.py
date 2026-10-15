import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
urls = [
    "https://api.reddit.com/r/technology/hot?limit=3",
    "https://www.reddit.com/r/technology/hot.json?limit=3",
    "https://api.pullpush.io/reddit/submission/search?subreddit=technology&size=3",
]
for u in urls:
    try:
        r = requests.get(u, headers=UA, timeout=8)
        print(r.status_code, "|", u[:75], "|", r.text[:100].replace("\n", " "))
    except Exception as e:
        print("ERR |", u[:75], "|", e)
