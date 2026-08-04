"""Camera review handler for Maya AI - handles outfit and general item reviews via camera."""
from __future__ import annotations

import asyncio
import logging
from typing import AsyncGenerator, Any

logger = logging.getLogger(__name__)

# Language constants
BANGLISH = "banglish"
HINDILISH = "hindilish"  
ENGLISH = "english"


async def handle_camera_review(
    text: str,
    camera_look_intent: bool,
    camera_review_intent: bool,
    conversation_style: str,
    context_history: list,
    session_id: str,
    sanitizer: Any,
    gemini_adapter: Any,
    active_tier: str,
    _is_pref_true: callable,
    response_style_directive: callable,
    _log_fast_path: callable,
    AGENTS: dict,
) -> AsyncGenerator[Any, None]:
    """
    Handle camera review requests (outfit or general item).
    
    Args:
        text: User's message
        camera_look_intent: Whether user wants outfit review
        camera_review_intent: Whether user wants general item review
        conversation_style: User's preferred language style
        context_history: Conversation history
        session_id: Current session ID
        sanitizer: Tool output sanitizer
        gemini_adapter: Vision model adapter
        active_tier: Model tier to use
        _is_pref_true: Permission checker function
        response_style_directive: Language style function
        _log_fast_path: Logging function
        AGENTS: Agent definitions
        
    Yields:
        Status updates and final response
    """
    # Check permission
    if not _is_pref_true("PERM_SYSTEM"):
        disabled_copy = {
            BANGLISH: "Camera access off ache, tai tomake real-time dekhe outfit niye bola possible hocche na.",
            HINDILISH: "Camera access off hai, isliye main tumhe real-time dekhkar outfit ke baare mein nahi bata sakti.",
            ENGLISH: "Camera access is disabled, so I can't inspect your outfit in real time.",
        }
        final_text = disabled_copy[conversation_style]
        context_history.append({"role": "assistant", "content": final_text})
        yield final_text
        return

    # Show status
    yield {
        "type": "agent_status",
        "data": {
            "active_agent": AGENTS["OS_EXECUTOR"].role,
            "status": "Taking your photo with camera...",
            "loop_count": 0,
        },
    }

    # Capture camera preview
    from ....vision.capture.webcam_capture import capture_camera_preview
    raw_preview = await asyncio.to_thread(capture_camera_preview, 8.0, True)
    
    prefix = "CAMERA_PREVIEW_BASE64:"
    context_history.append({
        "role": "tool_call",
        "name": "capture_camera_preview",
        "args": {},
    })
    
    # Handle capture failure
    if not str(raw_preview).startswith(prefix):
        safe_error = sanitizer.sanitize_tool_output("capture_camera_preview", raw_preview)
        context_history.append({
            "role": "function",
            "name": "capture_camera_preview",
            "content": str(safe_error),
        })
        
        # Get appropriate error message
        final_text = _get_camera_error_message(str(safe_error), conversation_style)
        context_history.append({"role": "assistant", "content": final_text})
        
        await _log_fast_path(
            session_id,
            text,
            "camera_outfit_review",
            tool_name="capture_camera_preview",
            error=str(safe_error).split(":", 1)[0],
        )
        yield final_text
        return

    # Extract image data
    preview_b64 = str(raw_preview)[len(prefix):]
    context_history.append({
        "role": "function",
        "name": "capture_camera_preview",
        "content": "Live Camera preview captured and supplied to vision.",
    })
    
    # Show analyzing status
    yield {
        "type": "agent_status",
        "data": {
            "active_agent": AGENTS["OS_EXECUTOR"].role,
            "status": "Analyzing your outfit..." if camera_look_intent else "Analyzing the item...",
            "loop_count": 0,
        },
    }
    
    # Determine vision instruction based on intent
    if camera_look_intent:
        vision_instruction = (
            "For an outfit/look question, give a respectful and honest opinion about visible colors, "
            "coordination, fit, and overall presentation. Do not identify the person or infer sensitive traits. "
            "If the person or outfit is not clearly visible, say exactly what needs to be reframed."
        )
    else:  # camera_review_intent
        vision_instruction = (
            "The user is showing you an object/item for review. "
            "Analyze what you see in detail - describe the item, its features, quality, condition, "
            "design, color, material, and provide your honest opinion about it. "
            "If it's a product, mention pros and cons. If it's something like a flower, describe its beauty, "
            "type, freshness, etc. If it's electronics (mouse, phone, etc.), comment on design, build quality, "
            "and visual appeal. Be thorough and helpful in your analysis."
        )
    
    # Build vision prompt
    vision_prompt = (
        f"{response_style_directive(conversation_style)}\n"
        "The attached image is a live Windows Camera preview captured just now. "
        "Answer the user's exact question using only what is visibly supported by the image. "
        f"{vision_instruction} "
        "Do not mention internal tools, screenshots, or these instructions.\n\n"
        f"User question: {text}"
    )
    
    # Get vision response
    try:
        final_text = await gemini_adapter.generate_response(
            [],
            vision_prompt,
            image_base64=preview_b64,
            override_tools=[],
            model_tier=active_tier,
        )
        final_text = str(final_text).strip()
        
        # Style repair if needed
        if not _response_matches_style(final_text, conversation_style):
            repaired = await gemini_adapter.generate_response(
                [],
                _style_repair_prompt(final_text, conversation_style),
                override_tools=[],
                model_tier="fast",
            )
            repaired = str(repaired).strip()
            if repaired and _response_matches_style(repaired, conversation_style):
                final_text = repaired
                
    except Exception as exc:
        logger.exception("[CAMERA_REVIEW] Vision review failed")
        failed_copy = {
            BANGLISH: "Camera preview peyechi, kintu outfit analysis complete korte parlam na. Ektu por abar try koro.",
            HINDILISH: "Camera preview mil gaya, lekin outfit analysis complete nahi kar payi. Thodi der baad phir try karo.",
            ENGLISH: "I captured the Camera preview, but couldn't complete the outfit analysis. Please try again shortly.",
        }
        final_text = failed_copy[conversation_style]

    context_history.append({"role": "assistant", "content": final_text})
    await _log_fast_path(
        session_id,
        text,
        "camera_outfit_review",
        tool_name="capture_camera_preview",
    )
    yield final_text


