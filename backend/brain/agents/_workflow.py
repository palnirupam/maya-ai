import logging
import json
import asyncio
import re
from typing import AsyncGenerator, Union

logger = logging.getLogger(__name__)
from ..providers.gemini_adapter import gemini_adapter
from .agent_defs import AGENTS, ROUTING_PROMPT
from ..gemini.function_calls import get_maya_tools
from .tool_router import select_relevant_tools, ROUTER_SIZE_GATE, _SEND_INTENT_RE
from .handlers.camera_handler import (
    handle_camera_review,
    check_camera_recently_attempted,
    is_explicit_camera_request,
)
# OLD: Deprecated camera-only intent classifier (no longer used)
# from .intent_classifier import classify_intent
from .intent_parsing import (
    is_generic_youtube_video_query, parse_foreground_youtube_play_intent,
    parse_youtube_mode_answer, _parse_direct_os_action, _format_direct_os_response,
    is_whatsapp_ui_intent,
)
from .execution_policy import adaptive_tool_round_limit, build_execution_brief, completion_audit_prompt, requires_tool_completion
from ..reasoning.tool_planner import tool_planner
from ..security_filter import sanitizer
from ..language_style import BANGLISH, ENGLISH, HINDILISH, LANGUAGE_STYLES, detect_conversation_style, detect_language_style, response_matches_style, response_style_directive, set_latest_conversation_style, style_repair_prompt
from ._tool_response_translator import translate_tool_response
from ._approval import FailureRecord, MAX_TOOL_OUTPUT_CHARS, DANGER_TOOLS, _DANGER_PC_ACTIONS, _DANGER_SHORTCUT_ACTIONS, _DANGER_FILE_ACTIONS, _ACTION_ALIASES, _canonical_action, _tool_call_requires_approval
from ._session_state import (
    _LAST_AGENT_BY_SESSION, _LAST_DIRECT_APP_BY_SESSION, _LAST_OS_CONTROL_BY_SESSION,
    _PENDING_SEND_BY_SESSION, _PENDING_YOUTUBE_TITLE_BY_SESSION, _PENDING_YOUTUBE_MODE_BY_SESSION,
    _LAST_AGENT_MAX_SESSIONS, _LAST_DIRECT_APP_NAME, _SEND_EXECUTING_TOOLS, _SEND_FLOW_TOOLS,
    _delivery_fingerprint, _remember_last_agent, _remember_direct_app, _remember_os_control,
    _remember_pending_send, _remember_pending_youtube_title, _remember_pending_youtube_mode,
    evict_session_state,
)
from ._routing import (
    _OS_PATTERNS, _RESEARCH_PATTERNS, _STRONG_RESEARCH_PATTERNS, _TODAY_NEWS_VARIANT_RE,
    _OS_STATUS_RE, _CAMERA_LOOK_INTENT_RE, _CAMERA_REVIEW_INTENT_RE, _CODER_PATTERNS, _CANVAS_PATTERNS, _FILE_ON_DISK_PATTERNS,
    _GREETING_PATTERNS, _FILE_SELECTION_FOLLOWUP_RE,
    _carries_tool_signal, _tool_router_query, _last_app_from_history,
    _parse_bulk_app_close, _parse_direct_app_action, _fast_route,
    _previous_user_messages, _router_context_prefix, _format_direct_app_response
)
from ._context_builder import (
    _IST, _CLARIFY_PICK, _CLARIFY_NOT_FOUND, _NOT_FOUND_DETAIL,
    _YT_TITLE_REQUEST, _YT_MODE_REQUEST, _YT_FG_SUCCESS, _YT_FG_PARTIAL, _YT_FG_FAILED,
    _YT_BG_SUCCESS, _YT_BG_FAILED, _SYSTEM_COPY,
    _detect_user_lang, _style_msg, _format_clarification, _is_pref_true,
    _render_time_block, _build_agent_context,
)
from ._tool_executor import (
    _declared_tool_names, _merge_mcp_tool_schemas,
    _summarize_completed_actions, _run_tool, _log_fast_path,
)

