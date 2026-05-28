import logging

logger = logging.getLogger(__name__)

class EmotionEngine:
    """
    Maps conversational sentiment to UI visual states for the Voice Orb.
    """
    def __init__(self):
        self.current_emotion = "focused"

    def get_orb_color(self, emotion: str) -> str:
        """Map abstract emotions to UI concepts"""
        mapping = {
            "focused": "cyan",
            "cheerful": "soft_gold",
            "thinking": "rotating_blue",
            "professional": "white_blue",
            "error": "red",
            "idle": "primary"
        }
        return mapping.get(emotion, "primary")

    def update_from_sentiment(self, text: str):
        """
        A placeholder for a real sentiment analysis step.
        In production, the LLM itself could return an 'emotion' tag in its JSON output.
        """
        text = text.lower()
        if "happy" in text or "great" in text or "!" in text:
            self.current_emotion = "cheerful"
        elif "error" in text or "failed" in text:
            self.current_emotion = "error"
        else:
            self.current_emotion = "focused"
        
        return self.current_emotion

emotion_engine = EmotionEngine()
