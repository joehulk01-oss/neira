import sys
from playwright.sync_api import sync_playwright

print("Starting playwright test...")
try:
    with sync_playwright() as p:
        print("Playwright started")
        # Check available browsers
        try:
            browser = p.chromium.launch(headless=True)
            print("Chromium launched OK")
            browser.close()
        except Exception as e:
            print("Chromium error:", e)
            try:
                browser = p.chromium.launch(channel="msedge", headless=True)
                print("Edge launched OK")
                browser.close()
            except Exception as e2:
                print("Edge error:", e2)
except Exception as e:
    print("Fatal error:", e)
print("Finished.")
