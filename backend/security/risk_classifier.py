import re
import json

class RiskClassifier:
    """Classifies terminal commands and tool calls into risk levels."""
    
    CRITICAL_PATTERNS = [
        r"rm\s+-rf",
        r"del\s+/s",
        r"format\s+[a-z]:",
        r"diskpart",
        r"taskkill\s+/f",
    ]
    
    HIGH_PATTERNS = [
        r"git\s+push",
        r"npm\s+publish",
        r"pip\s+install",
        r"npm\s+install\s+-g",
        r"winget\s+install",
        r"shutdown",
        r"reboot",
    ]
    
    MEDIUM_PATTERNS = [
        r"npm\s+install",
        r"pip\s+uninstall",
        r"git\s+commit",
        r"git\s+add",
        r"curl",
        r"wget",
    ]

    def classify(self, tool_name: str, payload: dict) -> str:
        """Returns LOW, MEDIUM, HIGH, or CRITICAL."""
        if tool_name == "permanent_delete_email":
            return "CRITICAL"
        if tool_name == "trash_background_email":
            return "HIGH"
            
        if tool_name not in ["execute_powershell", "execute_python", "run_terminal_command"]:
            return "LOW"
            
        cmd = ""
        if tool_name == "execute_powershell" or tool_name == "run_terminal_command":
            cmd = payload.get("command", "").lower()
        elif tool_name == "execute_python":
            cmd = payload.get("code", "").lower()
            
        if not cmd:
            return "LOW"
            
        for pattern in self.CRITICAL_PATTERNS:
            if re.search(pattern, cmd):
                return "CRITICAL"
                
        for pattern in self.HIGH_PATTERNS:
            if re.search(pattern, cmd):
                return "HIGH"
                
        for pattern in self.MEDIUM_PATTERNS:
            if re.search(pattern, cmd):
                return "MEDIUM"
                
        # Anything else running in shell is at least LOW
        return "LOW"

risk_classifier = RiskClassifier()
