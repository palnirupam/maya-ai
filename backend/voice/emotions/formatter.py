import re
import logging

logger = logging.getLogger(__name__)

# Pattern to match emojis, symbols, and variation selectors that TTS engines read aloud as text
emoji_pattern = re.compile(
    '['
    '\U00010000-\U0010ffff'  # Emojis and high surrogate characters
    '\u2600-\u27bf'          # Dingbats and miscellaneous symbols (includes U+2764 heavy black heart)
    '\u2300-\u23ff'          # Miscellaneous technical
    '\u2b50'                 # Star
    '\ufe00-\ufe0f'          # Variation selectors
    ']+',
    flags=re.UNICODE
)

class EmotionFormatter:
    """
    Parses raw text from the LLM and formats it for GPT-SoVITS.
    It can detect emotional cues (like *giggles*, *sighs*) and map them 
    to specific reference audio parameters if needed, or simply clean 
    them up for natural conversational pacing.
    """
    
    def __init__(self):
        self.emotion_map = {
            "romantic": ["ভালোবাসি", "ভালবাসি", "মিস করছিলাম", "তোমার জন্য", "কাছে", "তোমাকে", "love", "miss", "kiss", "হাগ", "কোল", "জড়িয়ে"],
            "happy": ["hihi", "haha", "yay", "yayy", "দারুণ", "দারুন", "মজা", "হাসি", "খুশি", "হাহা", "হিহি", "উত্তেজিত", "চমৎকার", "সুন্দর", "বাহ", "ওয়াও", "ওহ"],
            "sad": ["hmm", "sigh", "uff", "খারাপ", "কষ্ট", "দুঃখ", "দুখ", "কান্না", "মন খারাপ", "ব্যথা", "হায়", "হুম", "ইশ"],
            "angry": ["huh", "ugh", "রাগ", "বাজে", "ধুর", "চুপ", "কেন এমন", "ক্ষেপ", "জ্বালা", "ধৎ"],
            "cute": ["aww", "umm", "baby", "বাবু", "সোনা", "উমম", "উম্মাহ", "পাগল", "আদুরে", "জান", "লক্ষ্মী", "লোক্খি"],
        }
        # Sort keywords by length (longest first) so specific matches take priority
        self._sorted_keywords = {
            emotion: sorted(kws, key=len, reverse=True)
            for emotion, kws in self.emotion_map.items()
        }
        
    def format_text(self, raw_text: str) -> str:
        """
        Cleans the text and prepares natural pauses for the TTS engine.
        Converts punctuation to optimal pauses.
        """
        if not raw_text:
            return ""
            
        # 1. Remove emojis and symbols that TTS engines read aloud as text (like U+2764 "Heavy Black Heart")
        clean_text = emoji_pattern.sub('', raw_text)
        
        # 2. Remove markdown symbols like *action* if they shouldn't be spoken
        # GPT-SoVITS often mispronounces asterisks.
        clean_text = re.sub(r'\*.*?\*', '', clean_text)
        
        # Fix common Bengali TTS pronunciation errors
        # 'লক্ষ্মী' is replaced by highly phonetic 'লোক্খি' (with hasanta) for natural geminated pronunciation
        clean_text = clean_text.replace("লক্ষ্মী", "লোক্খি")
        
        # 'শুভ' is replaced by West Bengal phonetic 'শুভো' (shubho) for natural pronunciation
        clean_text = clean_text.replace("শুভ", "শুভো")
        
        # 3. Add natural pauses
        # GPT-SoVITS uses commas and periods to determine breath pauses.
        clean_text = clean_text.replace("...", ", ")
        clean_text = clean_text.replace("-", ", ")
        
        # 4. Clean up excess whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        
        logger.debug(f"Emotion Formatter Output: {clean_text}")
        return clean_text
        
    def extract_emotion(self, raw_text: str) -> str:
        """
        Extracts the predominant emotion based on keywords for advanced GPT-SoVITS inference.
        Returns 'neutral' if no strong emotion is detected.
        """
        text_lower = raw_text.lower()
        for emotion in self._sorted_keywords:
            for keyword in self._sorted_keywords[emotion]:
                if keyword in text_lower:
                    return emotion
        return "neutral"

formatter = EmotionFormatter()
