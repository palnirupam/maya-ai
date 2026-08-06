"""
Maya AI — Wallpaper Manager
Handles wallpaper history, feedback, and intelligent alternatives
"""

import os
import json
import time
import random
from pathlib import Path

# Wallpaper history storage
HISTORY_FILE = Path.home() / ".maya" / "wallpaper_history.json"
WALLPAPER_FOLDER = Path.home() / "Downloads"

# Ensure .maya directory exists
HISTORY_FILE.parent.mkdir(exist_ok=True)


class WallpaperManager:
    """Manages wallpaper history and user preferences"""
    
    def __init__(self):
        self.history = self._load_history()
    
    def _load_history(self):
        """Load wallpaper history from file"""
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE, 'r') as f:
                    return json.load(f)
            except Exception:
                return []
        return []
    
    def _save_history(self):
        """Save wallpaper history to file"""
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
        except Exception as e:
            print(f"Warning: Could not save wallpaper history: {e}")
    
    def add_to_history(self, path: str, theme: str = "unknown"):
        """Add wallpaper to history"""
        entry = {
            "path": str(path),
            "theme": theme,
            "timestamp": time.time(),
            "kept": False  # Will be updated if user keeps it
        }
        self.history.append(entry)
        
        # Keep only last 10 entries
        if len(self.history) > 10:
            self.history = self.history[-10:]
        
        self._save_history()
    
    def get_previous_wallpaper(self):
        """Get the wallpaper before the current one"""
        if len(self.history) >= 2:
            return self.history[-2]
        return None
    
    def mark_current_as_kept(self):
        """Mark current wallpaper as liked by user"""
        if self.history:
            self.history[-1]["kept"] = True
            self._save_history()
    
    def mark_current_as_disliked(self):
        """Mark current wallpaper as disliked"""
        if self.history:
            self.history[-1]["kept"] = False
            self._save_history()
    
    def get_user_preferences(self):
        """Analyze history to determine user preferences"""
        liked_themes = []
        disliked_themes = []
        
        for entry in self.history:
            if entry.get("kept"):
                liked_themes.append(entry["theme"])
            else:
                disliked_themes.append(entry["theme"])
        
        return {
            "liked_themes": list(set(liked_themes)),
            "disliked_themes": list(set(disliked_themes))
        }
    
    def get_alternative_wallpaper_url(self, theme: str, avoid_recent=True):
        """Get alternative wallpaper URL for the same theme"""
        # Generate random seed to get different image
        seed = random.randint(1000, 99999)
        
        # If avoiding recent, check history
        if avoid_recent:
            recent_themes = [h["theme"] for h in self.history[-3:]]
            while f"{theme}{seed}" in str(recent_themes):
                seed = random.randint(1000, 99999)
        
        # Multiple sources for variety
        sources = [
            f"https://picsum.photos/seed/{theme}{seed}/1920/1080",
            f"https://source.unsplash.com/1920x1080/?{theme}",
        ]
        
        return random.choice(sources)
    
    def suggest_alternative_themes(self, current_theme: str):
        """Suggest alternative themes based on current theme"""
        theme_alternatives = {
            "hacker": ["cyberpunk", "tech", "coding", "matrix", "digital"],
            "nature": ["landscape", "mountain", "forest", "ocean", "sunset"],
            "srikrishna": ["krishna", "radha", "spiritual", "hindu", "devotional"],
            "minimal": ["abstract", "simple", "clean", "geometric", "modern"],
            "dark": ["black", "noir", "night", "moody", "gothic"],
        }
        
        # Get alternatives or provide generic suggestions
        alternatives = theme_alternatives.get(current_theme.lower(), 
                                             ["nature", "minimal", "abstract", "dark"])
        
        return alternatives[:4]  # Return top 4 suggestions


# Global instance
wallpaper_manager = WallpaperManager()


def download_wallpaper(theme: str, filename: str = None):
    """Download wallpaper for given theme"""
    import urllib.request
    
    if filename is None:
        filename = f"maya_{theme}_wallpaper_{int(time.time())}.jpg"
    
    download_path = WALLPAPER_FOLDER / filename
    url = wallpaper_manager.get_alternative_wallpaper_url(theme)
    
    try:
        urllib.request.urlretrieve(url, str(download_path))
        return str(download_path)
    except Exception as e:
        return None


def handle_wallpaper_feedback(feedback_type: str, current_theme: str = None):
    """
    Handle user feedback about wallpaper
    
    feedback_type: "dislike" | "restore" | "suggest" | "like"
    current_theme: The theme of current wallpaper
    """
    from .system_ops import handle_pc
    
    if feedback_type == "dislike":
        # User doesn't like current wallpaper
        wallpaper_manager.mark_current_as_disliked()
        
        if current_theme:
            # Try alternative from same theme
            new_path = download_wallpaper(current_theme)
            if new_path:
                result = handle_pc("theme_wallpaper", name=new_path)
                wallpaper_manager.add_to_history(new_path, current_theme)
                return f"Tried different {current_theme} wallpaper. {result}"
            else:
                return "ERR: Could not download alternative wallpaper"
        else:
            # Suggest alternatives
            return handle_wallpaper_feedback("suggest")
    
    elif feedback_type == "restore":
        # Restore previous wallpaper
        previous = wallpaper_manager.get_previous_wallpaper()
        if previous:
            result = handle_pc("theme_wallpaper", name=previous["path"])
            return f"Restored previous wallpaper ({previous['theme']}). {result}"
        else:
            return "No previous wallpaper found in history"
    
    elif feedback_type == "suggest":
        # Suggest alternative themes
        if current_theme:
            suggestions = wallpaper_manager.suggest_alternative_themes(current_theme)
        else:
            suggestions = ["nature", "minimal", "dark", "abstract"]
        
        return f"Alternative themes: {', '.join(suggestions)}"
    
    elif feedback_type == "like":
        # User likes current wallpaper
        wallpaper_manager.mark_current_as_kept()
        return "Noted: You like this wallpaper!"
    
    return "Unknown feedback type"
