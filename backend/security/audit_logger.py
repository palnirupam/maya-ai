import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class AuditLogger:
    """Writes machine-readable audit logs in JSONL format."""
    def __init__(self, log_dir: str = "logs"):
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.log_file = os.path.join(self.log_dir, "audit.jsonl")

    def log_approval(self, request_id: str, tool_name: str, payload: dict, risk_level: str, approved: bool, approved_by: str, latency_ms: int):
        entry = {
            "ts": datetime.utcnow().isoformat() + "Z",
            "request_id": request_id,
            "tool": tool_name,
            "payload": payload,
            "risk": risk_level,
            "approved": approved,
            "approved_by": approved_by,
            "approval_latency_ms": latency_ms
        }
        
        try:
            with open(self.log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to write audit log: {e}")

audit_logger = AuditLogger()
