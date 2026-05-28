from fastapi import WebSocket
from typing import List, Dict
import json
import logging

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total clients: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            logger.info(f"Client disconnected. Total clients: {len(self.active_connections)}")

    async def send_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception as e:
                logger.error(f"Error broadcasting message: {e}")

    async def broadcast_event(self, event_type: str, data: Dict):
        message = json.dumps({"type": event_type, "data": data})
        await self.broadcast(message)

    async def send_personal_event(self, event_type: str, data: Dict, websocket: WebSocket):
        message = json.dumps({"type": event_type, "data": data})
        try:
            await self.send_message(message, websocket)
        except Exception as e:
            logger.error(f"Error sending personal message: {e}")

manager = ConnectionManager()
