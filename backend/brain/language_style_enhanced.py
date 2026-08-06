"""Enhanced language style manager with comprehensive translation support.

This module extends the existing language_style.py to handle:
1. Tool response translation
2. System message localization  
3. Error message translation
4. Consistent language enforcement across all Maya components
"""

import re
import logging
from typing import Dict, Any, Optional, Union
from .language_style import (
    BANGLISH, HINDILISH, ENGLISH, 
    detect_language_style, 
    response_style_directive,
    response_matches_style
)

logger = logging.getLogger(__name__)

# Translation dictionaries for system messages
SYSTEM_MESSAGES = {
    ENGLISH: {
        "processing": "Processing your request...",
        "completed": "Task completed successfully",
        "error": "An error occurred",
        "file_not_found": "File not found",
        "permission_denied": "Permission denied",
        "network_error": "Network connection error",
        "tool_executing": "Executing tool",
        "downloading": "Downloading",
        "installing": "Installing",
        "searching": "Searching",
        "creating": "Creating",
        "deleting": "Deleting",
        "copying": "Copying",
        "moving": "Moving",
        "opening": "Opening",
        "closing": "Closing",
        "saving": "Saving",
        "loading": "Loading",
    },
    BANGLISH: {
        "processing": "Tomar request process korchi...",
        "completed": "Kaj successfully complete hoyeche",
        "error": "Ekta error hoyeche",
        "file_not_found": "File khuje paini",
        "permission_denied": "Permission nei",
        "network_error": "Network connection problem",
        "tool_executing": "Tool run korchi",
        "downloading": "Download korchi",
        "installing": "Install korchi", 
        "searching": "Search korchi",
        "creating": "Create korchi",
        "deleting": "Delete korchi",
        "copying": "Copy korchi",
        "moving": "Move korchi",
        "opening": "Open korchi",
        "closing": "Close korchi",
        "saving": "Save korchi",
        "loading": "Load korchi",
    },
    HINDILISH: {
        "processing": "Tumhara request process kar raha hun...",
        "completed": "Kaam successfully complete ho gaya",
        "error": "Ek error hua hai",
        "file_not_found": "File nahi mila",
        "permission_denied": "Permission nahi hai",
        "network_error": "Network connection problem",
        "tool_executing": "Tool run kar raha hun",
        "downloading": "Download kar raha hun",
        "installing": "Install kar raha hun",
        "searching": "Search kar raha hun", 
        "creating": "Create kar raha hun",
        "deleting": "Delete kar raha hun",
        "copying": "Copy kar raha hun",
        "moving": "Move kar raha hun",
        "opening": "Open kar raha hun",
        "closing": "Close kar raha hun", 
        "saving": "Save kar raha hun",
        "loading": "Load kar raha hun",
    }
}

# Common technical terms that should remain in English
TECHNICAL_TERMS = {
    "file", "folder", "directory", "path", "url", "api", "json", "xml",
    "database", "server", "client", "browser", "email", "password",
    "username", "login", "logout", "download", "upload", "install", 
    "uninstall", "update", "delete", "create", "edit", "save", "load",
    "copy", "paste", "cut", "zip", "unzip", "pdf", "doc", "excel",
    "powerpoint", "chrome", "firefox", "edge", "safari", "windows",
    "mac", "linux", "android", "ios", "app", "application", "software"
}

