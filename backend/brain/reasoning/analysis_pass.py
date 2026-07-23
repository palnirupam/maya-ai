import re
import dataclasses
from typing import Any, Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

@dataclasses.dataclass
class AnalysisResult:
    complexity_score: int
    model_tier: str
    fast_path_eligible: bool
    needs_task_graph: bool
    task_graph: Optional[Dict[str, Any]] = None

def _heuristic_score(text: str, context: List[Dict[str, str]] = None) -> int:
    """
    Phase A helper: Calculate a complexity score based on heuristics.
    0-1: Very simple (e.g. "volume 50 koro")    -> fast path eligible
    2-5: Moderate   (e.g. "email likhte help")  -> reasoning tier
    6+:  Complex    (e.g. "research then mail")  -> thinking, needs task graph

    Calibrated against complexity_eval.jsonl — eval_heuristic.py gate must pass.
    Weights: single complex verb = 2, multi-step connector = 2, word count boost = 1-3.
    """
    score = 0

    # Word count — long requests are more likely complex
    words = len(text.split())
    if words > 15:
        score += 3
    elif words > 8:
        score += 1

    # Sequential connectors — "then", "tarpor", "por", "ebong" each = new step
    strong_connectors = len(re.findall(
        r"\b(and\s+then|then|tarpor|por\b|ebong)\b",
        text, re.IGNORECASE
    ))
    score += strong_connectors * 2

    # Bare "and" — weak signal (+1)
    bare_and = len(re.findall(r"\band\b", text, re.IGNORECASE))
    score += bare_and

    # Complex single-step verbs — reasoning signal (+2 each, capped at 4)
    COMPLEX_VERBS = (
        r"research|analyze|analyse|summarize|summarise|debug|"
        r"explain|review|optimize|optimise|outline|translate|"
        r"compose|compare|evaluate|suggest|recommend|"
        r"likhte|lekho|likho|list\s+koro|prepare\s+koro"
    )
    complex_matches = len(re.findall(COMPLEX_VERBS, text, re.IGNORECASE))
    score += min(complex_matches * 2, 4)

    # Write/create — weak reasoning signal (+1 per match, capped at 2)
    WRITE_VERBS = r"\bwrite\b|\breport\b|\bbanao\b|\boutline\b"
    write_matches = len(re.findall(WRITE_VERBS, text, re.IGNORECASE))
    score += min(write_matches, 2)

    # Search + follow-up output compound (search kore summary dao)
    if re.search(r"\b(search|fetch)\b.{0,25}\b(summary|report|dao|dekhao)\b", text, re.IGNORECASE):
        score += 2

    # Multi-tool patterns — very high confidence of multi-step workflow (+4)
    MULTI_TOOL = (
        r"(mail|email|send|pathao).{1,30}(zip|file|document|report|attachment)|"
        r"(zip|compress).{1,30}(send|mail|pathao)|"
        r"(backup|copy).{1,30}(delete|remove)|"
        r"(search|fetch|download).{1,30}(summarize|mail|email)"
    )
    if re.search(MULTI_TOOL, text, re.IGNORECASE):
        score += 4

    return score


def _score_to_tier(score: int) -> str:
    """
    Map heuristic score to model tier.
    Threshold calibration:
      fast      : 0-1  (simple OS commands, greetings)
      reasoning : 2-5  (single complex verb, short analysis tasks)
      thinking  : 6+   (multi-step, explicit connectors, multi-tool chains)
    """
    if score <= 1:
        return "fast"
    elif score <= 5:
        return "reasoning"
    else:
        return "thinking"

def run_heuristic_pass(text: str, context: List[Dict[str, str]] = None) -> AnalysisResult:
    """
    Phase A: Local heuristic scoring.
    Latency: < 5ms guaranteed (no I/O, no LLM).
    Outputs: complexity_score, model_tier, fast_path_eligible, needs_task_graph.
    task_graph is always None here — built in Phase B if needed.
    """
    score = _heuristic_score(text, context)
    return AnalysisResult(
        complexity_score=score,
        model_tier=_score_to_tier(score),
        needs_task_graph=(score >= 7),
        task_graph=None,
        fast_path_eligible=(score <= 2)
    )

async def _decompose_via_llm(text: str, context: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    Phase B helper: Calls LLM to decompose a complex task into a validated TaskGraph.
    Output is always passed through TaskPlanner.validate_and_sanitise before returning.
    Falls back to a linear graph if LLM output is malformed.
    """
    try:
        from ..providers.gemini_adapter import gemini_adapter
        from .task_planner import validate_and_sanitise, build_simple_graph

        prompt = (
            "Decompose the following user request into a TaskGraph JSON.\n"
            "Rules:\n"
            "- Each task must have: id (str), type (TOOL_CALL|LLM_REASONING|SEARCH|WRITE_FILE), "
            "description (str), failure_mode (RETRY|SKIP|ABORT), depends_on (list of task ids), args (dict)\n"
            "- Use depends_on to express ordering (tasks without deps run first)\n"
            "- ABORT = stop everything; SKIP = skip this step only; RETRY = retry up to 3 times\n"
            "- Return ONLY valid JSON, no markdown, no explanation\n\n"
            "Example:\n"
            '{"tasks": [\n'
            '  {"id": "step_1", "type": "SEARCH", "description": "Search news", '
            '"failure_mode": "RETRY", "depends_on": [], "args": {}},\n'
            '  {"id": "step_2", "type": "LLM_REASONING", "description": "Summarize", '
            '"failure_mode": "SKIP", "depends_on": ["step_1"], "args": {}}\n'
            "]}\n\n"
            f"User request: {text}"
        )

        response = await gemini_adapter.generate_response(
            context or [], prompt, override_tools=[]
        )

        import json
        clean = response.strip()
        if "```json" in clean:
            clean = clean.split("```json")[1].split("```")[0].strip()
        elif "```" in clean:
            clean = clean.split("```")[1].strip()

        raw_graph = json.loads(clean)

        # Always validate — never pass a raw LLM graph to WorkflowEngine
        validated = validate_and_sanitise(raw_graph)
        if validated:
            logger.info(
                f"[AnalysisPass] TaskGraph built and validated: "
                f"{len(validated.get('tasks', []))} steps"
            )
            return validated

        # LLM returned bad JSON structure — build a simple linear fallback
        logger.warning("[AnalysisPass] LLM graph failed validation — using linear fallback.")
        steps = [s.strip() for s in re.split(
            r"\b(then|and then|tarpor|por|ebong)\b", text, flags=re.IGNORECASE
        ) if s.strip() and len(s.strip()) > 3]
        return build_simple_graph(text, steps if len(steps) > 1 else [text])

    except Exception as e:
        logger.error(f"[AnalysisPass] LLM decomposition failed: {e}")
        return None

async def build_task_graph_if_needed(
    result: AnalysisResult,
    text: str,
    context: List[Dict[str, str]] = None
) -> AnalysisResult:
    """
    Phase B: LLM-based task decomposition.
    Latency: ~500-2000ms (one LLM call using fast model tier).
    Only called when Phase A sets needs_task_graph=True.
    Graph is validated by TaskPlanner before being stored in the result.
    """
    if not result.needs_task_graph:
        return result

    graph = await _decompose_via_llm(text, context)
    return dataclasses.replace(result, task_graph=graph)
