import re


_RISK_ORDER = {"LOW": 0, "MEDIUM": 1, "HIGH": 2, "CRITICAL": 3}


def _higher_risk(left: str, right: str) -> str:
    return left if _RISK_ORDER.get(left, 0) >= _RISK_ORDER.get(right, 0) else right


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

    TOOL_RISKS = {
        # Arbitrary code execution and host-state changes are HIGH even when a
        # command string does not match one of the patterns below.
        "execute_python": "HIGH",
        "execute_powershell": "HIGH",
        "run_terminal_command": "HIGH",
        "delete_file": "HIGH",
        "manage_system_state": "HIGH",
        "manage_processes": "HIGH",
        "configure_mcp_server": "HIGH",
        "configure_gmail_credentials": "HIGH",
        "send_background_email": "HIGH",
        "execute_macro": "HIGH",
        "permanent_delete_email": "CRITICAL",
        "trash_background_email": "HIGH",
        "whatsapp_revoke_message": "HIGH",
        "close_apps_except": "HIGH",
    }

    ACTION_RISKS = {
        ("file", "delete"): "HIGH",
        ("file", "delete_by_name"): "CRITICAL",
        ("pc", "bt_remove"): "MEDIUM",
        ("pc", "hibernate"): "HIGH",
        ("pc", "process_kill"): "HIGH",
        ("pc", "restart"): "HIGH",
        ("pc", "shutdown"): "HIGH",
        ("pc", "sleep"): "HIGH",
        ("pc", "wifi_connect"): "MEDIUM",
        ("perform_shortcut", "hibernate"): "HIGH",
        ("perform_shortcut", "restart"): "HIGH",
        ("perform_shortcut", "shutdown"): "HIGH",
        ("perform_shortcut", "sleep"): "HIGH",
    }

    def classify(self, tool_name: str, payload: dict) -> str:
        """Returns LOW, MEDIUM, HIGH, or CRITICAL."""
        payload = payload if isinstance(payload, dict) else {}
        risk = self.TOOL_RISKS.get(tool_name, "LOW")

        action = (
            str(payload.get("action", ""))
            .strip()
            .lower()
            .replace(" ", "_")
            .replace("-", "_")
        )
        if action == "suspend":
            action = "sleep"
        action_risk = self.ACTION_RISKS.get((tool_name, action))
        if action_risk:
            risk = _higher_risk(risk, action_risk)
            
        if tool_name not in ["execute_powershell", "execute_python", "run_terminal_command"]:
            return risk
            
        cmd = ""
        if tool_name == "execute_powershell" or tool_name == "run_terminal_command":
            cmd = payload.get("command", "").lower()
        elif tool_name == "execute_python":
            cmd = payload.get("code", "").lower()
            
        if not cmd:
            return risk
            
        for pattern in self.CRITICAL_PATTERNS:
            if re.search(pattern, cmd):
                return _higher_risk(risk, "CRITICAL")
                
        for pattern in self.HIGH_PATTERNS:
            if re.search(pattern, cmd):
                return _higher_risk(risk, "HIGH")
                
        for pattern in self.MEDIUM_PATTERNS:
            if re.search(pattern, cmd):
                return _higher_risk(risk, "MEDIUM")
                
        return risk

risk_classifier = RiskClassifier()
