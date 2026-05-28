"""
Maya AI — App Context System
Allows Maya to load specific knowledge (shortcuts, workflows) about an application
before attempting to control it.
"""
import os
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

CONTEXT_DIR = Path("c:/maya-ai/backend/data/app_contexts")

def get_app_context(app_name: str) -> str:
    """
    Retrieves the shortcut guide, capabilities, and workflow context for a specific application.
    Call this BEFORE attempting to automate an unfamiliar application.
    Args:
        app_name (str): The name of the application (e.g. 'vscode', 'chrome', 'google_meet', 'google_classroom', 'excel').
    Returns:
        str: A detailed markdown string containing shortcuts and guidelines for the app.
    """
    app_name = app_name.lower().strip().replace(" ", "_")
    file_path = CONTEXT_DIR / f"{app_name}.json"
    
    if not file_path.exists():
        # Try to find a partial match
        available = [f.stem for f in CONTEXT_DIR.glob("*.json")]
        matches = [m for m in available if app_name in m or m in app_name]
        if matches:
            file_path = CONTEXT_DIR / f"{matches[0]}.json"
        else:
            return (
                f"No specific context found for '{app_name}'.\n"
                f"Available contexts: {', '.join(available) if available else 'None'}.\n"
                "You must rely on generic Windows shortcuts or visual text clicking."
            )
            
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        result = f"# App Context: {data.get('name', app_name.upper())}\n\n"
        
        if "description" in data:
            result += f"{data['description']}\n\n"
            
        if "shortcuts" in data:
            result += "## Key Shortcuts\n"
            for action, shortcut in data["shortcuts"].items():
                result += f"- **{action}**: {shortcut}\n"
            result += "\n"
            
        if "workflows" in data:
            result += "## Workflows\n"
            for wf_name, steps in data["workflows"].items():
                result += f"### {wf_name}\n"
                for step in steps:
                    result += f"- {step}\n"
            result += "\n"
            
        if "tips" in data:
            result += "## Tips\n"
            for tip in data["tips"]:
                result += f"- {tip}\n"
                
        return result
    except Exception as e:
        logger.error(f"Error reading app context {app_name}: {e}")
        return f"ERROR reading context file: {e}"
