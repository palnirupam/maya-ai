import uuid
import logging
import asyncio
from typing import Dict, Any

logger = logging.getLogger(__name__)

class ToolPlanner:
    """
    Intercepts LLM tool calls and queues them for user approval.
    """
    def __init__(self):
        # Maps request_id -> Pending Tool Call Details
        self.approval_queue: Dict[str, Any] = {}

    def queue_tool(self, tool_name: str, payload: dict, risk_level: str = "safe") -> dict:
        """
        Creates a pending tool request and returns a payload to be sent via WebSocket
        to the frontend ToolApprovalCard.
        """
        request_id = str(uuid.uuid4())
        
        request_data = {
            "request_id": request_id,
            "tool_name": tool_name,
            "payload": payload,
            "risk_level": risk_level,
            "status": "pending",
            "future": asyncio.Future()
        }
        
        self.approval_queue[request_id] = request_data
        logger.info(f"Tool {tool_name} queued for approval. ID: {request_id}")
        
        # Return a safe copy without the future
        return {k: v for k, v in request_data.items() if k != "future"}

    async def wait_for_approval(self, request_id: str) -> bool:
        """Blocks until resolve_tool is called by the frontend websocket handler."""
        if request_id not in self.approval_queue:
            return False
        
        try:
            # Wait up to 60 seconds for user to click
            return await asyncio.wait_for(self.approval_queue[request_id]["future"], timeout=60.0)
        except asyncio.TimeoutError:
            logger.warning(f"Tool request {request_id} timed out waiting for user approval.")
            return False

    def resolve_tool(self, request_id: str, approved: bool) -> Any:
        """Called when the frontend sends back an [Approve] or [Deny] event."""
        if request_id not in self.approval_queue:
            return {"status": "error", "message": "Request ID not found or expired."}
            
        request = self.approval_queue.pop(request_id)
        if not request["future"].done():
            request["future"].set_result(approved)
            
        if not approved:
            return {"status": "denied", "message": "User denied the operation."}
            
        return {"status": "executed", "message": "Operation approved."}

tool_planner = ToolPlanner()
