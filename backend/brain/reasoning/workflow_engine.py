"""
TaskGraph Executor — backend/brain/reasoning/workflow_engine.py

Executes a TaskGraph produced by AnalysisPass.build_task_graph_if_needed().
Handles sequential step-by-step task execution with:
  - Dependency resolution (depends_on ordering)
  - Per-step failure handling (retry / skip / abort)
  - Status streaming back to the caller
  - Shared context (each step's output flows into the next step's context)

TaskGraph JSON format expected:
{
  "tasks": [
    {
      "id": "step_1",
      "type": "TOOL_CALL | LLM_REASONING | SEARCH | WRITE_FILE",
      "description": "What this step does in plain text",
      "failure_mode": "RETRY | SKIP | ABORT",
      "depends_on": [],           // list of step ids whose output is needed
      "args": { ... }             // optional static args; LLM fills rest
    },
    ...
  ]
}
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Dict, List, Optional, Union

logger = logging.getLogger(__name__)

# ── Status codes ──────────────────────────────────────────────────────────────
STEP_PENDING       = "pending"
STEP_RUNNING       = "running"
STEP_DONE          = "done"
STEP_FAILED        = "failed"
STEP_CANCELLED     = "cancelled"
STEP_SKIPPED       = "skipped"
STEP_AWAITING_USER = "awaiting_user"


@dataclass
class StepResult:
    step_id: str
    status: str          # pending / running / done / failed / cancelled / skipped
    output: str = ""
    error: str = ""


@dataclass
class GraphExecutionState:
    results: Dict[str, StepResult] = field(default_factory=dict)
    tasks_dict: Dict[str, dict] = field(default_factory=dict)

    def __init__(self, tasks: List[dict]):
        self.tasks_dict = {t["id"]: t for t in tasks}
        self.results = {
            t["id"]: StepResult(step_id=t["id"], status=STEP_PENDING) for t in tasks
        }

    def get_status(self, step_id: str) -> str:
        return self.results[step_id].status

    def output_of(self, step_id: str) -> str:
        return self.results[step_id].output

    def failed(self, step_id: str) -> bool:
        return self.get_status(step_id) == STEP_FAILED

    def all_deps_satisfied(self, task: dict) -> bool:
        """
        A dependency is satisfied if it is 'done' OR 'skipped'.
        (This allows optional skipped dependencies to not block execution).
        """
        resolvable = {STEP_DONE, STEP_SKIPPED}
        for dep in task.get("depends_on", []):
            if dep not in self.results:
                continue
            status = self.get_status(dep)
            if status not in resolvable:
                return False
        return True

    def has_cancelled_dep(self, task: dict) -> bool:
        """Return True if any dependency is cancelled, failed, or awaiting user input."""
        for dep in task.get("depends_on", []):
            if dep not in self.results:
                continue
            status = self.get_status(dep)
            if status in {STEP_CANCELLED, STEP_FAILED, STEP_AWAITING_USER}:
                return True
        return False


    def _get_all_downstream(self, failed_task_id: str) -> List[str]:
        """Recursively find all tasks that directly or indirectly depend on this task."""
        downstream = []
        to_check = [failed_task_id]
        visited = set()

        while to_check:
            curr = to_check.pop(0)
            if curr in visited:
                continue
            visited.add(curr)

            for tid, t in self.tasks_dict.items():
                if curr in t.get("depends_on", []) and tid not in downstream:
                    downstream.append(tid)
                    to_check.append(tid)
        return downstream

    def handle_failure(self, failed_task_id: str, failure_mode: str) -> List[str]:
        """
        Implements Bug 1 distinct failure modes: cancel_subtree, skip_optional, ask_user.
        """
        actions = []
        mode = failure_mode.upper()

        if mode in ("CANCEL_SUBTREE", "ABORT"):
            # Recursively cancel the entire dependency subtree
            to_cancel = self._get_all_downstream(failed_task_id)
            self.results[failed_task_id].status = STEP_FAILED
            actions.append(f"failed:{failed_task_id}")
            for tid in to_cancel:
                self.results[tid].status = STEP_CANCELLED
                actions.append(f"cancelled:{tid}")

        elif mode in ("SKIP_OPTIONAL", "SKIP"):
            # Only this task is skipped. Downstream re-evaluates.
            self.results[failed_task_id].status = STEP_SKIPPED
            actions.append(f"skipped:{failed_task_id}")

        elif mode == "ASK_USER":
            # Distinct from STEP_FAILED: the engine halts the whole graph rather
            # than silently continuing past a step that needed user input
            # (see execute_task_graph's STEP_AWAITING_USER branch).
            self.results[failed_task_id].status = STEP_AWAITING_USER
            actions.append(f"awaiting_user:{failed_task_id}")

        else: # Default fallback to failed
            self.results[failed_task_id].status = STEP_FAILED
            actions.append(f"failed:{failed_task_id}")

        return actions


async def _execute_step(
    task: dict,
    state: GraphExecutionState,
    session_context: list,
    all_tools: list,
) -> StepResult:
    """
    Run a single TaskGraph step. Dispatches to the correct executor based on
    the task's 'type' field.
    """
    step_id = task["id"]
    step_type = task.get("type", "LLM_REASONING").upper()
    description = task.get("description", "")
    args = task.get("args", {})
    failure_mode = task.get("failure_mode", "RETRY").upper()

    # Inject outputs from dependencies into context
    dep_outputs = []
    for dep_id in task.get("depends_on", []):
        output = state.output_of(dep_id)
        if output:
            dep_outputs.append(f"[Output from step '{dep_id}']: {output}")

    extra_context = "\n".join(dep_outputs)

    max_attempts = 3 if failure_mode == "RETRY" else 1

    for attempt in range(max_attempts):
        try:
            if step_type == "TOOL_CALL":
                result = await _exec_tool_call(task, args, all_tools)
            else:
                # LLM_REASONING, SEARCH, WRITE_FILE — all go through LLM with context
                result = await _exec_llm(description, extra_context, session_context)

            return StepResult(step_id=step_id, status=STEP_DONE, output=result)

        except Exception as e:
            logger.warning(
                f"[WorkflowEngine] Step '{step_id}' attempt {attempt+1} failed: {e}"
            )
            if attempt == max_attempts - 1:
                # Handle failure according to failure_mode
                state.handle_failure(step_id, failure_mode)
                return StepResult(step_id=step_id, status=state.get_status(step_id), error=str(e))

    # Unreachable fallback
    return StepResult(step_id=step_id, status=STEP_FAILED, error="Unknown failure")


async def _exec_tool_call(task: dict, args: dict, all_tools: list) -> str:
    """Execute a direct tool call step."""
    from ...tools.unified import pc, file  # noqa: F401
    func_name = task.get("tool_name") or task.get("id")
    func = next(
        (t for t in all_tools if hasattr(t, "__name__") and t.__name__ == func_name),
        None,
    )
    if not func:
        raise ValueError(f"Tool '{func_name}' not found in all_tools")

    import asyncio
    if asyncio.iscoroutinefunction(func):
        result = await func(**args)
    else:
        result = func(**args)
    return str(result)


async def _exec_llm(description: str, extra_context: str, session_context: list) -> str:
    """Execute an LLM reasoning step with dependency context injected."""
    from ..providers.gemini_adapter import gemini_adapter

    prompt = description
    if extra_context:
        prompt = f"{extra_context}\n\nNow complete this task: {description}"

    response = await gemini_adapter.generate_response(session_context, prompt)
    return response.strip()


async def execute_task_graph(
    graph: Dict[str, Any],
    session_id: str,
    session_context: list,
    all_tools: list,
) -> AsyncGenerator[Union[str, dict], None]:
    """
    Execute a full TaskGraph sequentially respecting dependency order and failure modes.
    Yields str (text chunks) and dict (status events) just like execute_workflow.
    """
    tasks: List[dict] = graph.get("tasks", [])
    if not tasks:
        yield "[WorkflowEngine] No tasks in graph — skipping."
        return

    state = GraphExecutionState(tasks)
    ordered = _topological_sort(tasks)

    total = len(ordered)
    for idx, task in enumerate(ordered):
        step_id = task["id"]
        description = task.get("description", step_id)
        failure_mode = task.get("failure_mode", "RETRY").upper()

        # Check if already cancelled by a parent failure
        if state.get_status(step_id) == STEP_CANCELLED:
            yield {
                "type": "agent_status",
                "data": {
                    "active_agent": "Workflow Engine",
                    "status": f"Step {idx+1}/{total}: '{description}' cancelled (dependency failed).",
                    "loop_count": idx,
                },
            }
            yield f"\n⏭️ Step '{step_id}' cancelled due to dependency failure."
            continue

        # Check if any dependency is cancelled
        if state.has_cancelled_dep(task):
            state.results[step_id].status = STEP_CANCELLED
            yield {
                "type": "agent_status",
                "data": {
                    "active_agent": "Workflow Engine",
                    "status": f"Step {idx+1}/{total}: '{description}' cancelled (dependency failed).",
                    "loop_count": idx,
                },
            }
            yield f"\n⏭️ Step '{step_id}' cancelled due to dependency failure."
            continue

        # Check if dependencies are satisfied
        if not state.all_deps_satisfied(task):
            state.results[step_id].status = STEP_CANCELLED
            yield f"\n⏭️ Step '{step_id}' cancelled due to unsatisfied dependency."
            continue

        # Emit step start event
        yield {
            "type": "agent_status",
            "data": {
                "active_agent": "Workflow Engine",
                "status": f"Step {idx+1}/{total}: {description}",
                "loop_count": idx,
            },
        }

        # Execute the step
        try:
            result = await _execute_step(task, state, session_context, all_tools)
            state.results[step_id] = result
        except Exception as e:
            state.handle_failure(step_id, failure_mode)
            state.results[step_id] = StepResult(step_id=step_id, status=state.get_status(step_id), error=str(e))
            result = state.results[step_id]

        # Stream the step output
        if result.status == STEP_DONE and result.output:
            yield f"\n**Step {idx+1}** — {description}:\n{result.output}\n"
        elif result.status == STEP_AWAITING_USER:
            # This sequential engine has no synchronous way to collect user input
            # mid-graph, so it must halt entirely here — continuing past an
            # unresolved ask_user step would silently skip a required decision.
            yield f"\n⏸️ Step '{step_id}' needs your input before continuing: {result.error}"
            yield f"\n⏸️ Workflow paused at step '{step_id}' — awaiting your response."
            return
        elif result.status == STEP_FAILED:
            yield f"\n⚠️ Step '{step_id}' failed: {result.error}"
            if failure_mode in ("CANCEL_SUBTREE", "ABORT"):
                yield f"\n❌ Workflow aborted at step '{step_id}'."
                return
        elif result.status == STEP_SKIPPED:
            yield f"\n⏭️ Step '{step_id}' skipped (optional)."
        elif result.status == STEP_CANCELLED:
            yield f"\n⏭️ Step '{step_id}' cancelled."

    # Final summary
    done_count = sum(1 for r in state.results.values() if r.status == STEP_DONE)
    fail_count = sum(1 for r in state.results.values() if r.status == STEP_FAILED)
    skip_count = sum(1 for r in state.results.values() if r.status == STEP_SKIPPED)
    cancel_count = sum(1 for r in state.results.values() if r.status == STEP_CANCELLED)
    yield (
        f"\n\n✅ Workflow complete: {done_count} done, "
        f"{fail_count} failed, {skip_count} skipped, {cancel_count} cancelled."
    )


def _topological_sort(tasks: List[dict]) -> List[dict]:
    """
    Simple Kahn's algorithm topological sort.
    Falls back to original order if a cycle is detected (graceful degradation).
    """
    task_map = {t["id"]: t for t in tasks}
    in_degree: Dict[str, int] = {t["id"]: 0 for t in tasks}
    dependents: Dict[str, List[str]] = {t["id"]: [] for t in tasks}

    for task in tasks:
        for dep in task.get("depends_on", []):
            if dep in in_degree:
                in_degree[task["id"]] += 1
                dependents[dep].append(task["id"])

    queue = [t for t in tasks if in_degree[t["id"]] == 0]
    sorted_tasks: List[dict] = []

    while queue:
        task = queue.pop(0)
        sorted_tasks.append(task)
        for dep_id in dependents[task["id"]]:
            in_degree[dep_id] -= 1
            if in_degree[dep_id] == 0:
                queue.append(task_map[dep_id])

    if len(sorted_tasks) != len(tasks):
        # Cycle detected — return original order (graceful fallback)
        logger.warning("[WorkflowEngine] Cycle detected in TaskGraph. Falling back to original order.")
        return tasks

    return sorted_tasks
