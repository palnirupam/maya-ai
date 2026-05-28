import pyautogui
import logging

logger = logging.getLogger(__name__)

# Configure PyAutoGUI for safety
pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.5 # Add a small pause between actions

class MouseTools:
    """
    Wrappers for PyAutoGUI mouse functions.
    Exposed to Gemini for automation.
    """
    @staticmethod
    def move_to(x: int, y: int):
        logger.info(f"Moving mouse to ({x}, {y})")
        pyautogui.moveTo(x, y, duration=0.5)
        return f"Mouse moved to {x}, {y}."

    @staticmethod
    def click():
        logger.info("Clicking mouse")
        pyautogui.click()
        return "Mouse clicked."

    @staticmethod
    def double_click():
        logger.info("Double clicking mouse")
        pyautogui.doubleClick()
        return "Mouse double-clicked."

    @staticmethod
    def get_position():
        x, y = pyautogui.position()
        return f"Mouse is currently at {x}, {y}."

mouse_tools = MouseTools()
