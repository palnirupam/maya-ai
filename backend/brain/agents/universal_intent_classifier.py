"""
Universal Intent Classification System for Maya AI
Industry-grade multi-intent detection for ALL Maya features.

Replaces brittle regex patterns across the entire system with flexible AI-powered classification.
"""
import logging
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from ..providers.gemini_adapter import gemini_adapter

logger = logging.getLogger(__name__)

# Intent cache with TTL support
_intent_cache: Dict[str, Dict[str, Any]] = {}
_cache_hits = 0
_cache_misses = 0


@dataclass
class IntentResult:
    """Structured intent classification result."""
    
    # Primary agent routing
    primary_agent: str  # CHAT, OS_EXECUTOR, RESEARCHER, CODER
    
    # Communication intents
    whatsapp_send: bool = False
    whatsapp_read: bool = False
    whatsapp_delete: bool = False
    email_send: bool = False
    email_read: bool = False
    email_delete: bool = False
    
    # Visual/Camera intents
    camera_outfit: bool = False
    camera_review: bool = False
    camera_photo: bool = False
    
    # Media intents
    youtube_play: bool = False
    youtube_data: bool = False  # Analytics/comments
    media_control: bool = False  # pause/play/stop
    
    # System control intents
    wallpaper_change: bool = False
    volume_control: bool = False
    brightness_control: bool = False
    power_action: bool = False  # shutdown/restart/sleep
    wifi_control: bool = False
    bluetooth_control: bool = False
    
    # File operations
    file_create: bool = False
    file_read: bool = False
    file_delete: bool = False
    file_search: bool = False
    
    # App control
    app_open: bool = False
    app_close: bool = False
    chrome_profile: Optional[str] = None  # Specific profile name
    
    # Research/search
    web_search: bool = False
    news_query: bool = False
    
    # Widget/Canvas requests
    create_widget: bool = False
    widget_type: Optional[str] = None  # calculator, tracker, game, etc.
    
    # Coding/scripting
    code_execution: bool = False
    script_create: bool = False
    
    # Conversation
    is_greeting: bool = False
    is_question: bool = False
    is_casual_chat: bool = False
    
    # Metadata
    confidence: float = 1.0
    entities: Dict[str, Any] = None  # Extracted entities (contact names, file paths, etc.)
    
    def __post_init__(self):
        if self.entities is None:
            self.entities = {}
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for caching."""
        result = {
            "primary_agent": self.primary_agent,
        }
        # Add all boolean flags
        for key, value in self.__dict__.items():
            if isinstance(value, bool):
                result[key] = value
            elif key in ["chrome_profile", "widget_type", "confidence", "entities"]:
                result[key] = value
        return result
    
    @classmethod
    def from_dict(cls, data: Dict) -> "IntentResult":
        """Create from dictionary."""
        return cls(**data)


UNIVERSAL_INTENT_PROMPT = """You are Maya AI's universal intent classifier. Analyze the user message and classify ALL relevant intents.

**USER'S LANGUAGE STYLE: {style}**
- If style is "banglish": User uses Bengali words in English letters (e.g., "ami", "tumi", "kore dao")
- If style is "hindilish": User uses Hindi words in English letters (e.g., "mera", "karo", "hai")
- If style is "english": User speaks pure English

**IMPORTANT**: Understand the message in the user's style, but classify intents in English. The intent flags are always in English.

## Intent Categories:

### 1. COMMUNICATION
- **whatsapp_send**: Send WhatsApp message
  Examples: "Maa ke msg pathao", "WhatsApp e Som ke bolo hi", "Ankita te text koro"
  
- **whatsapp_read**: Read WhatsApp messages
  Examples: "WhatsApp check koro", "msg ache ki", "Baba message korechhe ki"
  
- **whatsapp_delete**: Delete/revoke WhatsApp messages
  Examples: "last msg delete koro", "Ankita ke pathano msg mute koro"
  
- **email_send**: Send email
  Examples: "Gmail e mail pathao", "nirupam@gmail.com ke email koro", "resume attach kore mail pathao"
  
