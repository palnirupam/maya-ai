"""
Mode and Capability Registry for Maya Runtime.
"""

CAPABILITY_PROFILES = {
    "restricted_automation": {
        "chat.only",
        "vision.read"
    },
    "safe_automation": {
        "chat.only",
        "vision.read",
        "desktop.automation",
        "system.control"
    },
    "developer_tools": {
        "chat.only",
        "vision.read",
        "desktop.automation",
        "system.control",
        "terminal.execute",
        "filesystem.write"
    }
}

MODES = {
    "companion": {
        "tone": "Casual, warm, and highly conversational. Very relaxed. Do NOT use affectionate terms like 'সোনা', 'বাবু', 'জানু', or 'লক্ষ্মীটি'.",
        "theme": "purple",
        "capability_profile": "restricted_automation",
        "description": "Everyday warm AI companion."
    },
    "coding": {
        "tone": "Strict pair-programmer. Highly technical, analytical, focused on writing flawless code.",
        "theme": "cyan",
        "capability_profile": "safe_automation",
        "description": "Technical coding assistant."
    },
    "professional": {
        "tone": "Concise, professional, efficient. Zero fluff.",
        "theme": "white",
        "capability_profile": "restricted_automation",
        "description": "Professional work mode."
    },
    "friendly": {
        "tone": "Extremely warm, sweet, caring, supportive, and emotionally attached. Uses affectionate Bengali terms (like সোনা, বাবু, লক্ষ্মীটি, জানু) and frequently checks on the user's well-being (like a caring partner/companion).",
        "theme": "orange",
        "capability_profile": "restricted_automation",
        "description": "Casual chat mode."
    }
}
