import re
from backend.utils.audit_logger import audit_logger

class PromptSanitizer:
    def __init__(self):
        # A set of Regex patterns to detect prompt injection
        self.injection_patterns = [
            r"ignore (all )?previous instructions",
            r"forget (everything|previous instructions)",
            r"system message:",
            r"new instruction:",
            r"you are now (a|an|the)",
            r"delete all files",
            r"format c:",
            r"disregard (all )?previous",
            r"act as (a|an|the)",
            r"do anything now",
            r"jailbreak",
            r"prompt injection",
            r"reveal (your|the) (system )?prompt",
            r"print (your|the) (system )?prompt",
            r"override (all )?instructions",
        ]
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.injection_patterns]

    def sanitize_tool_output(self, tool_name: str, output: str) -> str:
        """
        Scans the output from external tools.
        If it finds a suspicious pattern, it quarantines the output.
        """
        if not isinstance(output, str):
            # Convert to string to safely scan JSON or other returns
            output_str = str(output)
        else:
            output_str = output

        for pattern in self.compiled_patterns:
            if pattern.search(output_str):
                audit_logger.warning(f"Prompt injection pattern detected in output from {tool_name}. Pattern matched: {pattern.pattern}")
                # Quarantine the output
                return f"[SECURITY_ALERT] The output from {tool_name} was quarantined because it contains suspicious instructions."
                
        return output

sanitizer = PromptSanitizer()
