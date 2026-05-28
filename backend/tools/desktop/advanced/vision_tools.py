"""
Maya AI — Vision-Guided Interaction Tools
Find UI elements by text/description and interact with them using OCR.
"""
import time
import logging

logger = logging.getLogger(__name__)


def find_and_click(text: str, timeout: float = 5.0) -> str:
    """
    Finds a UI element by its visible text on screen and clicks it using OCR.
    More reliable than fixed coordinates — works even if UI shifts.
    Args:
        text (str): The exact or partial text label of the button/element to click.
        timeout (float): How many seconds to wait for the element to appear (default 5).
    """
    import pyautogui
    from backend.vision.capture.screen_capture import screen_capture
    from backend.vision.ocr.ocr_engine import ocr_engine

    deadline = time.time() + timeout
    while time.time() < deadline:
        img, monitor = screen_capture.capture_as_pil()
        if not img or not monitor:
            time.sleep(0.5)
            continue

        processed = ocr_engine.preprocess_image(img)
        coords = ocr_engine.find_text_coordinates(processed, text, fuzzy_threshold=0.7)
        if coords:
            x = monitor["left"] + coords[0]
            y = monitor["top"] + coords[1]
            logger.info(f"find_and_click: found '{text}' at screen ({x}, {y})")
            pyautogui.moveTo(x, y, duration=0.3)
            time.sleep(0.15)
            pyautogui.click()
            return f"SUCCESS: Clicked '{text}' at ({x}, {y})."
        time.sleep(0.5)

    return f"ERROR: Could not find '{text}' on screen within {timeout}s."


def wait_for_element(text: str, timeout: float = 8.0) -> str:
    """
    Waits until a specific text element appears on screen (e.g. waiting for an app to load).
    Args:
        text (str): The text to wait for on screen.
        timeout (float): Maximum seconds to wait (default 8).
    """
    from backend.vision.capture.screen_capture import screen_capture
    from backend.vision.ocr.ocr_engine import ocr_engine

    deadline = time.time() + timeout
    while time.time() < deadline:
        img, monitor = screen_capture.capture_as_pil()
        if img:
            processed = ocr_engine.preprocess_image(img)
            coords = ocr_engine.find_text_coordinates(processed, text, fuzzy_threshold=0.7)
            if coords:
                return f"SUCCESS: Element '{text}' is visible on screen."
        time.sleep(0.6)

    return f"TIMEOUT: '{text}' did not appear within {timeout}s."


def read_active_window_title() -> str:
    """
    Returns the title of the currently focused/active window.
    Useful to know which app is in the foreground before taking action.
    """
    try:
        import pygetwindow as gw
        win = gw.getActiveWindow()
        if win:
            return f"Active window: '{win.title}'"
        return "No active window detected."
    except Exception as e:
        return f"ERROR: {e}"


def is_app_open(app_name: str) -> str:
    """
    Checks whether a specific application is currently running.
    Args:
        app_name (str): The name of the app to check (e.g. 'WhatsApp', 'Chrome').
    """
    try:
        import pygetwindow as gw
        windows = gw.getAllWindows()
        name_lower = app_name.lower()
        for w in windows:
            if name_lower in w.title.lower():
                state = "minimized" if w.isMinimized else "open"
                return f"YES: '{app_name}' is {state} (window: '{w.title}')."
        return f"NO: '{app_name}' does not appear to be open."
    except Exception as e:
        return f"ERROR: {e}"


def take_verified_screenshot() -> str:
    """
    Captures a screenshot to verify the current state of the screen after taking an action.
    Use this after opening an app, clicking a button, or navigating somewhere to confirm it worked.
    Returns screenshot data as base64.
    """
    from backend.vision.capture.screen_capture import screen_capture
    result = screen_capture.capture_as_base64()
    if result == "ERROR_SENSITIVE_APP":
        return "BLOCKED: Sensitive app on screen. Cannot capture screenshot."
    if result:
        return f"SCREENSHOT_BASE64:{result}"
    return "ERROR: Could not capture screenshot."
