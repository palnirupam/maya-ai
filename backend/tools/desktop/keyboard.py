import pyautogui
import logging

logger = logging.getLogger(__name__)

class KeyboardTools:
    """
    Wrappers for PyAutoGUI keyboard functions.
    Exposed to Gemini for automation.
    """
    @staticmethod
    def type_text(text: str):
        logger.info(f"Typing text: {text}")
        # pyautogui.write() silently drops non-ASCII (Bengali etc.) and can
        # garble text if focus shifts mid-typing. Clipboard-paste is instant
        # and Unicode-safe; fall back to write() only for plain ASCII.
        try:
            import pyperclip
            old_clip = None
            try:
                old_clip = pyperclip.paste()
            except Exception:
                pass
            pyperclip.copy(text)
            pyautogui.hotkey("ctrl", "v")
            if old_clip is not None:
                import threading
                threading.Timer(1.0, lambda: pyperclip.copy(old_clip)).start()
        except Exception:
            pyautogui.write(text, interval=0.05)
        return f"Typed: '{text}'"

    @staticmethod
    def press_key(key: str):
        logger.info(f"Pressing key: {key}")
        pyautogui.press(key)
        return f"Pressed key '{key}'"

    @staticmethod
    def hotkey(*keys):
        logger.info(f"Executing hotkey: {keys}")
        pyautogui.hotkey(*keys)
        return f"Executed hotkey '{keys}'"

keyboard_tools = KeyboardTools()
