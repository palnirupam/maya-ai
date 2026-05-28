"""
Maya AI — Playwright Browser (Async)
Properly uses async Playwright API and async tool functions.
"""
import os
import time
import logging
import asyncio
from playwright.async_api import async_playwright, Browser, BrowserContext, Page

logger = logging.getLogger(__name__)

STATE_FILE = "c:/maya-ai/backend/data/browser_state.json"
SCREENSHOT_DIR = "c:/maya-ai/backend/data/screenshots"

class PlaywrightBrowserManager:
    def __init__(self):
        self._playwright = None
        self._browser: Browser = None
        self._context: BrowserContext = None
        self._page: Page = None

    async def start(self, headless: bool = False):
        if self._page and self._browser and self._browser.is_connected():
            return
        await self.cleanup()
        self._playwright = await async_playwright().start()

        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-infobars",
        ]
        
        # Try to use the system's actual Chrome/Edge to avoid "Unsupported Browser" and bot detection
        try:
            self._browser = await self._playwright.chromium.launch(
                channel="chrome", headless=headless, args=launch_args
            )
        except Exception:
            try:
                self._browser = await self._playwright.chromium.launch(
                    channel="msedge", headless=headless, args=launch_args
                )
            except Exception as e:
                # Fallback to bundled chromium
                err_str = str(e).lower()
                if "executable" in err_str or "install" in err_str or "not found" in err_str:
                    logger.info("System Chrome/Edge missing. Auto-installing bundled Chromium...")
                    import subprocess, sys
                    subprocess.run(
                        [sys.executable, "-m", "playwright", "install", "chromium"],
                        check=True, capture_output=True, text=True
                    )
                self._browser = await self._playwright.chromium.launch(
                    headless=headless, args=launch_args
                )

        storage_state = STATE_FILE if os.path.exists(STATE_FILE) else None
        self._context = await self._browser.new_context(
            viewport={"width": 1280, "height": 720},
            storage_state=storage_state,
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )
        self._page = await self._context.new_page()
        self._page.set_default_timeout(15000)

    async def save_state(self):
        if self._context:
            os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
            await self._context.storage_state(path=STATE_FILE)

    async def close(self):
        try:
            if self._context:
                await self.save_state()
            if self._page:
                await self._page.close()
            if self._context:
                await self._context.close()
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()
        except Exception:
            pass
        finally:
            await self.cleanup()

    async def cleanup(self):
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    @property
    def page(self) -> Page:
        return self._page


browser_manager = PlaywrightBrowserManager()


# ── Public Tool Functions (Must be async!) ────────────────────────────────────

async def playwright_navigate(url: str, headless: bool = False) -> str:
    """
    Navigates the advanced agent browser to a URL and returns the page title.
    Args:
        url (str): The URL to navigate to (e.g. 'https://github.com').
        headless (bool): Set to False to open a visible browser window. Default is False (visible).
    """
    if isinstance(headless, str):
        headless = headless.lower().strip() == "true"
    if not url.startswith("http"):
        url = "https://" + url

    try:
        await browser_manager.start(headless=headless)
        await browser_manager.page.goto(url, wait_until="load")
        await browser_manager.save_state()
        title = await browser_manager.page.title()
        current_url = browser_manager.page.url
        return f"SUCCESS: Navigated to {current_url}. Page Title: '{title}'"
    except Exception as e:
        return f"ERROR during navigation: {e}"


async def playwright_click(selector: str, use_text: bool = False) -> str:
    """
    Clicks an element on the current browser page.
    Args:
        selector (str): CSS selector (e.g. 'button.submit') or visible text of the element.
        use_text (bool): Set to True if the selector is the visible text of the button/link to click.
    """
    if isinstance(use_text, str):
        use_text = use_text.lower().strip() == "true"
    if not browser_manager.page:
        return "ERROR: Browser is not open. Navigate to a URL first using playwright_navigate."
    try:
        if use_text:
            await browser_manager.page.get_by_text(selector).first.click()
        else:
            try:
                await browser_manager.page.click(selector)
            except Exception:
                try:
                    await browser_manager.page.get_by_role("button", name=selector).first.click()
                except Exception:
                    await browser_manager.page.get_by_text(selector).first.click()
        await browser_manager.save_state()
        return f"SUCCESS: Clicked element '{selector}'"
    except Exception as e:
        return f"ERROR clicking element '{selector}': {e}"


