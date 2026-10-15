"""
Neira Smart Browser Core Engine.
Inspired by OpenMuse (https://github.com/CopilotKit/openmuse) architecture:
1. Persistent Browser Context: User data, cookies, and local session retained across actions.
2. Compact Interactive Accessibility / DOM Tree:
   Maps clickable/typeable elements to clean integer IDs (#1, #2, #3),
   drastically reducing token usage and eliminating selector guessing for LLMs (Hermes/Gemini).
3. Robust Action Dispatcher:
   - navigate(url)
   - click(element_id)
   - type_text(element_id, text, clear, press_enter)
   - select_option(element_id, value)
   - snapshot() -> structured interactive element list + text summary
   - take_control() -> opens interactive headful browser for human takeover (OTP, Captcha, 2FA)
"""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR = _base_dir()
PROFILE_DIR = BASE_DIR / "workspace" / "browser_data" / "default_profile"
TRACES_DIR = BASE_DIR / "workspace" / "browser_data" / "traces"

PROFILE_DIR.mkdir(parents=True, exist_ok=True)
TRACES_DIR.mkdir(parents=True, exist_ok=True)


# JavaScript snippet to extract interactive elements and generate numbered indices
JS_EXTRACT_INTERACTIVE_TREE = """
(() => {
    let elements = [];
    let idCounter = 1;
    
    // Remove previous markers
    document.querySelectorAll('[data-neira-id]').forEach(el => el.removeAttribute('data-neira-id'));

    const isVisible = (elem) => {
        if (!elem) return false;
        const style = window.getComputedStyle(elem);
        if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
        const rect = elem.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
    };

    const selector = 'button, a[href], input, textarea, select, [role="button"], [role="link"], [role="checkbox"], [contenteditable="true"]';
    const candidateNodes = Array.from(document.querySelectorAll(selector));

    for (let el of candidateNodes) {
        if (!isVisible(el)) continue;
        
        const tagName = el.tagName.toLowerCase();
        let role = el.getAttribute('role') || tagName;
        let type = el.getAttribute('type') || '';
        let label = (
            el.innerText ||
            el.getAttribute('aria-label') ||
            el.getAttribute('placeholder') ||
            el.getAttribute('title') ||
            el.getAttribute('name') ||
            el.value ||
            ''
        ).replace(/\\s+/g, ' ').trim();

        // Limit label length
        if (label.length > 80) label = label.substring(0, 77) + '...';

        const nid = idCounter++;
        el.setAttribute('data-neira-id', nid.toString());

        elements.push({
            id: nid,
            tag: tagName,
            role: role,
            type: type,
            label: label,
            value: el.value !== undefined ? String(el.value).trim() : ''
        });
    }

    return {
        title: document.title,
        url: window.location.href,
        elements: elements
    };
})();
"""


