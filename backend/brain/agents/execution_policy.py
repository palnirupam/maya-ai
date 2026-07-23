"""Adaptive execution policy for Maya's agent loop.

The planner should make the main tool-capable loop more effective, not replace
it with a weaker execution path. This module keeps the policy decisions small,
deterministic, and easy to test.
"""

from __future__ import annotations

import re
from typing import Any, Mapping


_CODER_ACTION_RE = re.compile(
    r"\b(run|execute|debug|fix|edit|read|create|write|save|delete|move|rename)\b"
    r".{0,30}\b(file|folder|script|project|repo|terminal|powershell|python)\b"
    r"|\b(file|folder|script|project|repo|terminal|powershell)\b"
    r".{0,30}\b(run|execute|debug|fix|edit|read|create|write|save|delete|move|rename)\b"
    r"|\.py\b|\.js\b|\.ts\b|\.tsx\b|\.json\b|\.md\b",
    re.IGNORECASE,
)

_CANVAS_ACTION_RE = re.compile(
    r"\b(canvas|widget|dashboard|tracker|kanban|calculator|interactive|visualization)\b"
    r"|\b(game|app|tool)\b.{0,24}\b(banao|build|create|make)\b"
    r"|\b(banao|build|create|make)\b.{0,24}\b(game|app|tool|ui)\b",
    re.IGNORECASE,
)


def build_execution_brief(
    graph: Mapping[str, Any] | None,
    original_task: str,
    *,
    max_steps: int = 10,
) -> str:
    """Render a bounded internal checklist from a validated TaskGraph."""
    if not isinstance(graph, Mapping):
        return ""

    tasks = graph.get("tasks")
    if not isinstance(tasks, list) or not tasks:
        return ""

    lines = [
        "[ADAPTIVE EXECUTION PLAN - INTERNAL]",
        f"Goal: {' '.join(original_task.split())[:600]}",
        "Use this as a flexible checklist, not a rigid script. Re-plan when tool results change the situation.",
        "Continue until the requested end state is completed and verified. Ask the user only for genuinely missing input or required approval.",
        "Planned steps:",
    ]

    for idx, task in enumerate(tasks[:max_steps], start=1):
        if not isinstance(task, Mapping):
            continue
        description = " ".join(
            str(task.get("description") or task.get("id") or f"Step {idx}").split()
        )[:320]
        depends_on = task.get("depends_on") or []
        dep_text = ""
        if isinstance(depends_on, list) and depends_on:
            dep_text = f" (after: {', '.join(str(dep) for dep in depends_on[:4])})"
        lines.append(f"{idx}. {description}{dep_text}")

    if len(tasks) > max_steps:
        lines.append(f"... plus {len(tasks) - max_steps} additional planned step(s).")

    return "\n".join(lines)


def adaptive_tool_round_limit(
    agent_name: str,
    complexity_score: int,
    graph: Mapping[str, Any] | None = None,
) -> int:
    """Return the loop's maximum tool-round index.

    Existing simple-turn limits stay unchanged. Complex planned work gets more
    room, with a hard cap so a confused model cannot loop forever.
    """
    is_os = agent_name.upper() == "OS_EXECUTOR"
    base = 6 if is_os else 3
    cap = 12 if is_os else 8

    tasks = graph.get("tasks", []) if isinstance(graph, Mapping) else []
    step_count = len(tasks) if isinstance(tasks, list) else 0
    if complexity_score < 7 and step_count == 0:
        return base

    complexity_extra = max(1, min(4, (max(complexity_score, 7) - 5) // 2))
    planned_target = step_count + 2 if step_count else base
    return min(cap, max(base + complexity_extra, planned_target))


def requires_tool_completion(agent_name: str, text: str, *, has_image: bool = False) -> bool:
    """Whether a tool-free answer would leave the user's request unperformed."""
    name = agent_name.upper()
    if name == "OS_EXECUTOR":
        return True
    if name == "RESEARCHER":
        return True
    if name == "CODER":
        return bool(_CODER_ACTION_RE.search(text or ""))
    if name == "CHAT" and not has_image:
        return bool(_CANVAS_ACTION_RE.search(text or ""))
    return False


def completion_audit_prompt(original_task: str) -> str:
    """One-shot recovery prompt used after premature tool-free completion."""
    return (
        "EXECUTION AUDIT: The previous attempt did not call any tool, so the requested real action "
        "has not been completed yet. Re-evaluate the request and use the available tools now. "
        "Inspect tool results, recover from failures, and continue until the requested end state is real. "
        "If execution is genuinely impossible, state one precise blocker without claiming success.\n\n"
        f"Original request: {original_task}"
    )
