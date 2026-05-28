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
