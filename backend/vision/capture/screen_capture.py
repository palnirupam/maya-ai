import base64
import io
import logging
from PIL import Image
import mss
import pygetwindow as gw
from .overlay import show_toast_notification

SENSITIVE_KEYWORDS = [
    "bitwarden", "1password", "lastpass", "dashlane", "keeper", 
    "bank", "banking", "otp", "password", "auth", "login", "credential"
]

logger = logging.getLogger(__name__)

class ScreenCapture:
    """
    Utility for capturing the desktop screen or active window using mss.
    """
    @staticmethod
    def capture_as_base64() -> str:
        try:
            with mss.mss() as sct:
                # Try to get active window
                active_window = gw.getActiveWindow()
                if active_window and active_window.title and active_window.width > 0 and active_window.height > 0:
                    # Security Check: Sensitive App Detection
                    title_lower = active_window.title.lower()
                    if any(kw in title_lower for kw in SENSITIVE_KEYWORDS):
                        logger.warning(f"Sensitive app detected ('{active_window.title}'). Capture aborted.")
                        return "ERROR_SENSITIVE_APP"

                    # Capture specific region (the active window)
                    monitor = {
                        "top": active_window.top, 
                        "left": active_window.left, 
                        "width": active_window.width, 
                        "height": active_window.height
                    }
                    sct_img = sct.grab(monitor)
                    
                    # Notify user
                    show_toast_notification(active_window.title)
                else:
                    # Fallback to primary monitor
                    sct_img = sct.grab(sct.monitors[1])
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                
                # Resize if it's too large to save bandwidth (e.g. 1080p max width)
                max_width = 1920
                if img.width > max_width:
                    ratio = max_width / img.width
                    new_size = (max_width, int(img.height * ratio))
                    img = img.resize(new_size, Image.Resampling.LANCZOS)
                
                # Save to an in-memory bytes buffer as JPEG
                buffer = io.BytesIO()
                img.save(buffer, format="JPEG", quality=75)
                
                # Encode to base64 string
                img_str = base64.b64encode(buffer.getvalue()).decode('utf-8')
                return img_str
        except Exception as e:
            logger.error(f"Failed to capture screen with mss: {e}")
            return ""

    @staticmethod
    def capture_as_pil():
        """
        Captures the screen and returns a tuple: (PIL.Image, monitor_dict)
        where monitor_dict contains 'top' and 'left' offsets for the active window.
        Returns (None, None) if sensitive app detected or on failure.
        """
        try:
            with mss.mss() as sct:
                active_window = gw.getActiveWindow()
                if active_window and active_window.title and active_window.width > 0 and active_window.height > 0:
                    title_lower = active_window.title.lower()
                    if any(kw in title_lower for kw in SENSITIVE_KEYWORDS):
                        logger.warning(f"Sensitive app detected ('{active_window.title}'). Capture aborted.")
                        return None, None

                    monitor = {
                        "top": active_window.top, 
                        "left": active_window.left, 
                        "width": active_window.width, 
                        "height": active_window.height
                    }
                    sct_img = sct.grab(monitor)
                    # We don't notify for OCR captures to avoid spamming the user on every click
                else:
                    monitor = sct.monitors[1] # Primary monitor
                    sct_img = sct.grab(monitor)
                
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                return img, monitor
        except Exception as e:
            logger.error(f"Failed to capture screen as PIL: {e}")
            return None, None

screen_capture = ScreenCapture()