- **email_read**: Read emails
  Examples: "email check koro", "inbox dekho", "latest mail ki"
  
- **email_delete**: Delete/trash emails
  Examples: "ei mail delete koro", "trash e pathao", "first email remove koro"

### 2. VISUAL/CAMERA
- **camera_outfit**: User wants outfit/appearance review
  Examples: "ami kemon lagchi", "outfit kemon", "dress ta bhalo?"
  
- **camera_review**: Review object/item via camera
  Examples: "eta ki dekho", "ei flower review koro", "mouse ta kemon"
  
- **camera_photo**: Take a photo
  Examples: "photo tolo", "picture nao", "camera click koro"

### 3. MEDIA
- **youtube_play**: Play YouTube video (foreground or background)
  Examples: "gaana chalao", "song play koro", "YouTube e video dekho"
  
- **youtube_data**: Get YouTube analytics/data
  Examples: "ei video te like koto", "subscriber count", "comment dekho"
  
- **media_control**: Control playing media
  Examples: "pause koro", "stop music", "volume up", "gaana bondho koro"

### 4. SYSTEM CONTROL
- **wallpaper_change**: Change desktop wallpaper
  Examples: "wallpaper lagao", "background change koro", "Srikrishna er wallpaper dao"
  
- **volume_control**: Adjust volume
  Examples: "volume 50 koro", "awaz badao", "mute koro"
  
- **brightness_control**: Adjust screen brightness
  Examples: "brightness increase koro", "screen dim koro", "70% brightness"
  
- **power_action**: System power actions
  Examples: "shutdown koro", "PC restart koro", "sleep mode e jao", "lock screen"
  
- **wifi_control**: WiFi management
  Examples: "wifi on koro", "network scan koro", "MyWiFi connect koro"
  
- **bluetooth_control**: Bluetooth management
  Examples: "bluetooth on koro", "device list dekho", "unpair speaker"

### 5. FILE OPERATIONS
- **file_create**: Create/write files
  Examples: "Desktop e file banao", "summary save koro", "D drive e html file create koro"
  
- **file_read**: Read file contents
  Examples: "ei file poro", "document dekho", "C:/report.pdf kholo"
  
- **file_delete**: Delete files
  Examples: "ei file delete koro", "Desktop er txt remove koro"
  
- **file_search**: Search for files
  Examples: "report.pdf khuje dao", "resume kothay ache", "photo gulo dhundo"

### 6. APP CONTROL
- **app_open**: Open application
  Examples: "Chrome kholo", "Notepad chalu koro", "Calculator open koro"
  
- **app_close**: Close application
  Examples: "Chrome bondho koro", "app close koro", "Notepad band koro"
  
- **chrome_profile**: Open Chrome with specific profile (extract profile name)
  Examples: "Chrome kholo Nirupam profile e", "Ankita profile e Chrome"

### 7. RESEARCH/SEARCH
- **web_search**: General web search
  Examples: "search koro", "google e khuje dao", "Python tutorial dhundo"
  
- **news_query**: News/current events
  Examples: "news ki", "today's headlines", "stock market update"

### 8. WIDGETS/CANVAS
- **create_widget**: Build interactive UI component (extract widget_type)
  Examples: "calculator banao", "habit tracker create koro", "todo list", "game banao"
  Types: calculator, tracker, todo, habit, timer, game, dashboard, kanban

### 9. CODING
- **code_execution**: Run code/script
  Examples: "script run koro", "Python file execute koro", "test.py chalao"
  
- **script_create**: Write code/script
  Examples: "Python script likho", "automation code banao", "function create koro"

### 10. CONVERSATION
- **is_greeting**: Greetings
  Examples: "hello", "hi Maya", "kemon acho", "good morning"
  
- **is_question**: General questions
  Examples: "time koto", "kon dine", "Python ki", "how does X work"
  
- **is_casual_chat**: Casual conversation
  Examples: "golpo bolo", "joke sunao", "boring lagche"

