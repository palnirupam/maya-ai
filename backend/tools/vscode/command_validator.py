import re
import logging

logger = logging.getLogger(__name__)

class CommandValidator:
    """
    Scans proposed terminal commands and blocks dangerous execution.
    """
    def __init__(self):
        # List of dangerous patterns to block immediately
        self.blocked_patterns = [
            r"\brm\s+-rf\b",
            r"\bformat\b",
            r"\breg\s+add\b",
            r"\breg\s+delete\b",
            r"\bshutdown\b",
            r"\bdel\s+/f\s+/s\s+/q\b",
            r"\bcurl\s+.*?\|\s*bash\b",
            r"\bwget\s+.*?\|\s*bash\b",
            r"Invoke-WebRequest", # Block arbitrary remote execution fetching
        ]
        
    def is_safe(self, command: str) -> bool:
        """
        Checks command against blocked patterns.
        Returns True if safe, False if blocked.
        """
        cmd_lower = command.lower()
        for pattern in self.blocked_patterns:
            if re.search(pattern, cmd_lower):
                logger.warning(f"BLOCKED COMMAND: '{command}' matched dangerous pattern '{pattern}'")
                return False
        return True

command_validator = CommandValidator()
