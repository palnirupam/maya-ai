"""
Maya AI — Google Meet Integration
Automates joining and leaving Google Meet sessions using Playwright.
"""
import logging
import asyncio
from backend.tools.desktop.advanced.playwright_browser import browser_manager

logger = logging.getLogger(__name__)

async def google_meet_join(meeting_url: str, camera_on: bool = False, mic_on: bool = False) -> str:
    """
    Automatically opens the browser and joins a Google Meet link.
    Args:
        meeting_url (str): The Google Meet URL (e.g. 'meet.google.com/abc-defg-hij').
        camera_on (bool): Whether the camera should be ON. Default is False (OFF).
        mic_on (bool): Whether the microphone should be ON. Default is False (OFF).
    """
    if isinstance(camera_on, str): camera_on = camera_on.lower() == 'true'
    if isinstance(mic_on, str): mic_on = mic_on.lower() == 'true'
    
    if not meeting_url.startswith("http"):
        meeting_url = "https://" + meeting_url

    try:
        # We need headed mode for Meet so the user can participate
        await browser_manager.start(headless=False)
        page = browser_manager.page
        
        # Grant permissions for camera and microphone automatically
        await browser_manager._context.grant_permissions(["camera", "microphone"], origin="https://meet.google.com")
        
        await page.goto(meeting_url, wait_until="load")
        await asyncio.sleep(3)  # Wait for UI elements to load
        
        # Toggle Mic and Camera before joining if they are not in the desired state
        # Meet usually starts with them based on previous preference, so we use shortcuts
        # We assume they default to ON or we can just send the shortcut to toggle if needed
        # It's safer to click the explicit mute/video buttons if we can find them
        try:
            # Turn off mic if requested
            if not mic_on:
                mic_btn = page.get_by_label("Turn off microphone")
                if await mic_btn.count() > 0:
                    await mic_btn.first.click()
            
            # Turn off camera if requested
            if not camera_on:
                cam_btn = page.get_by_label("Turn off camera")
                if await cam_btn.count() > 0:
                    await cam_btn.first.click()
        except Exception as e:
            logger.warning(f"Could not toggle A/V before joining: {e}")
            
        # Click Join
        join_btn = page.get_by_text("Join now")
        ask_btn = page.get_by_text("Ask to join")
        
        if await join_btn.count() > 0:
            await join_btn.first.click()
            await browser_manager.save_state()
            return f"SUCCESS: Joined Google Meet ({meeting_url}). Camera={'ON' if camera_on else 'OFF'}, Mic={'ON' if mic_on else 'OFF'}."
        elif await ask_btn.count() > 0:
            await ask_btn.first.click()
            await browser_manager.save_state()
            return f"SUCCESS: Asked to join Google Meet ({meeting_url}). Waiting for host to admit you. Camera={'ON' if camera_on else 'OFF'}, Mic={'ON' if mic_on else 'OFF'}."
        else:
            return f"SUCCESS: Opened Google Meet ({meeting_url}), but could not find the Join button. You may need to log in first."
            
    except Exception as e:
        return f"ERROR joining Google Meet: {e}"

async def google_meet_leave() -> str:
    """Leaves the current Google Meet call."""
    if not browser_manager.page:
        return "ERROR: Browser is not open."
    try:
        page = browser_manager.page
        leave_btn = page.get_by_label("Leave call")
        if await leave_btn.count() > 0:
            await leave_btn.first.click()
            await asyncio.sleep(1)
            await page.close()
            return "SUCCESS: Left the Google Meet call."
        else:
            await page.close()
            return "SUCCESS: Closed the browser tab (could not find explicit leave button)."
    except Exception as e:
        return f"ERROR leaving Google Meet: {e}"
