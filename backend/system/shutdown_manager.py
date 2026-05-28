import os
import signal
import asyncio
import logging
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

    async def trigger_sleep(self):
        logger.info("Entering sleep mode...")
        # Tell frontend to switch to a standby state (mute mic, dim orb)
        await manager.broadcast_event("status_update", {"appState": "offline"})
        return "System is now in standby sleep mode."

shutdown_manager = ShutdownManager()
