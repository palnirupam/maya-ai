"""
Task Planner — backend/brain/reasoning/task_planner.py

Decomposes a high-level user goal into an ordered list of sub-tasks.
This is a lightweight layer that sits between AnalysisPass (which determines
WHETHER decomposition is needed) and WorkflowEngine (which executes the graph).

Responsibilities:
- Translate a free-text user goal into a structured TaskGraph dict
- Validate the graph has the required fields before passing to WorkflowEngine
- Apply safe defaults for missing fields (failure_mode, depends_on, etc.)

The actual LLM call is in AnalysisPass._decompose_via_llm(). TaskPlanner
handles validation and sanitisation of the returned graph.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Required fields every task node must have
_REQUIRED_TASK_FIELDS = {"id", "description"}

# Valid failure modes
_VALID_FAILURE_MODES = {
    "RETRY",
    "SKIP",
    "ABORT",
    "CANCEL_SUBTREE",
    "SKIP_OPTIONAL",
    "ASK_USER",
}



def _sanitise_task(raw: Dict[str, Any], idx: int) -> Dict[str, Any]:
    """
    Ensure a task dict has all required fields, filling safe defaults.
    Never raises — returns a best-effort sanitised dict.
    """
    task = dict(raw)

    # Required: id
    if "id" not in task or not str(task.get("id", "")).strip():
        task["id"] = f"step_{idx + 1}"

    # Required: description
    if "description" not in task or not str(task.get("description", "")).strip():
        task["description"] = task.get("type", f"Task {idx + 1}")

    # Optional with safe defaults
    task.setdefault("type", "LLM_REASONING")
    task.setdefault("depends_on", [])
    task.setdefault("args", {})

    # Validate failure_mode
    fm = str(task.get("failure_mode", "RETRY")).upper()
    task["failure_mode"] = fm if fm in _VALID_FAILURE_MODES else "RETRY"

    return task


def validate_and_sanitise(graph: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Validate a TaskGraph dict returned by the LLM.
    Returns a cleaned graph, or None if the structure is fundamentally broken.

    Guarantees:
    - graph["tasks"] is a non-empty list
    - every task has id, description, type, depends_on, args, failure_mode
    - depends_on references only ids that exist in the graph
    - no duplicate ids
    """
    if not isinstance(graph, dict):
        logger.warning("[TaskPlanner] Graph is not a dict — rejecting.")
        return None

    tasks = graph.get("tasks", [])
    if not isinstance(tasks, list) or not tasks:
        logger.warning("[TaskPlanner] Graph has no tasks — rejecting.")
        return None

    # Sanitise each task
    sanitised: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for idx, raw_task in enumerate(tasks):
        if not isinstance(raw_task, dict):
            logger.warning(f"[TaskPlanner] Task {idx} is not a dict — skipping.")
            continue
        task = _sanitise_task(raw_task, idx)

        # Deduplicate IDs
        original_id = task["id"]
        if original_id in seen_ids:
            task["id"] = f"{original_id}_{idx}"
            logger.warning(
                f"[TaskPlanner] Duplicate id '{original_id}' renamed to '{task['id']}'."
            )
        seen_ids.add(task["id"])
        sanitised.append(task)

    if not sanitised:
        logger.warning("[TaskPlanner] All tasks were invalid — rejecting graph.")
        return None

    # Fix dangling depends_on references
    valid_ids = {t["id"] for t in sanitised}
    for task in sanitised:
        bad_deps = [d for d in task["depends_on"] if d not in valid_ids]
        if bad_deps:
            logger.warning(
                f"[TaskPlanner] Task '{task['id']}' has unknown deps {bad_deps} — removing."
            )
            task["depends_on"] = [d for d in task["depends_on"] if d in valid_ids]

    return {"tasks": sanitised}


def build_simple_graph(description: str, steps: List[str]) -> Dict[str, Any]:
    """
    Build a simple linear TaskGraph from a list of plain-text step descriptions.
    Each step depends on the previous one. Useful as a fallback when LLM
    decomposition fails but we still want structured execution.
    """
    tasks = []
    for idx, step in enumerate(steps):
        task_id = f"step_{idx + 1}"
        task = {
            "id": task_id,
            "type": "LLM_REASONING",
            "description": step,
            "failure_mode": "RETRY",
            "depends_on": [f"step_{idx}"] if idx > 0 else [],
            "args": {},
        }
        tasks.append(task)
    return {"tasks": tasks, "goal": description}