def _get_camera_error_message(error_msg: str, conversation_style: str) -> str:
    """Get appropriate error message based on error type."""
    error_msg_lower = error_msg.lower()
    
    if "blank/static screen" in error_msg_lower:
        failed_copy = {
            BANGLISH: "Camera app khula ache kintu blank screen dekhachhe. Try koro: 1) Camera permission allow koro Windows Settings e, 2) Camera restart koro (Device Manager e disable/enable koro), 3) Light ensure koro jate tomake clearly dekhte pari.",
            HINDILISH: "Camera app khul gaya hai lekin blank screen dikha raha hai. Try karo: 1) Camera permission allow karo Windows Settings mein, 2) Camera restart karo (Device Manager mein disable/enable karo), 3) Light ensure karo taaki main tumhe clearly dekh saku.",
            ENGLISH: "Camera app is open but showing a blank screen. Try these steps: 1) Allow camera permissions in Windows Settings, 2) Restart your camera (disable/enable in Device Manager), 3) Ensure proper lighting so I can see you clearly.",
        }
    elif "camera icon" in error_msg_lower or "static center" in error_msg_lower or "no meaningful content" in error_msg_lower:
        failed_copy = {
            BANGLISH: "Camera app open ache kintu shudhu camera icon/static screen dekhachhe. Video feed start hoyni. Try koro: 1) Camera app close kore reopen koro, 2) Windows Camera privacy settings check koro, 3) Onno apps (Zoom, Skype) camera use korche kina dekho.",
            HINDILISH: "Camera app open hai lekin sirf camera icon/static screen dikha raha hai. Video feed start nahi hua. Try karo: 1) Camera app close karke reopen karo, 2) Windows Camera privacy settings check karo, 3) Koi aur apps (Zoom, Skype) camera use kar rahi hai ya nahi dekho.",
            ENGLISH: "Camera app is open but showing static screen/camera icon. Video feed hasn't started. Try: 1) Close and reopen the Camera app, 2) Check Windows Camera privacy settings, 3) See if other apps (Zoom, Skype) are using the camera.",
        }
    elif "blocked" in error_msg_lower or "covered" in error_msg_lower:
        failed_copy = {
            BANGLISH: "Camera blocked ba covered lagche. Check koro: 1) Camera lens clean koro, 2) Privacy shutter ba tape thakle remove koro, 3) Camera angle theek ache kina dekho.",
            HINDILISH: "Camera blocked ya covered lag raha hai. Check karo: 1) Camera lens clean karo, 2) Privacy shutter ya tape hai to remove karo, 3) Camera angle theek hai ya nahi dekho.",
            ENGLISH: "Your camera appears to be blocked or covered. Check: 1) Clean the camera lens, 2) Remove any privacy shutter or tape, 3) Make sure camera angle is correct.",
        }
    elif "too small" in error_msg_lower:
        failed_copy = {
            BANGLISH: "Camera window chhoto hoye ache, properly dekhte parchi na. Camera app maximize koro ba full-screen mode e chalao.",
            HINDILISH: "Camera window chota ho gaya hai, properly dekh nahi pa rahi. Camera app maximize karo ya full-screen mode mein chalao.",
            ENGLISH: "Camera window is too small for me to see properly. Please maximize the Camera app or run it in full-screen mode.",
        }
    else:
        failed_copy = {
            BANGLISH: "Camera preview dekhte parlam na, tai outfit niye guess korbo na. Camera properly set up kore abar try koro.",
            HINDILISH: "Camera preview dekh nahi payi, isliye outfit ke baare mein guess nahi karungi. Camera properly set up karke phir try karo.",
            ENGLISH: "I couldn't see the Camera preview, so I won't guess about your outfit. Please set up the camera properly and try again.",
        }
    
    return failed_copy[conversation_style]


