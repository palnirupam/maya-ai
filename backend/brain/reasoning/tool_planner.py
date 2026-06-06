import uuid
import logging
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from backend.database.connection import SessionLocal
from backend.database.models import PendingApproval
from backend.security.risk_classifier import risk_classifier
from backend.security.audit_logger import audit_logger

logger = logging.getLogger(__name__)

class ToolPlanner:
    """
    Intercepts LLM tool calls and queues them for user approval.
    """
    def __init__(self):
        # Maps request_id -> Future
        # We only keep the futures in memory. The actual data lives in the DB.
        self._memory_futures: Dict[str, dict] = {}

    def queue_tool(self, tool_name: str, payload: dict, risk_level: str = "safe") -> dict:
        """
        Creates a pending tool request in SQLite and returns a payload to be sent via WebSocket
        or Telegram.
        """
        request_id = str(uuid.uuid4())
        actual_risk = risk_classifier.classify(tool_name, payload)
        
        # Override if explicitly marked higher
        if risk_level == "danger" and actual_risk in ["LOW"]:
            actual_risk = "MEDIUM"

        request_data = {
            "request_id": request_id,
            "tool_name": tool_name,
            "payload": payload,
            "risk_level": actual_risk,
            "status": "pending",
        }
        
        # 1. Save to SQLite
        try:
            db = SessionLocal()
            expires_at = datetime.now(timezone.utc) + timedelta(hours=24)
            db_req = PendingApproval(
                request_id=request_id,
                tool_name=tool_name,
                payload=payload,
                risk_level=actual_risk,
                status="pending",
                expires_at=expires_at
            )
            db.add(db_req)
            db.commit()
        except Exception as e:
            logger.error(f"Failed to save PendingApproval to DB: {e}")
        finally:
            db.close()

        # 2. Store Future in memory
        self._memory_futures[request_id] = {
            "future": asyncio.Future(),
            "created_at_ts": time.monotonic()
        }
        
        logger.info(f"Tool {tool_name} queued for approval (Risk: {actual_risk}). ID: {request_id}")
        return request_data

    async def wait_for_approval(self, request_id: str) -> bool:
        """Blocks until resolve_tool is called."""
        if request_id not in self._memory_futures:
            # This request_id is unknown to memory (e.g., server restarted mid-approval).
            # Check DB for the EXACT request_id to see if it was already resolved.
            try:
                db = SessionLocal()
                req = db.query(PendingApproval).filter_by(request_id=request_id).first()
                if req and req.status == "approved":
                    return True
                elif req and req.status == "denied":
                    return False
                # Status is still "pending" or not found → unknown request, deny for safety
                logger.warning(f"[ToolPlanner] request_id {request_id} not in memory and not resolved in DB. Denying for safety.")
                return False
            finally:
                db.close()
            
        future_data = self._memory_futures[request_id]
        
        try:
            # Wait up to 5 minutes for user to click Approve/Deny
            return await asyncio.wait_for(future_data["future"], timeout=300.0)
        except asyncio.TimeoutError:
            logger.warning(f"Tool request {request_id} timed out waiting for user approval. Auto-denying.")
            return False
        finally:
            self._memory_futures.pop(request_id, None)

    def resolve_tool(self, request_id: str, approved: bool, user_id: str = "telegram_user") -> Any:
        """Called when the user sends back an [Approve] or [Deny] event."""
        
        status_str = "approved" if approved else "denied"
        tool_name = "unknown"
        payload = {}
        risk_level = "unknown"
        
        # 1. Update DB
        try:
            db = SessionLocal()
            req = db.query(PendingApproval).filter_by(request_id=request_id).first()
            if req:
                req.status = status_str
                tool_name = req.tool_name
                payload = req.payload
                risk_level = req.risk_level
                db.commit()
        except Exception as e:
            logger.error(f"Failed to update PendingApproval in DB: {e}")
        finally:
            db.close()

        # 2. Resolve memory future
        latency_ms = 0
        if request_id in self._memory_futures:
            future_data = self._memory_futures[request_id]
            latency_ms = int((time.monotonic() - future_data["created_at_ts"]) * 1000)
            if not future_data["future"].done():
                future_data["future"].set_result(approved)

        # 3. Write to Audit Log (JSONL)
        audit_logger.log_approval(
            request_id=request_id,
            tool_name=tool_name,
            payload=payload,
            risk_level=risk_level,
            approved=approved,
            approved_by=user_id,
            latency_ms=latency_ms
        )
            
        if not approved:
            return {"status": "denied", "message": "User denied the operation."}
            
        return {"status": "executed", "message": "Operation approved."}

tool_planner = ToolPlanner()