async def playwright_type(selector: str, text: str, press_enter: bool = False) -> str:
    """
    Types text into a form input or text field on the current browser page.
    Args:
        selector (str): CSS selector of the input field (e.g. 'input[name=q]').
        text (str): The text to type into the field.
        press_enter (bool): If True, presses Enter after typing. Default is False.
    """
    if isinstance(press_enter, str):
        press_enter = press_enter.lower().strip() == "true"
    if not browser_manager.page:
        return "ERROR: Browser is not open. Navigate to a URL first using playwright_navigate."
    try:
        await browser_manager.page.fill(selector, "")
        await browser_manager.page.type(selector, text)
        if press_enter:
            await browser_manager.page.press(selector, "Enter")
        await browser_manager.save_state()
        return f"SUCCESS: Typed text into '{selector}'"
    except Exception as e:
        return f"ERROR typing into '{selector}': {e}"


async def playwright_screenshot() -> str:
    """
    Takes a screenshot of the current browser viewport and saves it as a PNG file.
    Returns the absolute path of the saved screenshot.
    """
    if not browser_manager.page:
        return "ERROR: Browser is not open. Navigate to a URL first using playwright_navigate."
    try:
        os.makedirs(SCREENSHOT_DIR, exist_ok=True)
        filename = f"browser_{int(time.time())}.png"
        filepath = os.path.join(SCREENSHOT_DIR, filename)
        await browser_manager.page.screenshot(path=filepath)
        return f"SUCCESS: Saved browser screenshot to: {filepath}"
    except Exception as e:
        return f"ERROR taking screenshot: {e}"


async def playwright_get_content() -> str:
    """
    Extracts a clean, structured text representation of the current browser page content.
    Includes title, page text, form inputs, and links. Use after playwright_navigate.
    """
    if not browser_manager.page:
        return "ERROR: Browser is not open. Navigate to a URL first using playwright_navigate."
    try:
        title = await browser_manager.page.title()
        url = browser_manager.page.url

        script = """
        () => {
            const isVisible = (el) => {
                const rect = el.getBoundingClientRect();
                return rect.width > 0 && rect.height > 0 && window.getComputedStyle(el).display !== 'none';
            };
            const badTags = document.querySelectorAll('script, style, svg, iframe, noscript');
            badTags.forEach(t => t.remove());
            const links = [];
            document.querySelectorAll('a').forEach(a => {
                if (isVisible(a) && a.innerText.trim()) {
                    links.push(`[${a.innerText.trim()}](${a.href})`);
                }
            });
            const forms = [];
            document.querySelectorAll('input, textarea, select').forEach(el => {
                if (isVisible(el)) {
                    const id = el.id || '';
                    const name = el.name || '';
                    const type = el.type || '';
                    const val = el.value || '';
                    const placeholder = el.placeholder || '';
                    forms.push(`Input -> Type: ${type}, ID: "${id}", Name: "${name}", Value: "${val}", Placeholder: "${placeholder}"`);
                }
            });
            const bodyText = document.body.innerText || '';
            const lines = bodyText.split('\\n').map(l => l.trim()).filter(l => l.length > 0);
            const cleanText = lines.slice(0, 150).join('\\n');
            return { text: cleanText, links: links.slice(0, 30), forms: forms.slice(0, 20) };
        }
        """
        res = await browser_manager.page.evaluate(script)

        content_str = f"PAGE TITLE: {title}\nPAGE URL: {url}\n\n"
        content_str += "--- PAGE TEXT ---\n" + res["text"] + "\n\n"
        if res["forms"]:
            content_str += "--- INTERACTIVE FIELDS ---\n" + "\n".join(res["forms"]) + "\n\n"
        if res["links"]:
            content_str += "--- USEFUL LINKS ---\n" + "\n".join(res["links"]) + "\n"
        return content_str
    except Exception as e:
        return f"ERROR extracting page content: {e}"


async def playwright_upload_file(selector: str, file_path: str) -> str:
    """
    Uploads a file using a file input element on the current browser page.
    Args:
        selector (str): CSS selector of the file input element (e.g. 'input[type=file]').
        file_path (str): Absolute path to the file to upload (e.g. 'C:/Users/user/Documents/report.pdf').
    """
    if not browser_manager.page:
        return "ERROR: Browser is not open. Navigate to a URL first using playwright_navigate."
    if not os.path.exists(file_path):
        return f"ERROR: File not found: {file_path}"
    try:
        await browser_manager.page.set_input_files(selector, file_path)
        await browser_manager.save_state()
        return f"SUCCESS: Uploaded file '{os.path.basename(file_path)}' to '{selector}'"
    except Exception as e:
        return f"ERROR uploading file to '{selector}': {e}"


async def playwright_close() -> str:
    """
    Saves the current browser session (cookies, login state) and closes the browser.
    """
    try:
        await browser_manager.close()
        return "SUCCESS: Closed the browser and saved state."
    except Exception as e:
        return f"ERROR closing browser: {e}"