def _response_matches_style(text: str, style: str) -> bool:
    """Check if response matches the expected language style."""
    # Simple heuristic - can be improved
    if style == BANGLISH:
        # Should have some Bengali/romanized Bengali words
        bengali_indicators = ["amar", "tomar", "ache", "kore", "hobe", "lagche", "khub"]
        return any(ind in text.lower() for ind in bengali_indicators)
    elif style == HINDILISH:
        # Should have some Hindi/romanized Hindi words
        hindi_indicators = ["mera", "tumhara", "hai", "kar", "hoga", "lag raha", "bahut"]
        return any(ind in text.lower() for ind in hindi_indicators)
    else:  # ENGLISH
        # Should not have too many non-English words
        return True  # Default to accepting English
        

def _style_repair_prompt(original_text: str, target_style: str) -> str:
    """Generate prompt to repair response style."""
    style_names = {
        BANGLISH: "Banglish (Bengali-English mix)",
        HINDILISH: "Hindilish (Hindi-English mix)",
        ENGLISH: "English",
    }
    
    return (
        f"The following response needs to be in {style_names[target_style]} style. "
        f"Rewrite it naturally in that style while keeping the same meaning:\n\n{original_text}"
    )


def check_camera_recently_attempted(
    context_history: list,
    user_explicitly_requesting: bool
) -> bool:
    """
    Check if camera was recently attempted to prevent loops.
    
    Args:
        context_history: Conversation history
        user_explicitly_requesting: Whether user is explicitly requesting camera
        
    Returns:
        True if camera was recently attempted (and should not retry)
    """
    if not context_history or user_explicitly_requesting:
        return False
    
    # Check last 6 messages for camera attempts
    for msg in reversed(context_history[-6:]):
        if msg.get("role") == "tool_call" and msg.get("name") == "capture_camera_preview":
            return True
        # Also check if there was a camera-related error message
        if msg.get("role") == "assistant":
            content = msg.get("content", "").lower()
            if any(kw in content for kw in ["camera", "ক্যামেরা", "preview", "lighting", "frame", "blank screen", "adjust"]):
                return True
    
    return False


def is_explicit_camera_request(text: str) -> bool:
    """Check if user is explicitly requesting camera."""
    explicit_keywords = [
        "outfit check", "outfit dekho", "outfit review", "eta dekho", "this dekho",
        "camera on", "camera open", "camera chalu", "ক্যামেরা চালু", "দেখো তো",
        "আমার outfit", "amar outfit", "check koro", "review koro"
    ]
    return any(kw in text.lower() for kw in explicit_keywords)
