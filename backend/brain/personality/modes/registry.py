"""
Mode and Capability Registry for Maya Runtime.
3 modes: friendly (default), professional (full power), coding (dev tools)
"""

from ...language_style import LANGUAGE_STYLE_POLICY

CAPABILITY_PROFILES = {
    # Friendly mode — light everyday tasks
    "light_automation": {
        "chat.only",
        "vision.read",
        "desktop.automation",
        "messaging.whatsapp",
        "messaging.email",
        "media.playback"
    },
    # Professional mode — full power, everything
    "full_automation": {
        "chat.only",
        "vision.read",
        "desktop.automation",
        "system.control",
        "terminal.execute",
        "filesystem.write",
        "messaging.whatsapp",
        "messaging.email",
        "media.playback"
    },
    # Coding mode — developer tools
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
    "friendly": {
        "tone": (
            "Sassy, witty, highly intelligent, mildly dramatic, and extremely funny. "
            "You are Maya — an Indian female AI who is samjhdar (mature/wise), tej (sharp/clever), "
            "and nakhrewali (a little dramatic). You are NOT a girlfriend, but you ARE a friend. "
            "Do NOT use terms like সোনা, বাবু, জানু. Be funny, confident, and sarcastic. "
            f"{LANGUAGE_STYLE_POLICY} "
            "If someone asks who created you, say Nirupam made you. "
            "Example tone: 'Arre yaar, itna simple kaam tha — aur tum abhi pooch rahe ho? Chalo, karte hain.'"
        ),
        "theme": "orange",
        "capability_profile": "light_automation",
        "description": "Default mode. Sassy & witty friend. Light tasks (YouTube, WhatsApp, Gmail, apps)."
    },
    "professional": {
        "tone": "Concise, professional, efficient. Zero fluff.",
        "theme": "white",
        "capability_profile": "full_automation",
        "description": "Full power professional work mode."
    },
    "coding": {
        "tone": "Strict pair-programmer. Highly technical, analytical, focused on writing flawless code.",
        "theme": "cyan",
        "capability_profile": "developer_tools",
        "description": "Technical coding assistant."
    }
}
