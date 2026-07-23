"""Rolling conversation context compaction for Maya sessions.

The primary system prompt is always preserved. Older complete turns are rolled
into one summary while recent turns, including their tool calls and results,
remain verbatim.
"""

import json
import logging
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

VERBATIM_TURNS = 8
CONDENSE_THRESHOLD = 12
SUMMARY_MARKER = "[Conversation Summary - earlier turns condensed to save context space]"
SUMMARY_FLAG = "_maya_context_summary"


class ContextCondenser:
    """Maintain one rolling summary for a conversation session."""

    def __init__(self):
        self._summary_text = ""

    @staticmethod
    def _is_summary(message: Dict[str, Any]) -> bool:
        content = str(message.get("content", ""))
        return bool(
            message.get(SUMMARY_FLAG)
            or content.startswith("[Conversation Summary")
        )

    @staticmethod
    def _count_user_turns(history: List[Dict[str, Any]]) -> int:
        return sum(1 for message in history if message.get("role") == "user")

    def needs_condensing(self, history: List[Dict[str, Any]]) -> bool:
        return self._count_user_turns(history) > CONDENSE_THRESHOLD

    async def condense(
        self,
        history: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Summarize old complete turns and retain recent turns verbatim."""
        if not history:
            return history

        system_message = history[0] if history[0].get("role") == "system" else None
        rest = list(history[1:] if system_message else history)
        prior_summaries = [message for message in rest if self._is_summary(message)]
        conversation = [message for message in rest if not self._is_summary(message)]

        user_indices = [
            index
            for index, message in enumerate(conversation)
            if message.get("role") == "user"
        ]
        if len(user_indices) <= VERBATIM_TURNS:
            return history

        # Starting at a user message preserves every tool_call/function pair in
        # each retained turn and never leaves an orphaned function response.
        keep_from = user_indices[-VERBATIM_TURNS]
        newly_compressible = conversation[:keep_from]
        retained_messages = conversation[keep_from:]

        # Roll the previous summary forward with newly old turns. It is input to
        # the next summary, never copied beside it, so exactly one block remains.
        summary_input = prior_summaries + newly_compressible
        summary_res = await self._summarize(summary_input)
        if not summary_res:
            logger.warning("[ContextCondenser] Summarization failed; retaining original un-condensed history.")
            return history

        self._summary_text = summary_res
        summary_message = {
            "role": "system",
            "content": f"{SUMMARY_MARKER}\n{self._summary_text}",
            SUMMARY_FLAG: True,
        }

        condensed = []
        if system_message:
            condensed.append(system_message)
        condensed.append(summary_message)
        condensed.extend(retained_messages)

        logger.info(
            "[ContextCondenser] Rolled %d message(s) into summary; kept %d full turn(s).",
            len(newly_compressible),
            VERBATIM_TURNS,
        )
        return condensed

    async def _summarize(self, messages: List[Dict[str, Any]]) -> Optional[str]:
        """Use the fast model tier; return None on failure so history is preserved."""
        try:
            from ..providers.gemini_adapter import gemini_adapter

            transcript_lines = []
            for message in messages:
                role = message.get("role", "")
                if role == "tool_call":
                    args = json.dumps(message.get("args") or {}, ensure_ascii=False)
                    content = f"{message.get('name', 'tool')} args={args}"
                elif role == "function":
                    content = (
                        f"{message.get('name', 'tool')} "
                        f"result={message.get('content', '')}"
                    )
                else:
                    content = str(message.get("content", ""))
                transcript_lines.append(f"{role.upper()}: {content[:500]}")

            transcript = "\n".join(transcript_lines)
            prompt = (
                "Merge this conversation history into a concise rolling summary. "
                "Preserve key user facts, unfinished work, completed actions, "
                "paths, and important tool results. Omit pleasantries, filler, "
                "and intermediate reasoning.\n\n"
                f"{transcript}"
            )
            summary = await gemini_adapter.generate_response(
                [{"role": "user", "content": prompt}],
                prompt,
                override_tools=[],
                model_tier="fast",
            )
            return summary.strip()
        except Exception as exc:
            logger.warning("[ContextCondenser] Summarization failed: %s", exc)
            return None


_condensers: Dict[str, ContextCondenser] = {}


def get_condenser(session_id: str) -> ContextCondenser:
    if session_id not in _condensers:
        _condensers[session_id] = ContextCondenser()
    return _condensers[session_id]


def evict_condenser(session_id: str) -> None:
    _condensers.pop(session_id, None)