## CRITICAL RULES:
1. **Multiple intents possible**: "Chrome kholo and YouTube chalao" → app_open=true, youtube_play=true
2. **Context matters**: "lagiye dao" with "wallpaper" → wallpaper_change, NOT camera
3. **Agent routing priority**:
   - CHAT: greetings, questions, casual chat, widget creation (without file path)
   - OS_EXECUTOR: system control, apps, communication, file ops (with pc() or file() tools)
   - RESEARCHER: web search, news
   - CODER: file operations with specific drive/path, code execution
4. **Entity extraction**: Extract contact names, file paths, profile names, numbers
5. **Confidence**: 1.0 = certain, 0.5-0.9 = likely, <0.5 = uncertain

## Response Format (MUST be valid JSON):
{{
  "primary_agent": "CHAT" | "OS_EXECUTOR" | "RESEARCHER" | "CODER",
  "whatsapp_send": true/false,
  "whatsapp_read": true/false,
  "whatsapp_delete": true/false,
  "email_send": true/false,
  "email_read": true/false,
  "email_delete": true/false,
  "camera_outfit": true/false,
  "camera_review": true/false,
  "camera_photo": true/false,
  "youtube_play": true/false,
  "youtube_data": true/false,
  "media_control": true/false,
  "wallpaper_change": true/false,
  "volume_control": true/false,
  "brightness_control": true/false,
  "power_action": true/false,
  "wifi_control": true/false,
  "bluetooth_control": true/false,
  "file_create": true/false,
  "file_read": true/false,
  "file_delete": true/false,
  "file_search": true/false,
  "app_open": true/false,
  "app_close": true/false,
  "chrome_profile": null | "ProfileName",
  "web_search": true/false,
  "news_query": true/false,
  "create_widget": true/false,
  "widget_type": null | "calculator" | "tracker" | "todo" | "game" | etc,
  "code_execution": true/false,
  "script_create": true/false,
  "is_greeting": true/false,
  "is_question": true/false,
  "is_casual_chat": true/false,
  "confidence": 0.0-1.0,
  "entities": {{
    "contact_names": ["name1", "name2"],
    "file_paths": ["C:/path/to/file"],
    "profile_name": "ProfileName",
    "numbers": [50, 70],
    "app_names": ["chrome", "notepad"]
  }}
}}

