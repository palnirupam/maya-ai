"""
LLM-based Intent Classifier for Maya AI
Replaces brittle regex patterns with flexible AI-powered intent detection.
"""
import logging
from typing import Dict, Optional
from ...providers.gemini_adapter import gemini_adapter

logger = logging.getLogger(__name__)

# Cache to avoid repeated LLM calls for same queries
_intent_cache: Dict[str, Dict[str, bool]] = {}

INTENT_CLASSIFICATION_PROMPT = """You are an intent classifier. Analyze the user message and detect these intents:

1. CAMERA_OUTFIT: User wants you to see their outfit/clothes/dress using camera
   Examples: "outfit kemon lagche", "ami kemon lagchi", "dress ta dekhte kako", "how do I look"
   
2. CAMERA_REVIEW: User wants you to see and review an object/item using camera
   Examples: "eta ki dekho", "this flower ta dekho", "ei mouse review koro", "ye phone kaisa hai"
   
3. WALLPAPER: User wants to change desktop wallpaper/background
   Examples: "wallpaper lagao", "background change koro", "desktop theme set koro", "Srikrishna er wallpaper dao"

4. YOUTUBE_DATA: User wants YouTube video analytics/data (NOT just playing)
   Examples: "ei video te koto like ache", "subscriber count dekho", "view count bolo"

CRITICAL RULES:
- If message contains "wallpaper", "background", "theme", "desktop" → CAMERA_OUTFIT=false, CAMERA_REVIEW=false
- If no camera/visual intent → all camera flags false
- Be strict: only flag true if user CLEARLY wants camera vision

Respond ONLY with valid JSON:
{
  "camera_outfit": true/false,
  "camera_review": true/false,
  "wallpaper": true/false,
  "youtube_data": true/false
}

User message: "{message}"
"""


async def classify_intent(text: str, use_cache: bool = True) -> Dict[str, bool]:
    """
    Classify user intent using LLM instead of regex.
    
    Args:
        text: User message
        use_cache: Whether to use cached results
        
    Returns:
        Dict with intent flags: camera_outfit, camera_review, wallpaper, youtube_data
    """
    # Normalize for cache key
    cache_key = text.strip().lower()
    
    if use_cache and cache_key in _intent_cache:
        logger.info(f"[Intent Cache Hit] {cache_key[:50]}")
        return _intent_cache[cache_key]
    
    try:
        # Quick keyword pre-filter to save LLM calls
        text_lower = text.lower()
        
        # Fast path: obvious wallpaper request
        if any(kw in text_lower for kw in ["wallpaper", "background", "desktop theme"]):
            result = {
                "camera_outfit": False,
                "camera_review": False,
                "wallpaper": True,
                "youtube_data": False,
            }
            _intent_cache[cache_key] = result
            return result
        
        # Fast path: obvious greetings/chat (no vision needed)
        if any(kw in text_lower for kw in ["hello", "hi", "hey", "kemon acho", "ki korcho", "koto baje"]):
            result = {
                "camera_outfit": False,
                "camera_review": False,
                "wallpaper": False,
                "youtube_data": False,
            }
            _intent_cache[cache_key] = result
            return result
        
        # Use LLM for complex cases
        prompt = INTENT_CLASSIFICATION_PROMPT.format(message=text)
        
        response = await gemini_adapter.generate_response(
            context=[],
            prompt=prompt,
            override_tools=[],
            model_tier="fast",  # Use fast model for classification
        )
        
        # Parse JSON response
        import json
        response_text = str(response).strip()
        
        # Extract JSON if wrapped in markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        intent_result = json.loads(response_text)
        
        # Validate response
        required_keys = ["camera_outfit", "camera_review", "wallpaper", "youtube_data"]
        if not all(k in intent_result for k in required_keys):
            logger.warning(f"[Intent Classifier] Missing keys in response: {intent_result}")
            # Fallback to safe defaults
            intent_result = {k: intent_result.get(k, False) for k in required_keys}
        
        # Cache result
        _intent_cache[cache_key] = intent_result
        
        logger.info(f"[Intent Classified] {text[:50]} → {intent_result}")
        return intent_result
        
    except Exception as e:
        logger.error(f"[Intent Classifier] Failed: {e}", exc_info=True)
        # Safe fallback: no vision triggers
        return {
            "camera_outfit": False,
            "camera_review": False,
            "wallpaper": False,
            "youtube_data": False,
        }


def clear_intent_cache():
    """Clear the intent classification cache."""
    global _intent_cache
    _intent_cache.clear()
    logger.info("[Intent Cache] Cleared")
