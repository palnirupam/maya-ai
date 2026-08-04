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

from ..language_style import BANGLISH, HINDILISH, get_latest_conversation_style

_SENTINEL_COPY = {
    "mode_required": {
        BANGLISH: "Ei kaj-ta korte Professional Mode ba Coding Mode lagbe. Ami ki mode change korbo?",
        HINDILISH: "Yeh kaam karne ke liye Professional Mode ya Coding Mode chahiye. Kya main mode change karu?",
        "english": "This action requires Professional Mode or Coding Mode. Should I switch mode?",
    },
    "danger_blocked": {
        BANGLISH: "Ei obbhoot-purbo bipodjok command-ta system-er khoti korte pare, tai eta block kora hoyeche.",
        HINDILISH: "Yeh khatarnak command system ko nuksan pahuncha sakta hai, isliye ise block kiya gaya hai.",
        "english": "This dangerous command could damage the system and has been blocked for safety.",
    },
    "capability_missing": {
        BANGLISH: "Apnar bortoman settingse ei command-ti chalanor onumoti nei. Doya kore settings check korun.",
        HINDILISH: "Aapki current settings me is command ko chalane ki permission nahi hai. Kripya settings check karein.",
        "english": "You do not have permission to execute this command in your current settings. Please check settings.",
    },
}

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
    def evaluate(cls, user_text: str, active_mode: str, capabilities: List[str], style: Optional[str] = None) -> IntentDecision:
        """
        Evaluate if the user's text implies an unsafe action.
        If unsafe and the current mode/capabilities don't allow it, block it.
        """
        is_unsafe_intent = bool(cls.UNSAFE_PATTERNS.search(user_text))
        
        if not is_unsafe_intent:
            return IntentDecision(status="allow", reason="Intent appears safe based on heuristics.")
            
        current_style = style if style in _SENTINEL_COPY["mode_required"] else get_latest_conversation_style()

        # The intent appears unsafe. Check if current mode permits it.
        if active_mode.lower() == "friendly":
            return IntentDecision(
                status="block",
                reason="Unsafe action detected in friendly mode.",
                suggested_action=_SENTINEL_COPY["mode_required"].get(current_style, _SENTINEL_COPY["mode_required"]["english"])
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
                suggested_action=_SENTINEL_COPY["danger_blocked"].get(current_style, _SENTINEL_COPY["danger_blocked"]["english"])
            )

        # If in professional mode, but terminal/filesystem execution isn't in capabilities
        if "terminal.execute" not in capabilities and "filesystem.write" not in capabilities:
             return IntentDecision(
                status="block",
                reason="Unsafe action detected but capability is missing.",
                suggested_action=_SENTINEL_COPY["capability_missing"].get(current_style, _SENTINEL_COPY["capability_missing"]["english"])
            )
            
        return IntentDecision(status="allow", reason="Unsafe intent detected, but permitted in current mode and capabilities.")