User message: "{message}"
"""


async def classify_universal_intent(
    text: str,
    use_cache: bool = True,
    context_history: Optional[List] = None,
    conversation_style: Optional[str] = None
) -> IntentResult:
    """
    Universal intent classification for ALL Maya features.
    
    Args:
        text: User message
        use_cache: Whether to use cached results
        context_history: Recent conversation context
        conversation_style: User's language style (banglish/hindilish/english)
        
    Returns:
        IntentResult with all detected intents and entities
    """
    global _cache_hits, _cache_misses
    
    # Detect language style if not provided
    if not conversation_style:
        from ..language_style import detect_conversation_style
        conversation_style = detect_conversation_style(text, context_history)
    
    # Normalize for cache key
    cache_key = text.strip().lower()[:200]  # Limit key length
    
    if use_cache and cache_key in _intent_cache:
        _cache_hits += 1
        logger.info(f"[Intent Cache Hit] {cache_key[:50]}... (hits: {_cache_hits}, misses: {_cache_misses})")
        return IntentResult.from_dict(_intent_cache[cache_key])
    
    _cache_misses += 1
    
    try:
        # === FAST PATH: Keyword pre-filters ===
        text_lower = text.lower()
        
        # Greetings (instant, no LLM)
        if any(kw in text_lower for kw in ["hello", "hi ", "hey ", "kemon acho", "kemon acho maya", "good morning", "good evening"]):
            result = IntentResult(
                primary_agent="CHAT",
                is_greeting=True,
                confidence=1.0
            )
            _intent_cache[cache_key] = result.to_dict()
            return result
        
        # Time/date queries (instant)
        if any(kw in text_lower for kw in ["time koto", "koto baje", "date koto", "aj ki bar"]):
            result = IntentResult(
                primary_agent="CHAT",
                is_question=True,
                confidence=1.0
            )
            _intent_cache[cache_key] = result.to_dict()
            return result
        
        # === LLM CLASSIFICATION ===
        prompt = UNIVERSAL_INTENT_PROMPT.format(
            message=text,
            style=conversation_style or "english"
        )
        
        response = await gemini_adapter.generate_response(
            context=[],
            prompt=prompt,
            override_tools=[],
            model_tier="fast",  # Use fast model for classification
        )
        
        # Parse JSON response
        response_text = str(response).strip()
        
        # Extract JSON if wrapped in markdown
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()
        
        intent_data = json.loads(response_text)
        
        # Validate and create IntentResult
        result = IntentResult(
            primary_agent=intent_data.get("primary_agent", "CHAT"),
            whatsapp_send=intent_data.get("whatsapp_send", False),
            whatsapp_read=intent_data.get("whatsapp_read", False),
            whatsapp_delete=intent_data.get("whatsapp_delete", False),
            email_send=intent_data.get("email_send", False),
            email_read=intent_data.get("email_read", False),
            email_delete=intent_data.get("email_delete", False),
            camera_outfit=intent_data.get("camera_outfit", False),
            camera_review=intent_data.get("camera_review", False),
            camera_photo=intent_data.get("camera_photo", False),
            youtube_play=intent_data.get("youtube_play", False),
            youtube_data=intent_data.get("youtube_data", False),
            media_control=intent_data.get("media_control", False),
            wallpaper_change=intent_data.get("wallpaper_change", False),
            volume_control=intent_data.get("volume_control", False),
            brightness_control=intent_data.get("brightness_control", False),
            power_action=intent_data.get("power_action", False),
            wifi_control=intent_data.get("wifi_control", False),
            bluetooth_control=intent_data.get("bluetooth_control", False),
            file_create=intent_data.get("file_create", False),
            file_read=intent_data.get("file_read", False),
            file_delete=intent_data.get("file_delete", False),
            file_search=intent_data.get("file_search", False),
            app_open=intent_data.get("app_open", False),
            app_close=intent_data.get("app_close", False),
            chrome_profile=intent_data.get("chrome_profile"),
            web_search=intent_data.get("web_search", False),
            news_query=intent_data.get("news_query", False),
            create_widget=intent_data.get("create_widget", False),
            widget_type=intent_data.get("widget_type"),
            code_execution=intent_data.get("code_execution", False),
            script_create=intent_data.get("script_create", False),
            is_greeting=intent_data.get("is_greeting", False),
            is_question=intent_data.get("is_question", False),
            is_casual_chat=intent_data.get("is_casual_chat", False),
            confidence=intent_data.get("confidence", 1.0),
            entities=intent_data.get("entities", {}),
        )
        
        # Cache result
        _intent_cache[cache_key] = result.to_dict()
        
        logger.info(f"[Intent Classified] {text[:50]} → agent={result.primary_agent}, intents={_get_active_intents(result)}")
        return result
        
    except Exception as e:
        logger.error(f"[Universal Intent Classifier] Failed: {e}", exc_info=True)
        # Safe fallback: route to CHAT
        return IntentResult(
            primary_agent="CHAT",
            is_question=True,
            confidence=0.0
        )


def _get_active_intents(result: IntentResult) -> List[str]:
    """Get list of active intent flags for logging."""
    active = []
    for key, value in result.__dict__.items():
        if isinstance(value, bool) and value and not key.startswith("is_"):
            active.append(key)
    return active


def clear_intent_cache():
    """Clear the intent classification cache."""
    global _intent_cache, _cache_hits, _cache_misses
    _intent_cache.clear()
    _cache_hits = 0
    _cache_misses = 0
    logger.info("[Intent Cache] Cleared")


def get_cache_stats() -> Dict[str, int]:
    """Get cache performance statistics."""
    return {
        "hits": _cache_hits,
        "misses": _cache_misses,
        "size": len(_intent_cache),
        "hit_rate": _cache_hits / (_cache_hits + _cache_misses) if (_cache_hits + _cache_misses) > 0 else 0.0
    }