class SmartBrowserManager:
    """Singleton Browser Manager running Playwright with persistent context."""
    _instance: Optional["SmartBrowserManager"] = None
    _lock = threading.Lock()

    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._playwright = None
        self._context = None
        self._page = None
        self._active_elements: Dict[int, Any] = {}
        self._is_ready = threading.Event()
        self._start_worker_thread()

    @classmethod
    def get_instance(cls) -> "SmartBrowserManager":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def _start_worker_thread(self):
        self._init_error = None

        def _runner():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            try:
                self._loop.run_until_complete(self._init_playwright())
            except Exception as exc:
                self._init_error = exc
            finally:
                self._is_ready.set()
            self._loop.run_forever()

        self._thread = threading.Thread(target=_runner, name="NeiraSmartBrowserThread", daemon=True)
        self._thread.start()
        self._is_ready.wait(timeout=20.0)
        if self._init_error:
            raise RuntimeError(f"Playwright initialization failed: {self._init_error}")

    async def _init_playwright(self):
        from playwright.async_api import async_playwright
        self._playwright = await async_playwright().start()
        
        # Launch persistent context to store cookies, sessions, local storage
        self._context = await self._playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=True,
            viewport={"width": 1280, "height": 800},
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )
        if len(self._context.pages) > 0:
            self._page = self._context.pages[0]
        else:
            self._page = await self._context.new_page()

    def _run_coroutine(self, coro, timeout: float = 30.0):
        if not self._loop:
            raise RuntimeError("Browser event loop not initialized.")
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result(timeout=timeout)

    # ── Public Synchronous Actions ──────────────────────────────────────────

    def navigate(self, url: str) -> Dict[str, Any]:
        """Navigate to a URL and return initial page snapshot."""
        if not (url.startswith("http://") or url.startswith("https://") or url.startswith("file://") or url.startswith("about:")):
            url = "https://" + url

        async def _nav():
            await self._page.goto(url, wait_until="domcontentloaded", timeout=25000)
            await self._page.wait_for_timeout(1000)
            return await self._get_snapshot_async()

        return self._run_coroutine(_nav(), timeout=30.0)

    def snapshot(self) -> Dict[str, Any]:
        """Capture the current interactive element map and state."""
        return self._run_coroutine(self._get_snapshot_async(), timeout=15.0)

    async def _get_snapshot_async(self) -> Dict[str, Any]:
        data = await self._page.evaluate(JS_EXTRACT_INTERACTIVE_TREE)
        self._active_elements = {item["id"]: item for item in data.get("elements", [])}
        
        # Build compact text representation for LLM prompt
        lines = [f"URL: {data.get('url')}", f"Judul: {data.get('title')}", "--- Elemen Interaktif ---"]
        for el in data.get("elements", [])[:45]: # cap at 45 most relevant interactive elements
            desc = f"#{el['id']} [{el['tag'].upper()}"
            if el['type']:
                desc += f":{el['type']}"
            desc += f"]"
            if el['label']:
                desc += f" \"{el['label']}\""
            if el['value'] and el['value'] != el['label']:
                desc += f" (value: {el['value']})"
            lines.append(desc)
            
        if len(data.get("elements", [])) > 45:
            lines.append(f"... dan {len(data['elements']) - 45} elemen lainnya.")

        return {
            "url": data.get("url"),
            "title": data.get("title"),
            "elements_count": len(data.get("elements", [])),
            "text_summary": "\n".join(lines),
            "raw_elements": data.get("elements", [])
        }

    def click(self, element_id: int) -> Dict[str, Any]:
        """Click element by its numeric ID (#1, #2, etc)."""
        async def _click():
            selector = f'[data-neira-id="{element_id}"]'
            try:
                await self._page.click(selector, timeout=5000)
                await self._page.wait_for_timeout(1000)
                return {
                    "status": "success",
                    "action": f"Clicked element #{element_id}",
                    "new_snapshot": await self._get_snapshot_async()
                }
            except Exception as e:
                return {
                    "status": "error",
                    "action": f"Failed to click element #{element_id}: {str(e)}",
                    "new_snapshot": await self._get_snapshot_async()
                }

        return self._run_coroutine(_click(), timeout=15.0)

    def type_text(self, element_id: int, text: str, clear: bool = True, press_enter: bool = False) -> Dict[str, Any]:
        """Type text into element by its numeric ID."""
        async def _type():
            selector = f'[data-neira-id="{element_id}"]'
            try:
                if clear:
                    await self._page.fill(selector, "", timeout=4000)
                await self._page.fill(selector, text, timeout=5000)
                if press_enter:
                    await self._page.press(selector, "Enter", timeout=4000)
                    await self._page.wait_for_timeout(1000)
                return {
                    "status": "success",
                    "action": f"Filled element #{element_id} with text '{text}'",
                    "new_snapshot": await self._get_snapshot_async()
                }
            except Exception as e:
                return {
                    "status": "error",
                    "action": f"Failed to type in #{element_id}: {str(e)}",
                    "new_snapshot": await self._get_snapshot_async()
                }

        return self._run_coroutine(_type(), timeout=15.0)

    def select_option(self, element_id: int, value: str) -> Dict[str, Any]:
        """Select dropdown option for <select> element by ID."""
        async def _select():
            selector = f'[data-neira-id="{element_id}"]'
            try:
                await self._page.select_option(selector, value=value, timeout=5000)
                await self._page.wait_for_timeout(800)
                return {
                    "status": "success",
                    "action": f"Selected option '{value}' in #{element_id}",
                    "new_snapshot": await self._get_snapshot_async()
                }
            except Exception as e:
                return {
                    "status": "error",
                    "action": f"Failed to select in #{element_id}: {str(e)}",
                    "new_snapshot": await self._get_snapshot_async()
                }

        return self._run_coroutine(_select(), timeout=15.0)

    def screenshot(self, filename: str = "") -> str:
        """Capture screenshot to workspace traces."""
        if not filename:
            filename = f"screen_{int(time.time())}.png"
        out_path = TRACES_DIR / filename

        async def _shot():
            await self._page.screenshot(path=str(out_path), full_page=False)
            return str(out_path)

        return self._run_coroutine(_shot(), timeout=10.0)

    def take_control(self) -> str:
        """
        Open the current session in a visible browser window or notify the user
        to take control when manual action is needed (CAPTCHA / 2FA).
        """
        current_url = self._run_coroutine(self._page.evaluate("window.location.href"), timeout=5.0)
        screenshot_path = self.screenshot("takeover_prompt.png")
        return (
            f"Mode Take-Control Aktif!\n"
            f"URL Saat Ini: {current_url}\n"
            f"Screenshot tersimpan di: {screenshot_path}\n"
            f"Silakan buka browser atau selesaikan verifikasi/CAPTCHA manual."
        )

# Module-level convenience functions
def get_browser() -> SmartBrowserManager:
    return SmartBrowserManager.get_instance()
