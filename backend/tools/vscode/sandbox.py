import os
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

class WorkspaceSandbox:
    """
    Enforces strict path isolation for file modifications.
    """
    def __init__(self, allowed_root: str = "C:/maya-workspaces/"):
        self.allowed_root = Path(allowed_root).resolve()
        
    def is_path_allowed(self, target_path: str) -> bool:
        """
        Check if the target path resides strictly within the ALLOWED_ROOT.
        Prevents directory traversal (e.g., ../../../Windows/System32).
        """
        try:
            resolved_target = Path(target_path).resolve()
            # Ensure the resolved target starts with the allowed root
            if self.allowed_root in resolved_target.parents or resolved_target == self.allowed_root:
                return True
            return False
        except Exception as e:
            logger.error(f"Sandbox resolution error: {e}")
            return False

sandbox = WorkspaceSandbox()
