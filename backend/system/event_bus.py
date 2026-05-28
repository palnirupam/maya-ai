import asyncio
import logging
from typing import Callable, Dict, List, Any

logger = logging.getLogger(__name__)

class EventBus:
    """
    Immutable Event Bus for the Adaptive Runtime.
    """
    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}

    def subscribe(self, event_type: str, callback: Callable):
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    async def publish(self, event_type: str, data: Any = None):
        logger.info(f"[EventBus] Emitting: {event_type}")
        if event_type in self._listeners:
            for callback in self._listeners[event_type]:
                if asyncio.iscoroutinefunction(callback):
                    asyncio.create_task(callback(data))
                else:
                    try:
                        callback(data)
                    except Exception as e:
                        logger.error(f"[EventBus] Error in callback for {event_type}: {e}")

system_event_bus = EventBus()
