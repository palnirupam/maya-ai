import re
from dataclasses import dataclass
from typing import List, Literal, Optional
import logging

logger = logging.getLogger(__name__)

IntentDecisionStatus = Literal["allow", "block"]

@dataclass
class IntentDecision:
    status: IntentDecisionStatus
    reason: str
    suggested_action: Optional[str] = None

class IntentSentinel:
    """
    Layer 0: The Intent Sentinel.
    Fast, regex-based heuristic engine to detect unsafe or destructive intents
    before they reach the LLM. Uses ToolManifest's risk_tiers conceptually.
    
    Design principle: ONLY block things that should NEVER reach the LLM in
    the current mode. Regular file ops (delete/trash) are allowed through and
    gated by the agent-level DANGER_TOOLS approval flow instead.
    """

    # CRITICAL: These patterns are system-destructive and must be blocked early.
    # Do NOT add broad words like 'delete', 'remove', 'trash' here — those are
    # normal user file operations handled by the DANGER_TOOLS approval flow.
    # This sentinel targets truly irreversible system-level commands only.
    UNSAFE_PATTERNS = re.compile(
        r"(format\s+[a-zA-Z]:|\brm\s+-rf\b|drop\s+table|"
        r"\bpoweroff\b|rmdir\s+/s|\bdel\s+/[sfq]|"
        r"execute_powershell|execute_python|run\s+script)",
        re.IGNORECASE
    )

    @classmethod
    def evaluate(cls, user_text: str, active_mode: str, capabilities: List[str]) -> IntentDecision:
        """
        Evaluate if the user's text implies an unsafe action.
        If unsafe and the current mode/capabilities don't allow it, block it.
        """
        is_unsafe_intent = bool(cls.UNSAFE_PATTERNS.search(user_text))
        
        if not is_unsafe_intent:
            return IntentDecision(status="allow", reason="Intent appears safe based on heuristics.")
            
        # The intent appears unsafe. Check if current mode permits it.
        if active_mode.lower() == "friendly":
            return IntentDecision(
                status="block",
                reason="Unsafe action detected in friendly mode.",
                suggested_action="এই কাজটা করতে Professional Mode বা Coding Mode লাগবে। আমি কি মোড চেঞ্জ করবো?"
            )
            
        # Critical system-destruction commands are blocked unconditionally
        CRITICAL_SYSTEM_DESTRUCTION = re.compile(
            r"(format\s+[a-zA-Z]:|\brm\s+-rf\b|rmdir\s+/s|\bdel\s+/[sfq])",
            re.IGNORECASE
        )
        if CRITICAL_SYSTEM_DESTRUCTION.search(user_text):
            return IntentDecision(
                status="block",
                reason="System destruction command detected and blocked for safety.",
                suggested_action="এই অত্যন্ত বিপজ্জনক কমান্ডটি সিস্টেমের ক্ষতি করতে পারে, তাই এটি ব্লক করা হয়েছে।"
            )

        # If in professional mode, but terminal/filesystem execution isn't in capabilities
        if "terminal.execute" not in capabilities and "filesystem.write" not in capabilities:
             return IntentDecision(
                status="block",
                reason="Unsafe action detected but capability is missing.",
                suggested_action="আপনার বর্তমান সেটিংসে এই কমান্ডটি চালানোর অনুমতি নেই। দয়া করে সেটিংস চেক করুন।"
            )
            
        # NOTE: power actions (shutdown/restart/reboot/poweroff) are deliberately
        # NOT gated here. This Sentinel can only "allow"/"block" a request before
        # it ever reaches a tool call — it has no mechanism to pause execution
        # and resume once the user replies, so a "needs_approval" verdict here
        # was previously a dead end (the user was asked "Yes/No?" but a "Yes"
        # reply started a brand-new turn with no memory of the pending action,
        # so the shutdown never actually happened). The real, working approval
        # gate for these actions is the DANGER_TOOLS check in agent_team.py,
        # which intercepts the actual pc(action=...)/perform_shortcut(action=...)
        # tool call and drives a real tool_call_request/approve-deny round trip.
        return IntentDecision(status="allow", reason="Unsafe intent detected, but permitted in current mode and capabilities.")