async def execute_workflow(
    session_id: str,
    text: str,
    context_history: list[dict],
    image_base64: str = None
) -> AsyncGenerator[Union[str, dict], None]:
    """
    Stateful execution coordinator for the Multi-Agent team.
    Routes tasks to agents, runs specialized execution loops,
    and passes inter-agent results downstream.
    """
    logger.info(f"Multi-agent workflow routing request: {text}")
    conversation_style = detect_conversation_style(text, context_history)
    if text.startswith("SYSTEM_EVENT_STARTUP_GREETING"):
        conversation_style = BANGLISH
    else:
        set_latest_conversation_style(conversation_style)
    
    # ══════════════════════════════════════════════════════════════════════════
    # ULTRA-FAST PRE-ROUTING (Before any LLM/analysis)
    # ══════════════════════════════════════════════════════════════════════════
    # For extremely common commands, skip ALL processing and route directly
    # This saves ~300-400ms by avoiding router, analysis, and intent classification
    
    text_lower = text.lower().strip()
    
    # Pattern 1: Simple app open/close (instant)
    if len(text_lower) < 50 and not image_base64:
        # "open youtube", "youtube kholo", "yt kholo", "close chrome", etc.
        app_match = re.match(r'^(open|close|kholo|bondho|band|chalu|on|off)\s+(youtube|yt|chrome|whatsapp|notepad|calculator|paint|word|excel)$', text_lower)
        if app_match:
            logger.info(f"[ULTRA-FAST] Simple app command detected, skipping analysis")
            # Let the existing direct_app_candidate flow handle it below
            # But we've saved time by not doing analysis
    
    # Pattern 2: Simple greetings (instant response)
    if text_lower in {'hi', 'hello', 'hey', 'ok', 'okay', 'thanks', 'thank you', 'bye'}:
        logger.info(f"[ULTRA-FAST] Greeting detected, immediate response")
        greeting_response = {
            'hi': 'Hello!',
            'hello': 'Hi there!',
            'hey': 'Hey!',
            'ok': 'Alright.',
            'okay': 'Sure.',
            'thanks': 'Welcome!',
            'thank you': 'You\'re welcome!',
            'bye': 'Goodbye!'
        }
        quick_response = greeting_response.get(text_lower, 'Hi!')
        # Localize to user's language
        if conversation_style == BANGLISH:
            quick_response = {'hi': 'Hello!', 'hello': 'Haan bolo!', 'hey': 'Haan!', 'ok': 'Thik ache.', 'okay': 'Hobe.', 'thanks': 'Mention not!', 'thank you': 'Swaagotom!', 'bye': 'Tata bye!'}[text_lower] if text_lower in {'hi', 'hello', 'hey', 'ok', 'okay', 'thanks', 'thank you', 'bye'} else quick_response
        elif conversation_style == HINDILISH:
            quick_response = {'hi': 'Hello!', 'hello': 'Haan bolo!', 'hey': 'Haan!', 'ok': 'Theek hai.', 'okay': 'Hoga.', 'thanks': 'Koi baat nahi!', 'thank you': 'Shukriya!', 'bye': 'Alvida!'}[text_lower] if text_lower in {'hi', 'hello', 'hey', 'ok', 'okay', 'thanks', 'thank you', 'bye'} else quick_response
        
        context_history.append({"role": "assistant", "content": quick_response})
        yield quick_response
        return

    # ── Phase A: Intent Sentinel (Security Layer) ────────────────────────────
    from .intent_sentinel import IntentSentinel
    from ...system.state_manager import state_manager
    ctx_prompt_info = state_manager.get_prompt_context()
    active_mode = ctx_prompt_info.get("mode_name", "professional")
    capabilities = ctx_prompt_info.get("capabilities", [])

    intent_decision = IntentSentinel.evaluate(text, active_mode, capabilities)
    if intent_decision.status == "block":
        await _log_fast_path(session_id, text, "sentinel_block", error=intent_decision.reason)
        yield intent_decision.suggested_action or intent_decision.reason
        return
    # NOTE: IntentSentinel never returns "needs_approval" — it has no way to
    # pause and resume a turn, so that verdict was a dead end (see
    # intent_sentinel.py). The real approval gate for shutdown/restart/etc.
    # is the DANGER_TOOLS check further down this file, which properly
    # round-trips through a tool_call_request approve/deny event.

    # ── Phase B: Analysis Pass + BudgetManager ────────────────────────────────
    from ..reasoning.analysis_pass import run_heuristic_pass, build_task_graph_if_needed
    from ..budget_manager import budget_manager

    analysis_result = run_heuristic_pass(text, context_history)
    analysis_result = await build_task_graph_if_needed(analysis_result, text, context_history)

    # Register the intended tier with BudgetManager — it may downgrade silently
    # if this session has already exceeded its budget. The downgrade message (if
    # any) is surfaced inline below so the user always knows.
    budget_manager.set_requested_tier(session_id, analysis_result.model_tier)

    # The tier actually in force for this turn — may be lower than requested
    # if a prior turn in this session already downgraded it. This is what
    # gets passed to the main reasoning call below so the tier genuinely
    # picks the model instead of just being logged.
    active_tier = budget_manager.get_active_tier(session_id)

    # Emit downgrade notification if budget was previously exceeded
    downgrade_msg = budget_manager.pop_downgrade_notification(session_id)
    if downgrade_msg:
        yield downgrade_msg

    execution_graph = (
        analysis_result.task_graph
        if analysis_result.needs_task_graph and isinstance(analysis_result.task_graph, dict)
        else None
    )
    execution_brief = build_execution_brief(execution_graph, text)
    if execution_brief:
        step_count = len(execution_graph.get("tasks", []))
        logger.info(
            "[AgentTeam] Prepared adaptive plan with %s steps; "
            "continuing through the full tool-capable agent loop.",
            step_count,
        )
        yield {
            "type": "agent_status",
            "data": {
                "active_agent": "Planner",
                "status": f"Prepared {step_count}-step adaptive plan.",
                "loop_count": 0,
            },
        }

    # ── 1. Routing phase ─────────────────────────────────────────────────────
    # Try fast keyword router first (saves ~1-2s Gemini call). Pass the last
    # agent so short follow-ups can stick to it instead of collapsing to CHAT,
    # and the one-shot pending-send flag so a mid-send clarification reply
    # ("Likho je valo achis") continues on OS_EXECUTOR instead of CHAT.
    pending_send = _PENDING_SEND_BY_SESSION.pop(session_id, None) is not None
    _pending_yt_style = _PENDING_YOUTUBE_TITLE_BY_SESSION.pop(session_id, None)
    pending_youtube_title = _pending_yt_style is not None
    if pending_youtube_title and _pending_yt_style in LANGUAGE_STYLES:
        # The title reply ("Bangla best cinema") carries no style markers of its
        # own — keep the style the question was asked in, don't flip to English.
        conversation_style = _pending_yt_style
    if not pending_youtube_title and not image_base64 and text.strip():
        # The in-memory flag can be lost (backend restart, or the title
        # question was asked by the LLM loop instead of the deterministic
        # gate). Re-derive it from history: if the PREVIOUS user message was
        # a generic visible-YouTube request ("yt te cinema chaliye dao") and
        # this reply carries no other tool signal, treat it as the awaited
        # title — otherwise the ≤3-word branch strands it on CHAT, which has
        # no YouTube tools, and Maya falsely claims the tool is missing.
        _prevs = _previous_user_messages(context_history, text, n=1)
        _cancelish = re.search(
            r"\b(na|thak|cancel|bad|dorkar|lagbe na|stop|bondho)\b", text, re.IGNORECASE
        )
        if _prevs and not _carries_tool_signal(text) and not _cancelish:
            _prev_yt_q = parse_foreground_youtube_play_intent(_prevs[-1])
            if _prev_yt_q and is_generic_youtube_video_query(_prev_yt_q):
                pending_youtube_title = True
                # Same style-continuity rule as the stored-flag path: the reply
                # is just a title, so inherit the asking turn's style.
                _prev_style = detect_conversation_style(_prevs[-1], context_history)
                if _prev_style in LANGUAGE_STYLES:
                    conversation_style = _prev_style
    last_direct_app = _last_app_from_history(context_history, session_id)
    direct_app_candidate = (
        _parse_direct_app_action(text, last_direct_app)
        if not image_base64
        else None
    )
    # Parse deterministic OS controls before choosing an agent. Otherwise a
    # valid device command can be sent to CHAT/Canvas by keyword or context
    # routing before the direct executor gets a chance to handle it.
    direct_os_candidate = (
        _parse_direct_os_action(text, _LAST_OS_CONTROL_BY_SESSION.get(session_id))
        if not image_base64
        else None
    )
    youtube_request_query = (
        parse_foreground_youtube_play_intent(text)
        if not image_base64
        else None
    )
    youtube_title_needed = is_generic_youtube_video_query(youtube_request_query)
    # HOW should it play? "dekhbo/video" → visible screen; "shunbo/background"
    # → VLC audio. A YT play request naming WHAT but not HOW must be confirmed
    # first so audio never pops a browser window and vice versa.
    pending_youtube_mode_query = (
        _PENDING_YOUTUBE_MODE_BY_SESSION.pop(session_id, None)
        if not image_base64
        else None
    )
    youtube_mode = parse_youtube_mode_answer(text) if not image_base64 else None
    youtube_mode_needed_query = None
    background_youtube_query = None
    foreground_youtube_query = None
    if pending_youtube_title and not image_base64 and text.strip():
        # Reply carries the awaited title; the original request was a
        # watch-worded one (cinema/movie/video) so visible playback is right.
        foreground_youtube_query = text.strip()
    elif pending_youtube_mode_query:
        if youtube_mode == "background":
            background_youtube_query = pending_youtube_mode_query
        elif youtube_mode == "foreground":
            foreground_youtube_query = pending_youtube_mode_query
        # else: answer names no mode (maybe a topic change) → normal routing.
    elif youtube_request_query and not youtube_title_needed:
        if youtube_mode == "background":
            background_youtube_query = youtube_request_query
        elif youtube_mode == "foreground":
            foreground_youtube_query = youtube_request_query
        else:
            youtube_mode_needed_query = youtube_request_query
    # A syntactically complete app command is more authoritative than keyword
    # routing. In particular, a one-word follow-up such as "Close" used to hit
    # the short-chat branch before the remembered app could be consulted, making
    # Maya incorrectly claim it lacked the required tool. Route these commands
    # straight to the deterministic app executor instead.
    agents_to_run = (
        ["OS_EXECUTOR"]
        if youtube_title_needed or foreground_youtube_query
        or background_youtube_query or youtube_mode_needed_query
        or direct_app_candidate or direct_os_candidate
        else _fast_route(
            text, _LAST_AGENT_BY_SESSION.get(session_id), pending_send=pending_send
        )
    )
    if agents_to_run:
        logger.info(f"Router response (fast-route): {agents_to_run}")
    else:
        # Fall back to Gemini router for ambiguous messages. Prepend a hint of the
        # recent turn so follow-ups ("50% koro" after "volume 20% koro") resolve.
        ctx_prefix = _router_context_prefix(context_history, text)
        routing_context = [
            {"role": "system", "content": ROUTING_PROMPT},
            {"role": "user", "content": f"{ctx_prefix}Request: {text}"}
        ]
        routing_response = ""
        try:
            routing_response = await gemini_adapter.generate_response(
                routing_context, f"{ctx_prefix}Request: {text}", override_tools=[]
            )
            logger.info(f"Router response (gemini): {routing_response}")

            cleaned_resp = routing_response.strip()
            if "```" in cleaned_resp:
                cleaned_resp = cleaned_resp.split("```")[1]
                if cleaned_resp.startswith("json"):
                    cleaned_resp = cleaned_resp[4:]
                cleaned_resp = cleaned_resp.strip()

            parsed = json.loads(cleaned_resp)
            agents_to_run = parsed.get("agents", [])
        except Exception as e:
            logger.warning(f"Failed to parse agent routing JSON. Error: {e}")
            agents_to_run = []
            if routing_response:
                for agent_name in ["RESEARCHER", "CODER", "OS_EXECUTOR"]:
                    if agent_name in routing_response.upper():
                        agents_to_run.append(agent_name)

    cleaned_agents = []
    for agent in agents_to_run:
        upper = agent.upper()
        if upper in AGENTS and upper not in cleaned_agents:
            cleaned_agents.append(upper)

    if not cleaned_agents:
        cleaned_agents = ["CHAT"]

    logger.info(f"Target agents scheduled in order: {cleaned_agents}")

    # Remember the primary agent so the NEXT turn's follow-up can stick to it.
    _remember_last_agent(session_id, cleaned_agents[-1])

    direct_app_action = (
        direct_app_candidate
        if cleaned_agents == ["OS_EXECUTOR"] and not image_base64
        else None
    )
    direct_youtube_query = (
        foreground_youtube_query
        if cleaned_agents == ["OS_EXECUTOR"] and not image_base64
        else None
    )
    direct_youtube_bg_query = (
        background_youtube_query
        if cleaned_agents == ["OS_EXECUTOR"] and not image_base64
        else None
    )
    if direct_app_action and not _is_pref_true("PERM_SYSTEM"):
        direct_app_action = None
    if direct_youtube_query and not _is_pref_true("PERM_SYSTEM"):
        direct_youtube_query = None
    if direct_youtube_bg_query and not _is_pref_true("PERM_SYSTEM"):
        direct_youtube_bg_query = None
    
    # ══════════════════════════════════════════════════════════════════════════
    # FAST-PATH INTENT DETECTION (Instant, No LLM)
    # ══════════════════════════════════════════════════════════════════════════
    # For simple, unambiguous commands, use instant regex patterns.
    # Only call LLM for complex/ambiguous queries.
    # This keeps common actions instant while providing AI power when needed.
    
    from .universal_intent_classifier import classify_universal_intent
    
    # Quick pre-check: Does this need AI classification?
    text_lower = text.lower().strip()
    needs_llm_classification = True
    camera_look_intent = False
    camera_review_intent = False
    is_wallpaper_request = False
    
    # Fast-path patterns (instant, no LLM call)
    if len(text_lower) < 100:  # Short commands are usually simple
        # Simple greetings (already handled by fast_route, but double-check)
        if text_lower in {'hi', 'hello', 'hey', 'ok', 'okay', 'hmm', 'yes', 'no'}:
            needs_llm_classification = False
        
        # Simple SINGLE app commands (instant)
        # But if there's "and" or multiple actions, use LLM for multi-intent
        elif ' and ' not in text_lower and not any(op in text_lower for op in [' ar ', ' o ', ' এবং ', ' aur ']):
            if any(word in text_lower for word in ['open', 'close', 'kholo', 'bondho', 'band']):
                # These are handled by direct_app_candidate already, skip LLM
                if direct_app_candidate or any(app in text_lower for app in [
                    'youtube', 'chrome', 'whatsapp', 'notepad', 'calculator', 'yt'
                ]):
                    needs_llm_classification = False
        
        # Wallpaper keywords (instant detection) - but not if complex query
        if ' and ' not in text_lower and any(kw in text_lower for kw in ['wallpaper', 'background', 'desktop theme']):
            is_wallpaper_request = True
            # Still might need LLM if it's feedback ("valo lagche na")
            if not any(feedback in text_lower for feedback in ['lagche', 'lagchi', 'pasondo', 'valo', 'bhalo', 'like']):
                needs_llm_classification = False
    
    # Only call LLM if needed
    universal_intent = None
    if needs_llm_classification:
        try:
            universal_intent = await classify_universal_intent(
                text,
                use_cache=True,
                context_history=context_history,
                conversation_style=conversation_style
            )
            camera_look_intent = universal_intent.camera_outfit
            camera_review_intent = universal_intent.camera_review
            is_wallpaper_request = universal_intent.wallpaper_change
        except Exception as e:
            logger.warning(f"Intent classification failed: {e}. Using regex fallback.")
            # Fallback to regex if LLM fails
            camera_look_intent = bool(_CAMERA_LOOK_INTENT_RE.search(text))
            camera_review_intent = bool(_CAMERA_REVIEW_INTENT_RE.search(text))
            is_wallpaper_request = bool(re.search(r'\b(wallpaper|background|theme|desktop)\b', text, re.IGNORECASE))
    
    # CRITICAL: Wallpaper requests never trigger camera
    if is_wallpaper_request:
        camera_look_intent = False
        camera_review_intent = False
    
    # Check if we should trigger camera
    user_explicitly_requesting = is_explicit_camera_request(text)
    camera_recently_attempted = check_camera_recently_attempted(context_history, user_explicitly_requesting)
    
    # Handle camera review if appropriate
    if (camera_look_intent or camera_review_intent) and cleaned_agents == ["OS_EXECUTOR"] and not image_base64 and not camera_recently_attempted:
        # Delegate to camera handler
        async for result in handle_camera_review(
            text=text,
            camera_look_intent=camera_look_intent,
            camera_review_intent=camera_review_intent,
            conversation_style=conversation_style,
            context_history=context_history,
            session_id=session_id,
            sanitizer=sanitizer,
            gemini_adapter=gemini_adapter,
            active_tier=active_tier,
            _is_pref_true=_is_pref_true,
            response_style_directive=response_style_directive,
            _log_fast_path=_log_fast_path,
            AGENTS=AGENTS,
        ):
            yield result
        return
    if youtube_mode_needed_query and cleaned_agents == ["OS_EXECUTOR"]:
        # WHAT to play is known, HOW is not — confirm before touching anything.
        _remember_pending_youtube_mode(session_id, youtube_mode_needed_query)
        final_text = _style_msg(
            _YT_MODE_REQUEST, conversation_style, query=youtube_mode_needed_query
        )
        context_history.append({"role": "assistant", "content": final_text})
        await _log_fast_path(
            session_id,
            text,
            "youtube_mode_request",
        )
        yield final_text
        return
    if direct_youtube_bg_query:
        logger.info(
            "Direct background YouTube playback matched: %r",
            direct_youtube_bg_query,
        )
        yield {
            "type": "agent_status",
            "data": {
                "active_agent": AGENTS["OS_EXECUTOR"].role,
                "status": "Playing in the background...",
                "loop_count": 0,
            },
        }

        from ...tools.desktop.advanced.youtube_player import play_youtube_background

        try:
            raw_result = play_youtube_background(direct_youtube_bg_query)
        except Exception as exc:
            logger.exception("[DIRECT_YOUTUBE_BG] Background playback failed")
            raw_result = f"ERROR: Background playback failed unexpectedly: {exc}"

        safe_result = sanitizer.sanitize_tool_output("play_youtube_background", raw_result)
        context_history.append({
            "role": "tool_call",
            "name": "play_youtube_background",
            "args": {"query": direct_youtube_bg_query},
        })
        context_history.append({
            "role": "function",
            "name": "play_youtube_background",
            "content": str(safe_result),
        })

        if str(safe_result).startswith("SUCCESS"):
            final_text = _style_msg(
                _YT_BG_SUCCESS, conversation_style, query=direct_youtube_bg_query
            )
        else:
            final_text = _style_msg(
                _YT_BG_FAILED, conversation_style,
                query=direct_youtube_bg_query, result=safe_result,
            )

        context_history.append({"role": "assistant", "content": final_text})
        await _log_fast_path(
            session_id,
            text,
            "background_youtube",
            tool_name="play_youtube_background",
            error=None if str(safe_result).startswith("SUCCESS") else str(safe_result).split(":", 1)[0],
        )
        yield final_text
        return
    if youtube_title_needed:
        _remember_pending_youtube_title(session_id, conversation_style)
        final_text = _style_msg(_YT_TITLE_REQUEST, conversation_style)
        context_history.append({"role": "assistant", "content": final_text})
        await _log_fast_path(
            session_id,
            text,
            "youtube_title_request",
        )
        yield final_text
        return
    if direct_youtube_query:
        logger.info(
            "Direct foreground YouTube playback matched: %r",
            direct_youtube_query,
        )
        yield {
            "type": "agent_status",
            "data": {
                "active_agent": AGENTS["OS_EXECUTOR"].role,
                "status": "Opening YouTube in the foreground...",
                "loop_count": 0,
            },
        }

        from ...tools.desktop.advanced.browser_tools import search_youtube

        try:
            raw_result = search_youtube(direct_youtube_query)
        except Exception as exc:
            logger.exception("[DIRECT_YOUTUBE] Foreground playback failed")
            raw_result = f"ERROR: YouTube playback failed unexpectedly: {exc}"

        safe_result = sanitizer.sanitize_tool_output("search_youtube", raw_result)
        context_history.append({
            "role": "tool_call",
            "name": "search_youtube",
            "args": {"query": direct_youtube_query},
        })
        context_history.append({
            "role": "function",
            "name": "search_youtube",
            "content": str(safe_result),
        })

        if str(safe_result).startswith("SUCCESS"):
            final_text = _style_msg(
                _YT_FG_SUCCESS, conversation_style, query=direct_youtube_query
            )
        elif str(safe_result).startswith(("PARTIAL", "INFO")):
            final_text = _style_msg(
                _YT_FG_PARTIAL, conversation_style,
                query=direct_youtube_query, result=safe_result,
            )
        else:
            final_text = _style_msg(
                _YT_FG_FAILED, conversation_style,
                query=direct_youtube_query, result=safe_result,
            )

        context_history.append({"role": "assistant", "content": final_text})
        await _log_fast_path(
            session_id,
            text,
            "foreground_youtube",
            tool_name="search_youtube",
            error=None if str(safe_result).startswith("SUCCESS") else str(safe_result).split(":", 1)[0],
        )
        yield final_text
        return
    if direct_app_action:
        func_name, app_name = direct_app_action
        logger.info(f"Direct app action matched: {func_name}({app_name!r})")

        yield {
            "type": "agent_status",
            "data": {
                "active_agent": AGENTS["OS_EXECUTOR"].role,
                "status": "Executing local app action...",
                "loop_count": 0,
            },
        }

        tool_args = (
            {"excluded_apps": app_name}
            if func_name == "close_apps_except"
            else {"app_name": app_name}
        )

        # Decide whether this action needs explicit user approval before running.
        # close_apps_except is always broad/dangerous. open_app is gated only when
        # the target isn't a recognized app — this is where STT noise like
        # "please open oneself" would otherwise launch a random Windows Search hit.
        needs_approval = func_name == "close_apps_except"
        # tool-content (audit trail) vs assistant-facing (spoken) denial text.
        denial_content = "Permission denied: broad app close was not approved."
        denial_text = _style_msg(
            _SYSTEM_COPY["app_close_denied"], conversation_style
        )
        if func_name == "open_app":
            from ...tools.desktop.apps import (
                _best_registry_match,
                _normalize_app_query,
            )

            if _best_registry_match(_normalize_app_query(app_name)) is None:
                needs_approval = True
                denial_content = f"Permission denied: unrecognized app '{app_name}'."
                denial_text = _style_msg(
                    _SYSTEM_COPY["unknown_app_denied"],
                    conversation_style,
                    app_name=app_name,
                )

        if needs_approval:
            req = tool_planner.queue_tool(func_name, tool_args, risk_level="danger")
            yield {"type": "tool_call_request", "data": req}
            try:
                approved = await asyncio.wait_for(
                    tool_planner.wait_for_approval(req["request_id"]),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                approved = False
                logger.warning("[DIRECT_APP] Approval timeout for %s", func_name)
            if not approved:
                context_history.append(
                    {"role": "tool_call", "name": func_name, "args": tool_args}
                )
                context_history.append(
                    {"role": "function", "name": func_name, "content": denial_content}
                )
                context_history.append({"role": "assistant", "content": denial_text})
                await _log_fast_path(
                    session_id,
                    text,
                    "direct_app",
                    tool_name=func_name,
                    error="APPROVAL_DENIED",
                )
                yield denial_text
                return

        if func_name == "close_apps_except":
            from ...tools.desktop.apps import close_apps_except as app_func
        elif func_name == "close_app":
            _SONG_NAMES = {
                # English
                "song", "songta", "song ti", "songti", "songe", "music", "miusic", "audio",
                "sound", "media", "playback", "melody", "tune",
                # Bangla
                "গান", "গানটা", "গানটি", "সুর", "সঙ্গীত", "গীত", "গীতা",
                "বাদ্য", "বাজনা", "আওয়াজ", "শব্দ",
                # Banglish
                "gaan", "gan", "gaanta", "sur", "sor", "songeet", "sangeet", "geet", "bajna",
                "awaj", "awaz", "shobdo",
            }
            if app_name and any(w in _SONG_NAMES for w in app_name.lower().split()):
                from ...tools.desktop.advanced.youtube_player import stop_youtube_background

                raw_result = stop_youtube_background()
                safe_result = sanitizer.sanitize_tool_output("stop_youtube_background", raw_result)
                logger.info(f"[DIRECT_OS] stop_youtube_background result: {str(safe_result)[:200]}")

                context_history.append({"role": "tool_call", "name": "stop_youtube_background", "args": {}})
                context_history.append({"role": "function", "name": "stop_youtube_background", "content": str(safe_result)})

                if str(safe_result).startswith("SUCCESS"):
                    final_text = _style_msg(_SYSTEM_COPY["music_stopped"], conversation_style)
                else:
                    final_text = _style_msg(_SYSTEM_COPY["music_stop_failed"], conversation_style, detail=raw_result)

                context_history.append({"role": "assistant", "content": final_text})
                yield final_text
                return

            from ...tools.desktop.apps import close_app as app_func
        elif func_name == "close_active_window":
            from ...tools.desktop.apps import close_active_window as active_close

            app_func = lambda _app_name: active_close()
        elif func_name == "focus_app":
            from ...tools.desktop.apps import focus_app as app_func
        else:
            from ...tools.desktop.apps import open_app as app_func

        started_at = asyncio.get_running_loop().time()
        try:
            raw_result = app_func(app_name)
        except Exception as exc:
            logger.exception(
                "[DIRECT_APP] Tool '%s' raised unexpectedly",
                func_name,
            )
            raw_result = f"ERROR: App action failed unexpectedly: {exc}"
        safe_result = sanitizer.sanitize_tool_output(func_name, raw_result)
        logger.info(f"[DIRECT_OS] Tool '{func_name}' result: {str(safe_result)[:200]}")

        context_history.append({
            "role": "tool_call",
            "name": func_name,
            "args": tool_args,
        })
        context_history.append({
            "role": "function",
            "name": func_name,
            "content": str(safe_result),
        })

        final_text = _format_direct_app_response(
            func_name, app_name, str(safe_result), conversation_style
        )
        if str(safe_result).startswith("SUCCESS"):
            if func_name in {"open_app", "focus_app"}:
                _remember_direct_app(session_id, app_name)
            elif (
                func_name == "close_app"
                and _LAST_DIRECT_APP_BY_SESSION.get(session_id) == app_name
            ):
                _remember_direct_app(session_id, None)
        context_history.append({"role": "assistant", "content": final_text})
        result_text = str(safe_result).lstrip()
        result_status = result_text.split(":", 1)[0].upper()
        error_status = (
            None
            if result_status in {"SUCCESS", "OK"}
            else result_status[:40] or "UNKNOWN_FAILURE"
        )
        elapsed_ms = int(
            (asyncio.get_running_loop().time() - started_at) * 1000
        )
        await _log_fast_path(
            session_id,
            text,
            "direct_app",
            tool_name=func_name,
            error=error_status,
            latency_ms=elapsed_ms,
        )
        yield final_text
        return

    # ── WhatsApp explicit UI-send fast path detection ─────────────────────────
    # If the user says "WhatsApp open kore X find kore ... send koro", we want
    # the OS_EXECUTOR to drive the real WhatsApp Desktop app via
    # whatsapp_ui_send_message rather than the background Baileys service.
    whatsapp_ui_intent = (
        cleaned_agents == ["OS_EXECUTOR"]
        and not image_base64
        and is_whatsapp_ui_intent(text)
    )

    # ── Deterministic zero-LLM controls (volume / brightness / mute / clipboard) ──
    # Same idea as the direct app path: skip the whole LLM loop for simple laptop
    # controls — instant, free, more reliable.
    direct_os_action = (
        direct_os_candidate
        if cleaned_agents == ["OS_EXECUTOR"] and not image_base64 and not whatsapp_ui_intent
        else None
    )
    # The zero-LLM OS fast path must respect PERM_SYSTEM just like the LLM tool
    # filter does. If the user disabled system controls, force the request onto
    # the LLM path (where the tools themselves are filtered out anyway).
    if direct_os_action and not _is_pref_true("PERM_SYSTEM"):
        direct_os_action = None
    if direct_os_action:
        func_name, kwargs, control_type, display_msg = direct_os_action
        logger.info(f"Direct OS action matched: {func_name}({kwargs})")

        yield {
            "type": "agent_status",
            "data": {
                "active_agent": AGENTS["OS_EXECUTOR"].role,
                "status": "Executing local control...",
                "loop_count": 0,
            },
        }

        is_danger = _tool_call_requires_approval(func_name, kwargs)
        if is_danger:
            req = tool_planner.queue_tool(func_name, kwargs, risk_level="danger")
            yield {"type": "tool_call_request", "data": req}
            try:
                approved = await asyncio.wait_for(
                    tool_planner.wait_for_approval(req["request_id"]),
                    timeout=300.0,
                )
            except asyncio.TimeoutError:
                approved = False
                logger.warning(
                    "[DIRECT_OS] Approval timeout for %s(%s). Auto-denying.",
                    func_name,
                    kwargs,
                )
            if not approved:
                denial = "Permission denied: user did not approve this power action."
                context_history.append({"role": "tool_call", "name": func_name, "args": kwargs})
                context_history.append({"role": "function", "name": func_name, "content": denial})
                final_text = _style_msg(_SYSTEM_COPY["power_denied"], conversation_style)
                context_history.append({"role": "assistant", "content": final_text})
                yield final_text
                return

        os_func = None
        if func_name == "change_volume":
            from ...tools.desktop.advanced.system_tools import change_volume as os_func
        elif func_name == "read_clipboard":
            from ...tools.desktop.advanced.system_tools import read_clipboard as os_func
        elif func_name == "control_brightness":
            from ...tools.desktop.shortcuts import control_brightness as os_func
        elif func_name == "perform_shortcut":
            from ...tools.desktop.shortcuts import perform_shortcut as os_func
        elif func_name == "pc":
            from ...tools.unified import pc as os_func

        if os_func is not None:
            try:
                raw_result = os_func(**kwargs)
            except Exception as exc:
                raw_result = f"ERROR: {exc}"
            safe_result = sanitizer.sanitize_tool_output(func_name, raw_result)
            logger.info(f"[DIRECT_OS] Tool '{func_name}' result: {str(safe_result)[:200]}")

            context_history.append({"role": "tool_call", "name": func_name, "args": kwargs})
            context_history.append({"role": "function", "name": func_name, "content": str(safe_result)})

            _remember_os_control(session_id, control_type)
            final_text = _format_direct_os_response(
                func_name,
                str(safe_result),
                display_msg,
                conversation_style,
                kwargs,
            )
            context_history.append({"role": "assistant", "content": final_text})
            await _log_fast_path(session_id, text, "direct_os", tool_name=func_name)
            yield final_text
            return

    total_agents = len(cleaned_agents)

    # ── 2. Sequential execution phase ────────────────────────────────────────
    all_tools = get_maya_tools()
    mcp_tools = []
    try:
        from ...tools.mcp_service import MAX_GEMINI_TOOLS, mcp_service

        # Fetch once per workflow. Native relevance routing below reduces the
        # active schema set first; MCP schemas then consume the remaining budget.
        mcp_tools = await mcp_service.get_available_tools(limit=MAX_GEMINI_TOOLS)
    except Exception as exc:
        logger.warning("[AgentTeam] MCP discovery unavailable: %s", exc)
    # MCP tools are external capabilities. Their schemas do not provide a
    # trustworthy risk contract, so every discovered MCP call needs an explicit
    # approval bound to its exact server, tool, and arguments.
    mcp_tool_names = {
        name
        for tool in mcp_tools
        for name in _declared_tool_names(tool)
    }

    previous_agent_results: list[str] = []  # Carries results between agents
    # Send-flow tracking for the pending-send continuation memory (see below):
    # did any tool actually execute a send this request, and did any tool at
    # least progress a send flow (contact lookup/save)?
    send_executed = False
    send_flow_touched = False
    executed_delivery_fingerprints: set[str] = set()
    # Render the clock once per request; every round reuses it so the system
    # prefix stays byte-identical and Gemini's implicit caching can hit.
    request_time_block = _render_time_block()

    for agent_idx, agent_name in enumerate(cleaned_agents):
        is_last_agent = (agent_idx == len(cleaned_agents) - 1)
        agent_config = AGENTS[agent_name]
        logger.info(f"Activating agent: {agent_config.name}")

        # Get tone/mode from StateManager
        from ...system.state_manager import state_manager
        ctx_prompt_info = state_manager.get_prompt_context()
        active_tone = ctx_prompt_info.get("tone", "")
        active_mode = ctx_prompt_info.get("mode_name", "professional")

        # Fetch dynamic tool names to ensure they aren't filtered out
        from ...skills.skill_watcher import get_dynamic_tools
        dynamic_tool_names = {t.__name__ for t in get_dynamic_tools() if hasattr(t, "__name__")}

        # Filter tools for this specific agent (allow dynamic skills for all active agents)
        override_tools = [
            t for t in all_tools
            if hasattr(t, "__name__") and (
                t.__name__ in agent_config.tool_names or
                t.__name__ in dynamic_tool_names
            )
        ]

        # MCP APIs belong to OS_EXECUTOR. Merge them into the candidate set BEFORE
        # relevance routing so they are scored against the user request alongside
        # native tools, preventing irrelevant MCP tools (like memory graph) from
        # polluting the active tool set on unrelated turns.
        if agent_name == "OS_EXECUTOR" and mcp_tools:
            from ...tools.mcp_service import TOOL_SAFETY_BUFFER

            before_mcp = len(override_tools)
            override_tools = _merge_mcp_tool_schemas(
                override_tools,
                mcp_tools,
                max_total=MAX_GEMINI_TOOLS - TOOL_SAFETY_BUFFER,
            )
            logger.info(
                "[AgentTeam] Merged %d MCP tool schema(s) into OS_EXECUTOR candidate set.",
                len(override_tools) - before_mcp,
            )

        # ── Dynamic tool routing ──────────────────────────────────────────────
        # Large tool sets (OS_EXECUTOR ~55 native + MCP) are re-sent as function-call
        # schemas on every tool-round. Rank them down to the tools relevant to THIS
        # request via cached embeddings: big token savings + fewer mis-fired
        # calls. Done once per agent activation so the tool set stays stable
        # across rounds. Lean agents (CHAT/CODER/RESEARCHER) fall under the gate
        # and pass through untouched. select_relevant_tools never raises and
        # never empties the set (falls back to all candidates on any weak signal).
        if len(override_tools) > ROUTER_SIZE_GATE:
            _before = len(override_tools)
            _router_query = _tool_router_query(text, context_history)
            if execution_brief:
                # Complex goals often need tools implied by later planned steps,
                # not just words present in the original request. Include the
                # bounded plan so relevance routing keeps those tools available.
                _router_query = f"{_router_query}\n{execution_brief}"
            override_tools = select_relevant_tools(_router_query, override_tools)
            logger.info(
                f"[ToolRouter] {agent_config.name}: {_before} -> "
                f"{len(override_tools)} tools for: {_router_query[:60]!r}"
            )

        # If the user explicitly asked for the WhatsApp Desktop UI flow, make
        # sure the dedicated UI tool is available even after aggressive routing.
        if whatsapp_ui_intent:
            _has_ui_tool = any(
                hasattr(t, "__name__") and t.__name__ == "whatsapp_ui_send_message"
                for t in override_tools
            )
            if not _has_ui_tool:
                _ui_tool = next(
                    (t for t in all_tools if hasattr(t, "__name__") and t.__name__ == "whatsapp_ui_send_message"),
                    None,
                )
                if _ui_tool is not None:
                    override_tools.append(_ui_tool)
            # Remind the agent it MUST use the UI tool, not background send.
            context_history.append({
                "role": "user",
                "content": "USER WANTS THE WHATSAPP DESKTOP UI FLOW. Use whatsapp_ui_send_message(contact_name, message). Do NOT use whatsapp_send_message."
            })

        # Per-agent tool execution history (tool_call + function pairs)
        # This stays local to each agent's execution loop
        agent_tool_history: list[dict] = []

        # Tracks the most recent screenshot captured by a tool (e.g. take_verified_screenshot)
        # This gets injected as a real Vision image into the next Gemini call
        current_agent_screenshot: str = None

        # Complex planned work gets more room than a simple one-shot command,
        # while hard caps in execution_policy prevent runaway loops.
        max_tool_rounds = adaptive_tool_round_limit(
            agent_name,
            analysis_result.complexity_score,
            execution_graph,
        )
        tool_round = 0
        agent_final_text = ""
        tool_completion_required = requires_tool_completion(
            agent_name,
            text,
            has_image=bool(image_base64),
        )
        completion_audit_used = False
        completion_retry_prompt: str | None = None

        yield {
            "type": "agent_status",
            "data": {
                "active_agent": agent_config.role,
                "status": "Starting task...",
                "loop_count": 0
            }
        }

        needs_final_summary = False
        saved_action_text = ""
        defer_text_was_yielded = False

        while tool_round <= max_tool_rounds:
                # Build context fresh each round (includes latest tool results)
            agent_context = _build_agent_context(
                agent_config=agent_config,
                base_history=context_history,
                previous_results=previous_agent_results,
                original_task=text,
                active_mode=active_mode,
                active_tone=active_tone,
                time_block=request_time_block,
                conversation_style=conversation_style,
                execution_brief=execution_brief,
            )

            # Append local tool history for this agent
            # (tool_call + function pairs from previous rounds in this agent)
            agent_context.extend(agent_tool_history)

            # After tool execution rounds, Gemini requires a user turn after
            # the function response — append a continue signal so turn order is valid
            if tool_round > 0 and agent_tool_history:
                agent_context.append({
                    "role": "user",
                    "content": "Continue with the task using the tool results above."
                })

            yield {
                "type": "agent_status",
                "data": {
                    "active_agent": agent_config.role,
                    "status": f"Thinking... (round {tool_round + 1})",
                    "loop_count": tool_round
                }
            }

            tool_calls_this_round: list[dict] = []
            text_this_round = ""

            # First round sends the original task. A one-shot completion audit
            # can replace it when an action agent tried to finish without using
            # any tool (which means no real action happened).
            if completion_retry_prompt:
                user_prompt = completion_retry_prompt
                completion_retry_prompt = None
            else:
                user_prompt = text if tool_round == 0 else None
            defer_action_text = (
                is_last_agent
                and tool_completion_required
                and not agent_tool_history
            )
            # Vision context: round 0 uses the original user-provided image (if any).
            # Subsequent rounds use any screenshot that was captured by a tool this round.
            if tool_round == 0:
                image_b64 = image_base64
            elif current_agent_screenshot:
                image_b64 = current_agent_screenshot
                current_agent_screenshot = None  # consume it; reset for next round
            else:
                image_b64 = None

            async for chunk in gemini_adapter.generate_stream(
                agent_context,
                user_prompt,
                image_b64,
                override_tools=override_tools,
                model_tier=active_tier
            ):
                if isinstance(chunk, dict):
                    if chunk.get("type") == "tool_call":
                        tool_calls_this_round.append(chunk)
                    # Always pass through status/reasoning events
                    else:
                        yield chunk
                else:
                    text_this_round += chunk
                    # Buffer model text until the response style is validated.
                    # This trades a small amount of first-token latency for a
                    # strict production guarantee that the user never receives
                    # a reply in the wrong language style.

            if defer_action_text and text_this_round.strip():
                saved_action_text = text_this_round.strip()

            # ── No tool calls → agent is done ────────────────────────────
            if not tool_calls_this_round:
                if (
                    tool_completion_required
                    and not agent_tool_history
                    and override_tools
                    and not completion_audit_used
                ):
                    completion_audit_used = True
                    completion_retry_prompt = completion_audit_prompt(text)
                    logger.info(
                        "[%s] Tool-free premature completion detected; running one execution audit.",
                        agent_config.name,
                    )
                    yield {
                        "type": "agent_status",
                        "data": {
                            "active_agent": agent_config.role,
                            "status": "Checking execution completeness...",
                            "loop_count": tool_round,
                        },
                    }
                    continue

                # The first action response is buffered until we know whether
                # it actually called a tool. If the audit still cannot execute,
                # surface its precise blocker instead of swallowing the reply.
                candidate_text = saved_action_text or text_this_round.strip()
                if candidate_text:
                    if is_last_agent and not response_matches_style(
                        candidate_text, conversation_style
                    ):
                        try:
                            repaired = await gemini_adapter.generate_response(
                                [],
                                style_repair_prompt(candidate_text, conversation_style),
                                override_tools=[],
                                model_tier="fast",
                            )
                            repaired = str(repaired).strip()
                            if repaired and response_matches_style(
                                repaired, conversation_style
                            ):
                                candidate_text = repaired
                        except Exception as exc:
                            logger.warning("Language style repair failed: %s", exc)
                    agent_final_text = candidate_text
                    previous_agent_results.append(agent_final_text)
                    if is_last_agent:
                        yield agent_final_text
                        defer_text_was_yielded = True
                    saved_action_text = ""
                elif tool_round > 0:
                    # Agent used tools but gave no final text — collect tool outputs as result
                    # and surface a user-visible confirmation so the Telegram bot does not
                    # fall back to its generic "✅ Kaj hoye geche." default message.
                    tool_outputs = [
                        m["content"] for m in agent_tool_history
                        if m.get("role") == "function"
                    ]
                    if tool_outputs:
                        summary = f"[{agent_config.name} completed actions. Results: " + "; ".join(tool_outputs[-3:]) + "]"
                        previous_agent_results.append(summary)
                        # Build a concise user-facing confirmation from the LAST tool result.
                        last_output = tool_outputs[-1].strip()
                        import os as _os
                        # Detect failure patterns first
                        is_failure = (
                            last_output.startswith("ERR:")
                            or last_output.startswith("ERROR")
                            or last_output.startswith("Failed after")
                            or last_output.startswith("Permission denied")
                        )
                        if is_failure:
                            # Always show error, even if LLM already said something
                            if last_output.startswith("Failed after"):
                                # "Failed after 3 attempt(s). Last error: ..."
                                err_detail = last_output.split("Last error:", 1)[-1].strip() if "Last error:" in last_output else last_output
                                visible_confirmation = f"❌ Canvas update hoyeni. Error: {err_detail}"
                            else:
                                visible_confirmation = f"❌ Kaj hoyeni: {last_output}"
                            agent_final_text = visible_confirmation
                            previous_agent_results.append(visible_confirmation)
                            yield visible_confirmation
                        elif not defer_text_was_yielded:
                            # Only emit success confirmation if we haven't already shown text
                            if last_output.startswith("OK:"):
                                path_part = last_output[3:].strip()
                                fname = _os.path.basename(path_part) if path_part else ""
                                if fname:
                                    visible_confirmation = f"✅ '{fname}' create kore dilam.\n📁 Path: {path_part}"
                                else:
                                    visible_confirmation = f"✅ Kaj sesh hoyeche.\n{last_output}"
                            elif last_output.lower().startswith("found "):
                                visible_confirmation = f"🔍 File khuje pelam:\n{last_output}"
                            elif last_output.lower().startswith("not found"):
                                visible_confirmation = f"❌ File ta khuje pelam na. {last_output}"
                            elif last_output.startswith("SUCCESS"):
                                if "Canvas updated" in last_output:
                                    visible_confirmation = _style_msg(_SYSTEM_COPY["canvas_updated"], conversation_style)
                                else:
                                    clean_msg = last_output.replace("SUCCESS:", "").strip()
                                    visible_confirmation = _style_msg(_SYSTEM_COPY["generic_success"], conversation_style, clean_msg=clean_msg)
                            else:
                                visible_confirmation = f"✅ Kaj sesh.\n{last_output[:400]}"
                            agent_final_text = visible_confirmation
                            previous_agent_results.append(visible_confirmation)
                            yield visible_confirmation
                        # else: defer_text_was_yielded=True and no failure → LLM already said the right thing, stay silent
                break

            # ── Process tool calls ────────────────────────────────────────
            yield {
                "type": "agent_status",
                "data": {
                    "active_agent": agent_config.role,
                    "status": f"Executing {len(tool_calls_this_round)} action(s)...",
                    "loop_count": tool_round
                }
            }

            for tc in tool_calls_this_round:
                func_name = tc["name"]
                args = tc.get("args", {})
                delivery_key = _delivery_fingerprint(func_name, args) if func_name in _SEND_EXECUTING_TOOLS else None
                duplicate_delivery = bool(
                    delivery_key and delivery_key in executed_delivery_fingerprints
                )
                if delivery_key and not duplicate_delivery:
                    # A remote acceptance can be lost to a timeout. Do not let a
                    # later model round turn that ambiguity into a second send.
                    executed_delivery_fingerprints.add(delivery_key)

                # ── Safety approval for danger tools ─────────────────
                is_danger = _tool_call_requires_approval(
                    func_name,
                    args,
                    mcp_tool_names,
                )
                approved = not duplicate_delivery
                if is_danger and not duplicate_delivery:
                    from ...database.connection import SessionLocal
                    from ...database.models import UserPreferences
                    from ...database.crypto import crypto_manager

                    db_session = SessionLocal()
                    auto_approve = False
                    try:
                        pref = db_session.query(UserPreferences).filter(
                            UserPreferences.key == "PERM_AUTO_APPROVE"
                        ).first()
                        if pref and pref.value:
                            try:
                                auto_approve = (crypto_manager.decrypt(pref.value, raise_on_failure=True) == "true")
                            except Exception:
                                pass
                    finally:
                        db_session.close()

                    req = tool_planner.queue_tool(func_name, args, risk_level="danger")

                    # Auto-approve is a convenience for reversible actions, never
                    # a bypass for destructive or power-control operations.
                    auto_approve_allowed = req.get("risk_level") not in {"HIGH", "CRITICAL"}
                    if auto_approve and auto_approve_allowed:
                        req_copy = dict(req)
                        req_copy["status"] = "executed"
                        yield {"type": "tool_call_request", "data": req_copy}
                        tool_planner.resolve_tool(req["request_id"], approved=True)
                    else:
                        yield {"type": "tool_call_request", "data": req}
                        try:
                            approved = await asyncio.wait_for(
                                tool_planner.wait_for_approval(req["request_id"]),
                                timeout=300.0  # 5 minutes for user to approve
                            )
                        except asyncio.TimeoutError:
                            approved = False
                            logger.warning(f"[agent_team] Approval timeout for {func_name}. Auto-denying.")

                # ── Execute tool ──────────────────────────────────────
                tool_result_verified = False
                if approved:
                    from ...tools.manifest import get_manifest
                    from ...tools.verifier import ResultVerifier, VerifyResult

                    manifest = get_manifest(func_name)
                    # A send with an ambiguous result must not be executed
                    # again automatically; the transport owns safe retries.
                    max_attempts = 1 if func_name in _SEND_EXECUTING_TOOLS else 3
                    failure_history: list[FailureRecord] = []
                    current_tool_name = func_name
                    current_args = args
                    raw_result = None
                    # Initialize verify_result so it's always defined after the loop,
                    # even if max_attempts is ever set to 0 (defensive programming).
                    verify_result = VerifyResult(valid=True)

                    for attempt in range(max_attempts):
                        raw_result = await _run_tool(current_tool_name, current_args, all_tools, conversation_style)
                        verify_result = await ResultVerifier.verify(current_tool_name, raw_result, manifest)

                        if verify_result.valid:
                            break

                        logger.warning(f"Tool {current_tool_name} failed verification (attempt {attempt+1}): {verify_result.reason}")
                        failure_history.append(FailureRecord(
                            attempt=attempt + 1,
                            tool=current_tool_name,
                            args=current_args,
                            error=verify_result.reason
                        ))

                        if not verify_result.retryable:
                            logger.warning(
                                "Tool %s returned a non-retryable failure; preserving the original result.",
                                current_tool_name,
                            )
                            break

                        if attempt < max_attempts - 1:
                            # An approval is bound to the EXACT tool + args the
                            # user saw. A danger tool may retry with identical
                            # args only — replanned args or a fallback tool
                            # would execute something the user never approved
                            # (R06 audit, BUG-022).
                            if is_danger:
                                continue
                            if attempt == 0:
                                # Stage 2: same tool, mini-LLM re-plans args with failure context
                                replan_prompt = (
                                    f"Tool '{current_tool_name}' failed with error: {verify_result.reason}. "
                                    f"Current args: {current_args}. Provide corrected args as JSON."
                                )
                                try:
                                    replan_response = await gemini_adapter.generate_response(agent_context, replan_prompt)
                                    # re is already imported at module top
                                    json_match = re.search(r"```json(.*?)```", replan_response, re.DOTALL)
                                    if json_match:
                                        current_args = json.loads(json_match.group(1).strip())
                                except Exception:
                                    pass  # keep original args if replan fails
                            elif attempt == 1 and manifest.fallback_tool:
                                # Stage 3: switch to fallback tool
                                current_tool_name = manifest.fallback_tool
                                current_args = manifest.adapt_args_for_fallback(failure_history[-1].args)
                                manifest = get_manifest(current_tool_name)

                    if not verify_result.valid and verify_result.retryable:
                        attempts_used = len(failure_history)
                        if func_name in _SEND_EXECUTING_TOOLS:
                            raw_result = (
                                "ERROR: Delivery was not completed. "
                                f"Last error: {verify_result.reason}"
                            )
                        else:
                            raw_result = (
                                f"Failed after {attempts_used} attempt(s). "
                                f"Last error: {verify_result.reason}"
                            )
                    tool_result_verified = verify_result.valid
                elif duplicate_delivery:
                    raw_result = (
                        "ERROR: Duplicate delivery request blocked. "
                        "The earlier delivery result in this request is authoritative."
                    )
                else:
                    raw_result = "Permission denied by user."

                # ── Vision context extraction ─────────────────────────
                # If the tool returned a screenshot (base64), extract it and store
                # so the next Gemini reasoning round receives it as a real image.
                _VISION_PREFIXES = {
                    "SCREENSHOT_BASE64:": "[Screenshot captured. Gemini Vision will analyze it in the next reasoning step.]",
                    "CAMERA_PREVIEW_BASE64:": "[Live Camera preview captured. Inspect the real visible person/outfit in the next reasoning step; do not guess beyond the image.]",
                }
                if isinstance(raw_result, str):
                    for prefix, notice in _VISION_PREFIXES.items():
                        if raw_result.startswith(prefix):
                            current_agent_screenshot = raw_result[len(prefix):]
                            raw_result = notice
                            break

                # ── Mode Change Detection ─────────────────────────────────────
                # If the tool returned MODE_CHANGE_TRIGGERED, apply the mode
                # change immediately so the session is cleared and the next
                # agent round (and any subsequent agent) uses the new personality.
                if isinstance(raw_result, str) and "MODE_CHANGE_TRIGGERED:" in raw_result:
                    new_mode = raw_result.split("MODE_CHANGE_TRIGGERED:")[1].strip().split()[0]
                    try:
                        import asyncio as _asyncio
                        _asyncio.create_task(state_manager.change_mode(new_mode))
                    except Exception as _me:
                        logger.warning(f"[agent_team] Inline mode change failed: {_me}")

                # ── System State Detection ────────────────────────────────────
                # If the tool returned SYSTEM_STATE_TRIGGERED, yield it as a
                # text chunk so that both the websocket handler AND the Telegram
                # _process_and_reply can catch it in full_response.
                # Without this, it stays as a tool result the AI sees internally
                # and never surfaces in the streamed text output.
                if isinstance(raw_result, str) and "SYSTEM_STATE_TRIGGERED:" in raw_result:
                    yield raw_result  # surfaces to telegram + websocket handlers
                # ─────────────────────────────────────────────────────────────

                # ── Send-flow tracking ───────────────────────────────────────
                # Feeds the pending-send continuation memory: a send counts as
                # executed only if the send tool actually ran (not denied).
                if func_name in _SEND_FLOW_TOOLS:
                    send_flow_touched = True
                    if tool_result_verified and func_name in _SEND_EXECUTING_TOOLS:
                        send_executed = True

                # ── Clarification short-circuit ──────────────────────────────
                # When a tool needs the user to pick from a list (e.g. multiple
                # WhatsApp contacts matched), relay the list to the user
                # verbatim instead of trusting the LLM to repeat it — weak
                # fallback models paraphrase or drop the list entirely.
                if isinstance(raw_result, str) and raw_result.startswith("CLARIFICATION_NEEDED:"):
                    clarify_text = _format_clarification(
                        raw_result[len("CLARIFICATION_NEEDED:"):].strip(),
                        text,
                        conversation_style,
                    )
                    logger.info(f"[{agent_config.name}] Clarification needed — relaying list to user directly.")
                    # The user's answer ("2", "prothom ta") has no routable
                    # keywords — remember the paused flow so it sticks to
                    # OS_EXECUTOR instead of collapsing to CHAT.
                    _remember_pending_send(session_id)
                    yield f"\n{clarify_text}"
                    previous_agent_results.append(clarify_text)
                    combined = "\n\n".join(r for r in previous_agent_results if r)
                    context_history.append({"role": "assistant", "content": combined})
                    return

                # Sanitize and truncate
                safe_result = sanitizer.sanitize_tool_output(func_name, raw_result)
                if len(str(safe_result)) > MAX_TOOL_OUTPUT_CHARS:
                    safe_result = str(safe_result)[:MAX_TOOL_OUTPUT_CHARS] + "\n... [output truncated]"

                logger.info(f"[{agent_config.name}] Tool '{func_name}' result: {str(safe_result)[:200]}")

                # Append tool_call + function to agent's local history
                # so the next generation round sees the result
                agent_tool_history.append({
                    "role": "tool_call",
                    "name": func_name,
                    "args": args,
                    "thought_signature": tc.get("thought_signature")
                })
                agent_tool_history.append({
                    "role": "function",
                    "name": func_name,
                    "content": str(safe_result)
                })

                # Also record in shared context for memory continuity
                context_history.append({
                    "role": "tool_call",
                    "name": func_name,
                    "args": args,
                    "thought_signature": tc.get("thought_signature")
                })
                context_history.append({
                    "role": "function",
                    "name": func_name,
                    "content": str(safe_result)
                })

                if func_name in _SEND_EXECUTING_TOOLS:
                    # Delivery language comes directly from the observed tool
                    # result. Do not give a fallback model an opportunity to
                    # invent a success or omit an accepted send.
                    delivery_reply = str(safe_result)
                    if not tool_result_verified:
                        _remember_pending_send(session_id)
                    yield f"\n{delivery_reply}"
                    previous_agent_results.append(delivery_reply)
                    context_history.append({"role": "assistant", "content": delivery_reply})
                    return

            tool_round += 1
            if tool_round > max_tool_rounds:
                logger.warning(f"[{agent_config.name}] Max tool rounds reached. Requesting final summary.")
                needs_final_summary = True
                break

        if needs_final_summary:
            final_summary = await _summarize_completed_actions(
                agent_config.name, agent_context, agent_tool_history, text
            )
            if final_summary:
                yield f"\n{final_summary}"
                previous_agent_results.append(final_summary)

    # ── Pending-send continuation memory ─────────────────────────────────────
    # A send-intent turn (or the continuation of one) ran through OS_EXECUTOR
    # but nothing was actually sent — Maya is mid-flow, asking the user for the
    # missing piece (contact number / message text). Remember it so the user's
    # NEXT reply routes back to OS_EXECUTOR with its messaging tools, instead
    # of stranding on CHAT ("আমার টুল লিস্টে WhatsApp নেই" bug). Re-armed from a
    # consumed flag only while the flow is demonstrably alive (a send-flow tool
    # was touched this turn), so an abandoned flow can't pin routing forever.
    if (
        "OS_EXECUTOR" in cleaned_agents
        and not send_executed
        and (_SEND_INTENT_RE.search(text) or (pending_send and send_flow_touched))
    ):
        _remember_pending_send(session_id)

    # ── 3. Persist final assistant message ───────────────────────────────────
    if previous_agent_results:
        combined = "\n\n".join(r for r in previous_agent_results if r)
        context_history.append({"role": "assistant", "content": combined})
