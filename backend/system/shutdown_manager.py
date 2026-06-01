import os
import signal
import asyncio
import logging
import subprocess
from ..api.websocket.manager import manager

logger = logging.getLogger(__name__)

class ShutdownManager:
    """
    Handles graceful system termination and sleep mode transitions.
    """
    async def trigger_shutdown(self):
        logger.info("Initiating graceful shutdown sequence...")
        
        # 1. Notify frontend to close its window
        await manager.broadcast_event("app_shutdown", {"message": "Shutting down..."})
        
        # 2. Wait for message to flush
        await asyncio.sleep(1)
        
        # 3. Disconnect all WebSockets
        for connection in manager.active_connections:
            await connection.close(code=1000, reason="System Shutdown")
            
        manager.active_connections.clear()
        logger.info("All connections closed. Terminating process.")
        
        # 4. Trigger Uvicorn graceful shutdown via SIGTERM
        os.kill(os.getpid(), signal.SIGTERM)

    async def trigger_windows_shutdown(self, delay_seconds: int = 10):
        """
        Closes Chrome/browsers first, then shuts down Windows.
        Called when user confirms shutdown from Telegram.
        """
        logger.info("Initiating Windows shutdown sequence...")

        # 1. Close browsers and common apps (gracefully, ignore errors)
        apps_to_close = ["chrome.exe", "firefox.exe", "msedge.exe", "notepad.exe"]
        for app in apps_to_close:
            try:
                subprocess.run(["taskkill", "/f", "/im", app], capture_output=True)
            except Exception:
                pass

        # 2. Brief pause
        await asyncio.sleep(2)

        # 3. Schedule Windows shutdown
        subprocess.Popen(["shutdown", "/s", "/t", str(delay_seconds)])
        logger.info(f"Windows shutdown scheduled in {delay_seconds}s.")

    async def trigger_sleep(self):
        logger.info("Entering sleep mode...")
        await manager.broadcast_event("status_update", {"appState": "offline"})
        return "System is now in standby sleep mode."

shutdown_manager = ShutdownManager()
