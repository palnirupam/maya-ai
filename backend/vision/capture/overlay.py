import logging
from winotify import Notification

logger = logging.getLogger(__name__)

def show_toast_notification(app_name: str):
    """
    Shows a native Windows 10/11 Toast Notification to inform the user
    that Maya is actively inspecting the screen.
    """
    try:
        toast = Notification(
            app_id="Maya AI",
            title="Privacy Alert 👁️",
            msg=f"Maya is currently inspecting: {app_name}",
            duration="short"
        )
        # Note: winotify is blocking when show() is called, but it's very fast for "short".
        # If it blocks too much, we may need to thread it.
        toast.show()
    except Exception as e:
        logger.error(f"Failed to show toast notification: {e}")

if __name__ == "__main__":
    show_toast_notification("VS Code")
