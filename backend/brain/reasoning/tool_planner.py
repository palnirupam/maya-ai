import uuid
import logging
import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Any

from backend.database.connection import SessionLocal
from backend.database.models import PendingApproval
from backend.security.risk_classifier import risk_classifier
from backend.security.audit_logger import (
    approval_display_payload,
    audit_logger,
    redact_approval_payload,
)

logger = logging.getLogger(__name__)

APPROVAL_TIMEOUT_SECONDS = 300.0

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
        
        # A caller marks a tool as danger only when explicit approval is
        # required. Keep that contract HIGH even if the classifier misses a
        # new tool name, so auto-approve cannot become an accidental bypass.
        if str(risk_level).strip().lower() == "danger" and actual_risk in {"LOW", "MEDIUM"}:
            actual_risk = "HIGH"

        persisted_payload = redact_approval_payload(payload or {}, tool_name)
        request_data = {
            "request_id": request_id,
            "tool_name": tool_name,
            "payload": approval_display_payload(payload or {}, tool_name),
            "risk_level": actual_risk,
            "status": "pending",
        }
        
        # 1. Save to SQLite
        db = None
        persisted = False
        try:
            db = SessionLocal()
            now = datetime.now(timezone.utc)
            db.query(PendingApproval).filter(
                PendingApproval.status == "pending",
                PendingApproval.expires_at < now,
            ).update({"status": "expired"}, synchronize_session=False)
            expires_at = now + timedelta(seconds=APPROVAL_TIMEOUT_SECONDS)
            db_req = PendingApproval(
                request_id=request_id,
                tool_name=tool_name,
                payload=persisted_payload,
                risk_level=actual_risk,
                status="pending",
                expires_at=expires_at
            )
            db.add(db_req)
            db.commit()
            persisted = True
        except Exception as e:
            if db is not None:
                try:
                    db.rollback()
                except Exception:
                    pass
            logger.error("Failed to persist approval request (%s).", type(e).__name__)
        finally:
            if db is not None:
                db.close()

        if not persisted:
            request_data["status"] = "error"
            return request_data

        # 2. Store Future in memory
        self._memory_futures[request_id] = {
            "future": asyncio.get_running_loop().create_future(),
            "created_at_ts": time.monotonic()
        }
        
        logger.info(f"Tool {tool_name} queued for approval (Risk: {actual_risk}). ID: {request_id}")
        return request_data

    async def wait_for_approval(self, request_id: str) -> bool:
        """Blocks until resolve_tool is called."""
        if request_id not in self._memory_futures:
            # A persisted decision must never resurrect an operation after the
            # process that created it has gone away.
            db = None
            try:
                db = SessionLocal()
                req = db.query(PendingApproval).filter_by(request_id=request_id).first()
                logger.warning(
                    "[ToolPlanner] request_id %s is not active in memory (db_status=%s). Denying.",
                    request_id,
                    getattr(req, "status", "missing"),
                )
                # Status is still "pending" or not found → unknown request, deny for safety
                return False
            except Exception as e:
                logger.error(
                    "Approval lookup failed for an inactive request (%s). Denying.",
                    type(e).__name__,
                )
                return False
            finally:
                if db is not None:
                    db.close()
            
        future_data = self._memory_futures[request_id]
        
        try:
            # Wait up to 5 minutes for user to click Approve/Deny
            return await asyncio.wait_for(
                future_data["future"], timeout=APPROVAL_TIMEOUT_SECONDS
            )
        except asyncio.TimeoutError:
            logger.warning(f"Tool request {request_id} timed out waiting for user approval. Auto-denying.")
            return False
        finally:
            self._memory_futures.pop(request_id, None)

    def resolve_tool(self, request_id: str, approved: bool, user_id: str = "local_ui") -> Any:
        """Called when the user sends back an [Approve] or [Deny] event."""
        
        status_str = "approved" if approved else "denied"
        tool_name = "unknown"
        payload = {}
        risk_level = "unknown"
        existing_status = None
        db_error = False
        
        known_in_memory = request_id in self._memory_futures
        found_in_db = False

        # 1. Update DB
        db = None
        try:
            db = SessionLocal()
            req = db.query(PendingApproval).filter_by(request_id=request_id).first()
            if req:
                found_in_db = True
                tool_name = req.tool_name
                payload = req.payload
                risk_level = req.risk_level
                existing_status = req.status
                if existing_status != "pending":
                    approved = False
                    status_str = existing_status or "inactive"
                else:
                    if not known_in_memory:
                        # The process that owned this operation is gone. Keep a
                        # stale click from creating a misleading approved record.
                        approved = False
                        status_str = "expired"
                    else:
                        expires_at = req.expires_at
                        if expires_at is not None:
                            if expires_at.tzinfo is None:
                                expires_at = expires_at.replace(tzinfo=timezone.utc)
                            if expires_at <= datetime.now(timezone.utc):
                                approved = False
                                status_str = "expired"
                    req.status = status_str
                    db.commit()
        except Exception as e:
            db_error = True
            logger.error("Failed to update approval request (%s).", type(e).__name__)
        finally:
            if db is not None:
                db.close()

        if db_error:
            if known_in_memory:
                future_data = self._memory_futures[request_id]
                if not future_data["future"].done():
                    future_data["future"].set_result(False)
            return {"status": "error", "message": "Approval could not be recorded."}

        if not found_in_db:
            logger.warning("Rejected resolution for unknown approval request %s", request_id)
            if known_in_memory:
                future_data = self._memory_futures[request_id]
                if not future_data["future"].done():
                    future_data["future"].set_result(False)
            return {"status": "unknown", "message": "Approval request is no longer active."}

        if existing_status and existing_status != "pending":
            if known_in_memory:
                future_data = self._memory_futures[request_id]
                if not future_data["future"].done():
                    future_data["future"].set_result(False)
            return {
                "status": existing_status,
                "message": "Approval request is no longer pending.",
            }

        # 2. Resolve memory future
        latency_ms = 0
        if known_in_memory:
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
            message = (
                "Approval request expired."
                if status_str == "expired"
                else "User denied the operation."
            )
            return {"status": status_str, "message": message}

        return {"status": "executed", "message": "Operation approved."}

tool_planner = ToolPlanner()