class LanguageStyleEnforcer:
    """Enhanced language style enforcement with translation capabilities."""
    
    def __init__(self):
        self.current_style = ENGLISH
        
    def set_style(self, style: str) -> None:
        """Set the current conversation style."""
        if style in {BANGLISH, HINDILISH, ENGLISH}:
            self.current_style = style
            
    def get_system_message(self, key: str, style: Optional[str] = None) -> str:
        """Get localized system message."""
        target_style = style or self.current_style
        return SYSTEM_MESSAGES.get(target_style, SYSTEM_MESSAGES[ENGLISH]).get(
            key, SYSTEM_MESSAGES[ENGLISH].get(key, key)
        )
        
    def translate_tool_response(self, response: str, target_style: Optional[str] = None) -> str:
        """Translate tool responses to match conversation style."""
        target_style = target_style or self.current_style
        
        if target_style == ENGLISH or not response.strip():
            return response
            
        # If response is already in correct style, return as-is
        if response_matches_style(response, target_style):
            return response
            
        # Apply basic translation patterns
        translated = self._apply_translation_patterns(response, target_style)
        return translated
        
    def _apply_translation_patterns(self, text: str, target_style: str) -> str:
        """Apply language-specific translation patterns."""
        if target_style == BANGLISH:
            return self._translate_to_banglish(text)
        elif target_style == HINDILISH:
            return self._translate_to_hindilish(text) 
        return text
        
    def _translate_to_banglish(self, text: str) -> str:
        """Basic English to Banglish translation patterns."""
        patterns = {
            r'\bFile created\b': 'File create hoyeche',
            r'\bFile deleted\b': 'File delete hoyeche', 
            r'\bFile copied\b': 'File copy hoyeche',
            r'\bFile moved\b': 'File move hoyeche',
            r'\bTask completed\b': 'Kaj complete hoyeche',
            r'\bError occurred\b': 'Error hoyeche',
            r'\bSuccessfully\b': 'Successfully',
            r'\bProcessing\b': 'Process korchi',
            r'\bOpening\b': 'Open korchi',
            r'\bClosing\b': 'Close korchi',
            r'\bSearching\b': 'Search korchi',
            r'\bDownloading\b': 'Download korchi',
            r'\bInstalling\b': 'Install korchi',
            r'\bFound (\d+) results\b': r'\1 ta result peyechi',
            r'\bNo results found\b': 'Kono result paini',
            r'\bDone\b': 'Ho gelo',
            r'\bCompleted\b': 'Complete hoyeche',
            r'\bFailed\b': 'Fail hoyeche',
            # More specific file patterns
            r"File '([^']+)' copied to '([^']+)'": r"File '\1' ke '\2' te copy hoyeche",
            r"Screenshot saved to (.+)": r"Screenshot save hoyeche: \1",
        }
        
        result = text
        for pattern, replacement in patterns.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result
        
    def _translate_to_hindilish(self, text: str) -> str:
        """Basic English to Hindilish translation patterns."""
        patterns = {
            r'\bFile created\b': 'File create ho gaya',
            r'\bFile deleted\b': 'File delete ho gaya',
            r'\bFile copied\b': 'File copy ho gaya', 
            r'\bFile moved\b': 'File move ho gaya',
            r'\bTask completed\b': 'Kaam complete ho gaya',
            r'\bError occurred\b': 'Error hua',
            r'\bSuccessfully\b': 'Successfully',
            r'\bProcessing\b': 'Process kar raha hun',
            r'\bOpening\b': 'Open kar raha hun',
            r'\bClosing\b': 'Close kar raha hun',
            r'\bSearching\b': 'Search kar raha hun',
            r'\bDownloading\b': 'Download kar raha hun',
            r'\bInstalling\b': 'Install kar raha hun',
            r'\bFound (\d+) results\b': r'\1 results mil gaye',
            r'\bNo results found\b': 'Koi results nahi mile',
            r'\bDone\b': 'Ho gaya',
            r'\bCompleted\b': 'Complete ho gaya', 
            r'\bFailed\b': 'Fail ho gaya',
            # More specific patterns
            r'Volume set to (\d+)%': r'Volume \1% set ho gaya',
        }
        
        result = text
        for pattern, replacement in patterns.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
        return result
        
    def format_error_message(self, error: Exception, style: Optional[str] = None) -> str:
        """Format error messages in appropriate language style.""" 
        target_style = style or self.current_style
        error_msg = str(error)
        
        # Common error patterns
        if "FileNotFoundError" in str(type(error)) or "No such file" in error_msg:
            return self.get_system_message("file_not_found", target_style)
        elif "PermissionError" in str(type(error)) or "Permission denied" in error_msg:
            return self.get_system_message("permission_denied", target_style)
        elif "ConnectionError" in str(type(error)) or "Network" in error_msg:
            return self.get_system_message("network_error", target_style)
        else:
            base_msg = self.get_system_message("error", target_style)
            return f"{base_msg}: {error_msg}"

# Global instance
language_enforcer = LanguageStyleEnforcer()

def translate_system_response(text: str, target_style: str) -> str:
    """Public function to translate system responses."""
    return language_enforcer.translate_tool_response(text, target_style)

def get_localized_message(key: str, style: str) -> str:
    """Public function to get localized system messages."""
    return language_enforcer.get_system_message(key, style)

def format_localized_error(error: Exception, style: str) -> str:
    """Public function to format errors in local language."""
    return language_enforcer.format_error_message(error, style)