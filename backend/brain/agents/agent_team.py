import logging
import json
import asyncio
from typing import AsyncGenerator, Union
from ..providers.gemini_adapter import gemini_adapter
from .agent_defs import AGENTS, ROUTING_PROMPT
from ..gemini.function_calls import get_maya_tools
from ..reasoning.tool_planner import tool_planner
from ..security_filter import sanitizer

logger = logging.getLogger(__name__)

# Maximum characters for a single tool output to prevent context blowup
MAX_TOOL_OUTPUT_CHARS = 3000

# Tools requiring explicit user approval before execution
DANGER_TOOLS = [
    "execute_python", "execute_powershell", "delete_file",
    "manage_system_state", "manage_processes"
]


def _build_agent_context(
    agent_config,
    base_history: list[dict],
    previous_results: list[str],
    original_task: str,
    active_mode: str,
    active_tone: str,
) -> list[dict]:
    """
    Builds a clean context for a sub-agent.
    - Only user/assistant turns from base_history (no tool_call/function roles)
    - Injects previous agent results as a user context message
    - Appends the original task as the final user turn
    """
    tone_directive = f"\nACTIVE MODE: {active_mode.upper()}\nTONE CONTEXT: {active_tone}"
    if active_mode == "friendly":
        tone_directive += (
            "\nSince active mode is FRIENDLY, you must act as an affectionate companion. "
            "Use cute terms like সোনা, বাবু, জানু, লক্ষ্মীটি. "
            "Address the user sweetly and show deep emotional attachment in your text."
        )
    else:
        tone_directive += (
            "\nDo NOT use affectionate companion terms like 'সোনা', 'বাবু', 'জানু', "
            "or 'লক্ষ্মীটি' in this mode. Keep your conversational language normal, polite, or technical."
        )

    system_instruction = f"{agent_config.system_prompt}\n{tone_directive}"

    # Clean history: only user/assistant roles, last 5 turns
    clean_history = [
        m for m in base_history if m.get("role") in ("user", "assistant")
    ]
    trimmed = clean_history[-5:] if len(clean_history) > 5 else clean_history

    context = [{"role": "system", "content": system_instruction}] + trimmed

    # Inject results from previous agents as context
    if previous_results:
        combined = "\n\n---\n".join(previous_results)
        context.append({
            "role": "user",
            "content": (
                f"[Context from previous agents]\n{combined}\n\n"
                f"[Your task] {original_task}"
            )
        })
    else:
        context.append({"role": "user", "content": original_task})

    return context


