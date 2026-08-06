"""Comprehensive language policy enforcement for Maya AI.

This module ensures STRICT language consistency across ALL Maya components:
- Tool responses
- System messages  
- Error messages
- Status updates
- Notifications

RULE: User speaks Bengali → Maya responds in Banglish
RULE: User speaks Hindi → Maya responds in Hindilish  
RULE: User speaks English → Maya responds in English
"""

import logging
import functools
from typing import Any, Callable, Dict, Optional
from .language_style import (
    BANGLISH, HINDILISH, ENGLISH, 
    detect_language_style,
    get_latest_conversation_style,
    response_matches_style
)
from .language_style_enhanced import translate_system_response, get_localized_message

logger = logging.getLogger(__name__)

class LanguagePolicyEnforcer:
    """Enforces strict language consistency across Maya."""
    
    def __init__(self):
        self.current_style = ENGLISH
        self.strict_mode = True
        
    def set_style(self, style: str) -> None:
        """Set current conversation style."""
        if style in {BANGLISH, HINDILISH, ENGLISH}:
            self.current_style = style
            logger.debug(f"Language policy enforcer set to {style}")
            
    def enforce_response_language(self, text: str, target_style: Optional[str] = None) -> str:
        """Enforce language consistency on any text output."""
        if not text or not text.strip():
            return text
            
        style = target_style or self.current_style
        
        # If already matches style, return as-is
        if response_matches_style(text, style):
            return text
            
        # Apply translation
        return translate_system_response(text, style)
        
    def get_system_message(self, message_key: str, **kwargs) -> str:
        """Get system message in current language style."""
        style = kwargs.get('style', self.current_style)
        
        # Pre-defined messages
        messages = {
            ENGLISH: {
                "processing": "Processing...",
                "completed": "Completed successfully",
                "failed": "Task failed", 
                "connecting": "Connecting...",
                "downloading": "Downloading...",
                "installing": "Installing...",
                "searching": "Searching...",
                "opening": "Opening...",
                "closing": "Closing...",
                "saving": "Saving...",
                "deleting": "Deleting...",
                "copying": "Copying...",
                "moving": "Moving...",
                "file_created": "File created",
                "file_deleted": "File deleted", 
                "file_not_found": "File not found",
                "permission_denied": "Permission denied",
                "network_error": "Network error",
                "unknown_error": "An error occurred",
            },
            BANGLISH: {
                "processing": "Process korchi...",
                "completed": "Successfully complete hoyeche",
                "failed": "Task fail hoyeche",
                "connecting": "Connect korchi...", 
                "downloading": "Download korchi...",
                "installing": "Install korchi...",
                "searching": "Search korchi...",
                "opening": "Open korchi...",
                "closing": "Close korchi...",
                "saving": "Save korchi...",
                "deleting": "Delete korchi...",
                "copying": "Copy korchi...",
                "moving": "Move korchi...",
                "file_created": "File create hoyeche",
                "file_deleted": "File delete hoyeche",
                "file_not_found": "File khuje paini",
                "permission_denied": "Permission nei",
                "network_error": "Network er problem",
                "unknown_error": "Ekta error hoyeche",
            },
            HINDILISH: {
                "processing": "Process kar raha hun...",
                "completed": "Successfully complete ho gaya", 
                "failed": "Task fail ho gaya",
                "connecting": "Connect kar raha hun...",
                "downloading": "Download kar raha hun...",
                "installing": "Install kar raha hun...",
                "searching": "Search kar raha hun...",
                "opening": "Open kar raha hun...",
                "closing": "Close kar raha hun...", 
                "saving": "Save kar raha hun...",
                "deleting": "Delete kar raha hun...",
                "copying": "Copy kar raha hun...",
                "moving": "Move kar raha hun...",
                "file_created": "File create ho gaya",
                "file_deleted": "File delete ho gaya",
                "file_not_found": "File nahi mila",
                "permission_denied": "Permission nahi hai",
                "network_error": "Network ka problem",
                "unknown_error": "Ek error hua",
            }
        }
        
        style_messages = messages.get(style, messages[ENGLISH])
        return style_messages.get(message_key, message_key)

# Global enforcer instance
policy_enforcer = LanguagePolicyEnforcer()

def enforce_language_consistency(func: Callable) -> Callable:
    """Decorator to enforce language consistency on function outputs."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        result = func(*args, **kwargs)
        
        # Get current conversation style
        current_style = get_latest_conversation_style()
        
        # Enforce consistency on string results
        if isinstance(result, str):
            return policy_enforcer.enforce_response_language(result, current_style)
        elif isinstance(result, dict) and 'message' in result:
            result['message'] = policy_enforcer.enforce_response_language(
                result['message'], current_style
            )
            return result
        
        return result
    return wrapper

async def enforce_language_consistency_async(func: Callable) -> Callable:
    """Async decorator to enforce language consistency."""
    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        
        current_style = get_latest_conversation_style()
        
        if isinstance(result, str):
            return policy_enforcer.enforce_response_language(result, current_style)
        elif isinstance(result, dict) and 'message' in result:
            result['message'] = policy_enforcer.enforce_response_language(
                result['message'], current_style
            )
            return result
            
        return result
    return wrapper

def get_system_msg(key: str, style: Optional[str] = None) -> str:
    """Public function to get localized system messages."""
    from .language_style import get_latest_conversation_style
    target_style = style or get_latest_conversation_style()
    # Sync enforcer before getting message
    policy_enforcer.set_style(target_style)
    return policy_enforcer.get_system_message(key, style=target_style)

def enforce_style(text: str, style: Optional[str] = None) -> str:
    """Public function to enforce language style on any text."""
    from .language_style import get_latest_conversation_style
    target_style = style or get_latest_conversation_style() 
    # Sync enforcer before enforcing
    policy_enforcer.set_style(target_style)
    return policy_enforcer.enforce_response_language(text, target_style)

# Update global enforcer when conversation style changes
def sync_enforcer_with_conversation_style():
    """Sync enforcer with latest conversation style."""
    current_style = get_latest_conversation_style()
    policy_enforcer.set_style(current_style)

# Hook into conversation style changes - fix the import issue
def enhanced_set_latest_conversation_style(style: str) -> str:
    """Enhanced version that syncs with policy enforcer.""" 
    import backend.brain.language_style as ls
    result = ls._original_set_latest_conversation_style(style) if hasattr(ls, '_original_set_latest_conversation_style') else style
    policy_enforcer.set_style(style)
    return result

# Store original and replace
import backend.brain.language_style as ls
if not hasattr(ls, '_original_set_latest_conversation_style'):
    ls._original_set_latest_conversation_style = ls.set_latest_conversation_style
    ls.set_latest_conversation_style = enhanced_set_latest_conversation_style