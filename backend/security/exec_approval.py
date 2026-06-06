import asyncio
import uuid
import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)

class ApprovalRequest:
    def __init__(self, command: str, reason: str):
        self.id = str(uuid.uuid4())[:8]
        self.command = command
        self.reason = reason
        self.event = asyncio.Event()
        self.approved = False

class ExecApprovalManager:
    def __init__(self):
        self.pending_requests: Dict[str, ApprovalRequest] = {}
        # Callback to notify external systems (like Telegram)
        self.on_request_created = None
        
    def create_request(self, command: str, reason: str = "Automated execution") -> ApprovalRequest:
        req = ApprovalRequest(command, reason)
        self.pending_requests[req.id] = req
        if self.on_request_created:
            try:
                # Fire and forget notification
                asyncio.create_task(self.on_request_created(req))
            except Exception as e:
                logger.error(f"Failed to notify approval request: {e}")
        return req
        
    def approve(self, req_id: str) -> bool:
        if req_id in self.pending_requests:
            req = self.pending_requests[req_id]
            req.approved = True
            req.event.set()
            return True
        return False
        
    def deny(self, req_id: str) -> bool:
        if req_id in self.pending_requests:
            req = self.pending_requests[req_id]
            req.approved = False
            req.event.set()
            return True
        return False
        
    def remove_request(self, req_id: str):
        self.pending_requests.pop(req_id, None)

exec_approval_manager = ExecApprovalManager()
