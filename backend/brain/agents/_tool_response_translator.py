"""Tool response translation layer for consistent language experience.

This module wraps tool execution to ensure all tool responses
match the user's conversation style consistently.
"""

import json
import logging
from typing import Any, Dict, Optional, Union
from ..language_style import detect_language_style, get_latest_conversation_style
from ..language_style_enhanced import translate_system_response, get_localized_message

logger = logging.getLogger(__name__)

class ToolResponseTranslator:
    """Translates tool responses to match user's language style."""
    
    def __init__(self):
        self.style_cache = {}
        
    def wrap_tool_response(
        self, 
        tool_name: str, 
        response: Any, 
        user_style: Optional[str] = None
    ) -> Any:
        """Wrap tool response with language-appropriate formatting."""
        
        target_style = user_style or get_latest_conversation_style()
        
        # Handle different response types
        if isinstance(response, str):
            return self._translate_string_response(response, target_style, tool_name)
        elif isinstance(response, dict):
            return self._translate_dict_response(response, target_style, tool_name)
        elif isinstance(response, list):
            return self._translate_list_response(response, target_style, tool_name)
        else:
            return response
            
    def _translate_string_response(self, text: str, style: str, tool_name: str) -> str:
        """Translate string responses."""
        if not text.strip():
            return text
            
        # Tool-specific translations
        if tool_name in {"file", "pc"}:
            return self._translate_system_tool_response(text, style)
        elif tool_name in {"search", "web_search"}:
            return self._translate_search_response(text, style)
        elif tool_name in {"email", "whatsapp", "telegram"}:
            return self._translate_communication_response(text, style)
        else:
            return translate_system_response(text, style)
            
    def _translate_dict_response(self, data: Dict, style: str, tool_name: str) -> Dict:
        """Translate dictionary responses while preserving structure."""
        translated = {}
        
        for key, value in data.items():
            # Translate user-facing messages
            if key in {"message", "status", "result", "description", "error"}:
                if isinstance(value, str):
                    translated[key] = translate_system_response(value, style)
                else:
                    translated[key] = value
            # Keep technical data as-is
            elif key in {"path", "size", "url", "id", "timestamp", "data"}:
                translated[key] = value
            # Recursively handle nested structures
            elif isinstance(value, (dict, list)):
                translated[key] = self.wrap_tool_response(tool_name, value, style)
            else:
                translated[key] = value
                
        return translated
        
    def _translate_list_response(self, items: list, style: str, tool_name: str) -> list:
        """Translate list responses."""
        return [
            self.wrap_tool_response(tool_name, item, style) 
            for item in items
        ]
        
    def _translate_system_tool_response(self, text: str, style: str) -> str:
        """Translate file/pc tool responses."""
        import re
        
        # Common file operation patterns
        if style == "banglish":
            patterns = {
                r"File '([^']+)' created successfully": r"File '\1' successfully create hoyeche",
                r"File '([^']+)' deleted": r"File '\1' delete hoyeche", 
                r"File '([^']+)' copied to '([^']+)'": r"File '\1' ke '\2' te copy hoyeche",
                r"File '([^']+)' moved to '([^']+)'": r"File '\1' ke '\2' te move hoyeche",
                r"Folder created: (.+)": r"Folder create hoyeche: \1",
                r"Volume set to (\d+)%": r"Volume \1% set hoyeche",
                r"Brightness set to (\d+)%": r"Brightness \1% set hoyeche",
                r"Screenshot saved to (.+)": r"Screenshot save hoyeche: \1",
            }
        elif style == "hindilish":
            patterns = {
                r"File '([^']+)' created successfully": r"File '\1' successfully create ho gaya",
                r"File '([^']+)' deleted": r"File '\1' delete ho gaya", 
                r"File '([^']+)' copied to '([^']+)'": r"File '\1' ko '\2' mein copy ho gaya",
                r"File '([^']+)' moved to '([^']+)'": r"File '\1' ko '\2' mein move ho gaya",
                r"Folder created: (.+)": r"Folder create ho gaya: \1",
                r"Volume set to (\d+)%": r"Volume \1% set ho gaya",
                r"Brightness set to (\d+)%": r"Brightness \1% set ho gaya",
                r"Screenshot saved to (.+)": r"Screenshot save ho gaya: \1",
            }
        else:
            return text
        
        result = text
        for pattern, replacement in patterns.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
                
        return result
        
    def _translate_search_response(self, text: str, style: str) -> str:
        """Translate search tool responses.""" 
        if style == "banglish":
            text = text.replace("Found", "Peye6chi")
            text = text.replace("results", "ta result")
            text = text.replace("No results found", "Kono result paini")
            text = text.replace("Searching for", "Search korchi")
        elif style == "hindilish":
            text = text.replace("Found", "Mile")
            text = text.replace("results", "results")
            text = text.replace("No results found", "Koi results nahi mile")
            text = text.replace("Searching for", "Search kar raha hun")
            
        return text
        
    def _translate_communication_response(self, text: str, style: str) -> str:
        """Translate email/messaging responses."""
        if style == "banglish":
            text = text.replace("Message sent", "Message pathano hoyeche")
            text = text.replace("Email sent", "Email pathano hoyeche")
            text = text.replace("Failed to send", "Pathate parini")
            text = text.replace("Connected", "Connect hoyeche")
            text = text.replace("Disconnected", "Disconnect hoyeche")
        elif style == "hindilish":
            text = text.replace("Message sent", "Message bhej diya")
            text = text.replace("Email sent", "Email bhej diya") 
            text = text.replace("Failed to send", "Bhejne mein fail")
            text = text.replace("Connected", "Connect ho gaya")
            text = text.replace("Disconnected", "Disconnect ho gaya")
            
        return text

# Global translator instance
tool_translator = ToolResponseTranslator()

def translate_tool_response(tool_name: str, response: Any, user_style: Optional[str] = None) -> Any:
    """Public function to translate tool responses."""
    return tool_translator.wrap_tool_response(tool_name, response, user_style)