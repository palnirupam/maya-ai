from dataclasses import dataclass
import re
from typing import Any, Dict
from .manifest import ToolManifest
import logging

logger = logging.getLogger(__name__)

@dataclass
class VerifyResult:
    """Outcome of tool verification.

    ``retryable`` is only relevant when ``valid`` is false: it allows the
    agent loop to re-plan transient or argument-related failures while keeping
    safety, configuration, and capability failures terminal for this call.
    """
    valid: bool
    reason: str = ""
    retryable: bool = False

class ResultVerifier:
    """Verifies tool execution results against schemas and semantic expectations."""

    _FAILURE_PREFIX = re.compile(
        r"^(?:ERR(?:OR)?|FAIL(?:ED)?|BLOCKED|PARTIAL)\s*:",
        re.IGNORECASE,
    )
    _EXECUTION_FAILURE_PREFIX = re.compile(
        r"^(?:[A-Z][A-Z _-]*\s+)?EXECUTION FAILED\s*:",
        re.IGNORECASE,
    )
    _TOOL_RUNTIME_FAILURE = re.compile(
        r"^(?:MCP\s+)?Tool\s+.+?\s+(?:raised an error|is disabled or not available)\b",
        re.IGNORECASE,
    )
    _NON_RETRYABLE_MARKERS = (
        "protected path",
        "sensitive path",
        "permission denied",
        "sensitive app",
        "administrator rights required",
        "not installed",
        "credentials not configured",
        "rate limit exceeded",
        "disabled or not available",
        "no bluetooth adapter",
        "no wifi adapter",
        "not supported on this display",
    )
    
    @staticmethod
    def _schema_check(result: Any, schema: Dict[str, Any]) -> bool:
        """Fast synchronous check to ensure result matches expected output schema."""
        # For our unified tools, mostly checking if it's a string
        if schema.get("type") == "string":
            return isinstance(result, str)
        elif schema.get("type") == "object":
            return isinstance(result, dict)
        elif schema.get("type") == "array":
            return isinstance(result, list)
        # If schema is empty or unknown, assume valid
        return True

    @classmethod
    def _explicit_failure(cls, result: Any) -> VerifyResult | None:
        """Recognize deterministic tool failure contracts before LLM review.

        Maya's native tools consistently expose operational failures through a
        small set of prefixes. Only the beginning of the result is inspected so
        ordinary content containing words such as "ERROR" is not misclassified.
        """
        if not isinstance(result, str):
            return None

        text = result.strip()
        if not text:
            return None

        is_failure = bool(
            cls._FAILURE_PREFIX.match(text)
            or cls._EXECUTION_FAILURE_PREFIX.match(text)
            or cls._TOOL_RUNTIME_FAILURE.match(text)
        )
        if not is_failure:
            return None

        normalized = text.lower()
        retryable = not text.upper().startswith("PARTIAL:") and not any(
            marker in normalized for marker in cls._NON_RETRYABLE_MARKERS
        )
        # Keep enough detail for argument re-planning without feeding an
        # unbounded tool response back into the retry prompt and logs.
        reason = text[:500]
        return VerifyResult(valid=False, reason=reason, retryable=retryable)

    @staticmethod
    async def _llm_verify(tool_name: str, result: Any) -> VerifyResult:
        """Asynchronous semantic check using LLM to ensure the result is correct.
        
        tools/ is one level below backend/, so:
          ..brain.providers  = backend.brain.providers  ✓
          ..config           = backend.config           ✓
        """
        try:
            from ..brain.providers.gemini_adapter import gemini_adapter
            from ..config.model_config import get_model  # noqa: F401 — unused here but confirms path

            prompt = (
                f"You are a strict output verifier. Review the following result from tool '{tool_name}'.\n"
                f"Result: {str(result)[:2000]}\n\n"
                f"Is this result semantically valid for the tool? "
                f"Answer with 'VALID' if it looks correct, or 'INVALID: <reason>' if there is an error or it looks wrong."
            )

            # Empty context — stateless one-shot check
            response = await gemini_adapter.generate_response([], prompt)

            if response.strip().upper().startswith("VALID"):
                return VerifyResult(valid=True)
            else:
                reason = response.replace("INVALID:", "").strip()
                return VerifyResult(valid=False, reason=reason, retryable=True)

        except Exception as e:
            logger.error(f"Semantic verification failed for {tool_name}: {e}")
            # If verification itself fails (network, etc.), assume valid — don't block execution
            return VerifyResult(valid=True, reason=f"Verification unavailable: {e}")

    @classmethod
    async def verify(cls, tool_name: str, result: Any, manifest: ToolManifest) -> VerifyResult:
        """
        Verify the tool result in two steps:
        1. Fast schema check
        2. Semantic check (if required by manifest)
        """
        # Step 1: Schema Check
        if not cls._schema_check(result, manifest.output_schema):
            return VerifyResult(
                valid=False,
                reason="schema_mismatch",
                retryable=False,
            )

        # Step 2: Deterministic failure-contract check. This must happen before
        # semantic verification so obvious ERR:/ERROR: responses never consume
        # another model call or get accepted as a valid string.
        explicit_failure = cls._explicit_failure(result)
        if explicit_failure is not None:
            return explicit_failure

        # Step 3: Semantic Verification
        if manifest.needs_semantic_verify:
            return await cls._llm_verify(tool_name, result)

        return VerifyResult(valid=True)
