"""
Maya AI — Background App Text Reader
Extracts text from running applications using the Windows UI Automation (UIA)
accessibility tree. NO screenshot, NO OCR needed.

For web browsers (Chrome, Edge), falls back to Playwright CDP to get actual
page content rather than the browser chrome UI text.

Two tools:
  1. get_app_text_content(app_name) — full text from a named app window
  2. get_active_window_info()       — structured info about the focused window
"""
import logging

logger = logging.getLogger(__name__)


def _extract_uia_text(win) -> str:
    """Walk a pywinauto UIA window and collect all unique non-empty text strings."""
    texts = []
    for ctrl in win.descendants():
        try:
            t = ctrl.window_text()
            if t and t.strip() and len(t.strip()) > 1:
                texts.append(t.strip())
        except Exception:
            pass

    # Deduplicate while preserving order
    seen = set()
    unique = []
    for t in texts:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return "\n".join(unique)


def _is_browser(title: str) -> bool:
    """Check if the window title suggests a web browser."""
    title_l = title.lower()
    return any(kw in title_l for kw in ["chrome", "edge", "firefox", "brave", "opera", "vivaldi"])


async def _get_browser_content_via_playwright() -> str:
    """
    Extract page content from the currently open Playwright browser session.
    If no Playwright session is active, return a helpful message.
    """
    try:
        from ..playwright_browser import browser_manager, playwright_get_content
        if browser_manager.page is None:
            return (
                "No active Playwright browser session. "
                "Use playwright_navigate(url) first, or ask me to navigate to the page."
            )
        return await playwright_get_content()
    except Exception as e:
        return f"ERROR reading browser content via Playwright: {e}"


async def get_app_text_content(app_name: str = None) -> str:
    """
    Extract ALL readable text from a running application window without taking
    a screenshot or using OCR. Uses the Windows UI Automation accessibility tree.

    For web browsers (Chrome, Edge, etc.), automatically uses Playwright CDP
    to retrieve the actual page content, not just the browser UI elements.

    Args:
        app_name (str): Keyword matching the window title
                        (e.g. 'notepad', 'word', 'excel', 'chrome', 'calculator').
                        If None or empty, reads the currently active/focused window.

    Returns: Plain text with all text found in the window, or an error message.

    Examples of what this can read:
    - Notepad: The full document text
    - Calculator: Current display value and button labels
    - Word: Paragraph text visible in the window
    - Chrome/Edge: Full web page content via Playwright
    - Any dialog box: All label texts, field values, button names
    """
    import asyncio
    import pygetwindow as gw

    loop = asyncio.get_event_loop()

    # Determine target window title
    target_title = app_name.strip() if app_name else None
    if not target_title:
        active = gw.getActiveWindow()
        if not active:
            return "ERROR: No active window detected."
        target_title = active.title

    # Browser detection → use Playwright for real page content
    if _is_browser(target_title):
        logger.info(f"get_app_text_content: browser detected ('{target_title}'), using Playwright.")
        return await _get_browser_content_via_playwright()

    # UIA tree walk — run sync pywinauto in thread pool
    def _do_uia_read():
        try:
            import re as _re
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            wins = desktop.windows(title_re=f"(?i).*{_re.escape(target_title[:30])}.*", visible_only=True)
            if not wins:
                return f"No visible window found matching '{target_title}'."
            win = wins[0]
            actual_title = win.window_text() or target_title
            result = _extract_uia_text(win)
            return f"[Window: {actual_title}]\n{result}" if result else f"No readable text in '{actual_title}'."
        except ImportError:
            return "ERROR: pywinauto is not installed. Run: pip install pywinauto"
        except Exception as e:
            return f"ERROR reading app text via UIA: {e}"

    return await loop.run_in_executor(None, _do_uia_read)


async def get_active_window_info() -> str:
    """
    Returns structured information about the currently focused window:
    - Window title and process name
    - All text content (via UIA or Playwright for browsers)
    - Interactive elements: buttons, text fields, menu items

    Use this before interacting with an app to understand its current state.
    No screenshot or OCR is used.

    Returns: A formatted multi-line string with the window info.
    """
    import asyncio
    import pygetwindow as gw
    import psutil
    import subprocess

    loop = asyncio.get_event_loop()

    active = gw.getActiveWindow()
    if not active:
        return "ERROR: No active window detected."

    title = active.title
    pos   = f"Position: ({active.left}, {active.top}), Size: {active.width}×{active.height}px"

    # Get process name by window title using powershell
    proc_name = "unknown"
    try:
        safe_title = title[:25].replace("'", "''")
        ps_cmd = (
            f"powershell -Command \""
            f"Get-Process | Where-Object {{$_.MainWindowTitle -like '*{safe_title}*'}} "
            f"| Select-Object -First 1 Name | ConvertTo-Json\""
        )
        ps_result = subprocess.run(ps_cmd, capture_output=True, text=True, shell=True, timeout=5)
        if ps_result.stdout.strip():
            import json
            proc_data = json.loads(ps_result.stdout)
            if isinstance(proc_data, dict):
                proc_name = proc_data.get("Name", "unknown")
    except Exception:
        pass

    header = f"Active Window: {title}\nProcess: {proc_name}\n{pos}\n"

    # Browser → use Playwright
    if _is_browser(title):
        browser_content = await _get_browser_content_via_playwright()
        return header + "\n--- BROWSER PAGE CONTENT (via Playwright) ---\n" + browser_content

    # UIA walk for structured info
    def _do_structured_read():
        try:
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            wins = desktop.windows(title_re=f".*{title[:30]}.*", visible_only=True)
            if not wins:
                return header + "No UIA window found."

            win = wins[0]
            buttons, edits, menus, other_texts = [], [], [], []

            for ctrl in win.descendants():
                try:
                    t = ctrl.window_text()
                    if not t or not t.strip():
                        continue
                    t = t.strip()
                    ct = ctrl.element_info.control_type
                    if ct == "Button":
                        buttons.append(t)
                    elif ct in ("Edit", "Document"):
                        edits.append(t[:150])
                    elif ct in ("MenuItem", "Menu"):
                        menus.append(t)
                    elif len(t) > 1:
                        other_texts.append(t)
                except Exception:
                    pass

            # Deduplicate
            def dedup(lst):
                seen, out = set(), []
                for x in lst:
                    if x not in seen:
                        seen.add(x)
                        out.append(x)
                return out

            lines = [header]
            if buttons:
                lines.append(f"--- BUTTONS ({len(dedup(buttons))}) ---\n" + ", ".join(dedup(buttons)))
            if edits:
                lines.append(f"--- TEXT FIELDS ---\n" + "\n".join(dedup(edits)))
            if menus:
                lines.append(f"--- MENU ITEMS ---\n" + ", ".join(dedup(menus)[:20]))
            if other_texts:
                lines.append(f"--- OTHER TEXT ---\n" + "\n".join(dedup(other_texts)[:40]))
            if not (buttons or edits or menus or other_texts):
                lines.append("No interactive elements found via UIA.")
            return "\n\n".join(lines)

        except ImportError:
            return header + "ERROR: pywinauto not installed. Run: pip install pywinauto"
        except Exception as e:
            return header + f"ERROR reading UIA tree: {e}"

    return await loop.run_in_executor(None, _do_structured_read)