async def _run_tool(func_name: str, args: dict, all_tools: list) -> str:
    """Execute a single tool call and return the result as a string."""
    func = next(
        (t for t in all_tools if hasattr(t, "__name__") and t.__name__ == func_name),
        None
    )
    if not func:
        return f"Tool '{func_name}' is disabled or not available."
    try:
        import inspect
        if inspect.iscoroutinefunction(func):
            result = await func(**args)
        else:
            result = func(**args)
        return str(result)
    except Exception as e:
        return f"Tool '{func_name}' raised an error: {e}"


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

    # ── 1. Routing phase ─────────────────────────────────────────────────────
    routing_context = [
        {"role": "system", "content": ROUTING_PROMPT},
        {"role": "user", "content": f"Request: {text}"}
    ]

    routing_response = ""
    try:
        routing_response = await gemini_adapter.generate_response(
            routing_context, f"Request: {text}", override_tools=[]
        )
        logger.info(f"Router response: {routing_response}")

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
        cleaned_agents = ["RESEARCHER", "OS_EXECUTOR"]

    logger.info(f"Target agents scheduled in order: {cleaned_agents}")
    total_agents = len(cleaned_agents)

    # ── 2. Sequential execution phase ────────────────────────────────────────
    all_tools = get_maya_tools()
    previous_agent_results: list[str] = []  # Carries results between agents

    for agent_idx, agent_name in enumerate(cleaned_agents):
        is_last_agent = (agent_idx == len(cleaned_agents) - 1)
        agent_config = AGENTS[agent_name]
        logger.info(f"Activating agent: {agent_config.name}")

        # Get tone/mode from StateManager
        from ...system.state_manager import state_manager
        ctx_prompt_info = state_manager.get_prompt_context()
        active_tone = ctx_prompt_info.get("tone", "")
        active_mode = ctx_prompt_info.get("mode_name", "friendly")

        # Filter tools for this specific agent
        override_tools = [
            t for t in all_tools
            if hasattr(t, "__name__") and t.__name__ in agent_config.tool_names
        ]

        # Per-agent tool execution history (tool_call + function pairs)
        # This stays local to each agent's execution loop
        agent_tool_history: list[dict] = []

        # Tracks the most recent screenshot captured by a tool (e.g. take_verified_screenshot)
        # This gets injected as a real Vision image into the next Gemini call
        current_agent_screenshot: str = None

        # Flags
        max_tool_rounds = 8   # Max rounds of tool use per agent (increased for vision loops)
        tool_round = 0
        agent_final_text = ""

        yield {
            "type": "agent_status",
            "data": {
                "active_agent": agent_config.role,
                "status": "Starting task...",
                "loop_count": 0
            }
        }

        while tool_round <= max_tool_rounds:
            # Build context fresh each round (includes latest tool results)
            agent_context = _build_agent_context(
                agent_config=agent_config,
                base_history=context_history,
                previous_results=previous_agent_results,
                original_task=text,
                active_mode=active_mode,
                active_tone=active_tone,
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

            # First round: send original task as user prompt.
            # Subsequent rounds: context already has tool results + continue message above.
            user_prompt = text if tool_round == 0 else None
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
                override_tools=override_tools
            ):
                if isinstance(chunk, dict):
                    if chunk.get("type") == "tool_call":
                        tool_calls_this_round.append(chunk)
                    # Always pass through status/reasoning events
                    else:
                        yield chunk
                else:
                    text_this_round += chunk
                    # Only stream text to user from the LAST agent
                    # Intermediate agents' text is buffered (used as context for next agent)
                    if is_last_agent:
                        yield chunk

            # ── No tool calls → agent is done ────────────────────────────
            if not tool_calls_this_round:
                if text_this_round.strip():
                    agent_final_text = text_this_round.strip()
                    previous_agent_results.append(agent_final_text)
                elif tool_round > 0:
                    # Agent used tools but gave no final text — collect tool outputs as result
                    tool_outputs = [
                        m["content"] for m in agent_tool_history
                        if m.get("role") == "function"
                    ]
                    if tool_outputs:
                        summary = f"[{agent_config.name} completed actions. Results: " + "; ".join(tool_outputs[-3:]) + "]"
                        previous_agent_results.append(summary)
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

                # ── Safety approval for danger tools ─────────────────
                approved = True
                if func_name in DANGER_TOOLS:
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
                                auto_approve = (crypto_manager.decrypt(pref.value) == "true")
                            except Exception:
                                pass
                    finally:
                        db_session.close()

                    req = tool_planner.queue_tool(func_name, args, risk_level="danger")

                    if auto_approve:
                        req_copy = dict(req)
                        req_copy["status"] = "executed"
                        yield {"type": "tool_call_request", "data": req_copy}
                        tool_planner.resolve_tool(req["request_id"], approved=True)
                    else:
                        yield {"type": "tool_call_request", "data": req}
                        try:
                            approved = await asyncio.wait_for(
                                tool_planner.wait_for_approval(req["request_id"]),
                                timeout=60.0
                            )
                        except asyncio.TimeoutError:
                            approved = False

                # ── Execute tool ──────────────────────────────────────
                if approved:
                    raw_result = await _run_tool(func_name, args, all_tools)
                else:
                    raw_result = "User denied permission."

                # ── Vision context extraction ─────────────────────────
                # If the tool returned a screenshot (base64), extract it and store
                # so the next Gemini reasoning round receives it as a real image.
                _SCREENSHOT_PREFIX = "SCREENSHOT_BASE64:"
                if isinstance(raw_result, str) and raw_result.startswith(_SCREENSHOT_PREFIX):
                    current_agent_screenshot = raw_result[len(_SCREENSHOT_PREFIX):]
                    raw_result = "[Screenshot captured. Gemini Vision will analyze it in the next reasoning step.]"

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

            tool_round += 1
            if tool_round > max_tool_rounds:
                logger.warning(f"[{agent_config.name}] Max tool rounds reached. Stopping.")
                yield f"\n[{agent_config.role}: reached max execution rounds. Task may be partially complete.]"
                break

    # ── 3. Persist final assistant message ───────────────────────────────────
    if previous_agent_results:
        combined = "\n\n".join(r for r in previous_agent_results if r)
        context_history.append({"role": "assistant", "content": combined})
