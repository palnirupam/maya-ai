"""
Action Selector — backend/brain/reasoning/action_selector.py

Given a user intent and the available tools (from ToolManifest), selects the
single best tool call or action to perform. Used by OS_EXECUTOR and simple
single-step tasks BEFORE routing to the full TaskGraph path.

This is the lightweight alternative to full TaskGraph decomposition:
- AnalysisPass decides WHICH path (single action vs multi-step graph)
- ActionSelector handles the single-action path efficiently

Selection strategy (ordered by priority):
  1. Exact tool name match from ToolManifest if user text contains the name
  2. Risk-tier filtering — never suggest unsafe tools in non-professional modes
  3. Embedding similarity (if available) — nearest neighbour over tool descriptions
  4. Keyword fallback — count keyword overlaps between request and tool description
"""

from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple

from ...tools.manifest import TOOL_MANIFESTS, ToolManifest, get_manifest

logger = logging.getLogger(__name__)


def _keyword_score(text: str, description: str) -> int:
    """Count how many words from `text` appear in `description`."""
    words = set(re.findall(r"\w+", text.lower()))
    desc_words = set(re.findall(r"\w+", description.lower()))
    return len(words & desc_words)


def select_best_tool(
    user_text: str,
    active_mode: str = "professional",
    capabilities: List[str] | None = None,
) -> Optional[Tuple[str, ToolManifest]]:
    """
    Select the best matching tool for a given user request.

    Returns (tool_name, manifest) or None if no confident match is found.

    Args:
        user_text: The user's raw text request.
        active_mode: Current mode (professional / friendly / coding).
        capabilities: List of enabled capability strings from StateManager.

    Design: O(n) over registered manifests — fast enough for <50 tools.
    """
    capabilities = capabilities or []
    candidates: List[Tuple[int, str, ToolManifest]] = []

    for tool_name, manifest in TOOL_MANIFESTS.items():
        # Risk-tier gate: never suggest unsafe tools in friendly mode
        if manifest.risk_tier == "unsafe" and active_mode.lower() == "friendly":
            continue
        # Capability gate: unsafe tools need terminal.execute or filesystem.write
        if manifest.risk_tier in ("unsafe", "requires_approval"):
            if "terminal.execute" not in capabilities and "filesystem.write" not in capabilities:
                continue

        score = _keyword_score(user_text, manifest.description)
        # Boost score if the tool name itself appears in the text
        if tool_name.lower() in user_text.lower():
            score += 5
        candidates.append((score, tool_name, manifest))

    if not candidates:
        return None

    # Sort by score descending, pick best
    candidates.sort(key=lambda x: x[0], reverse=True)
    best_score, best_name, best_manifest = candidates[0]

    # Minimum confidence threshold — at least 1 keyword overlap
    if best_score < 1:
        return None

    logger.debug(
        f"[ActionSelector] Best tool for {user_text!r}: "
        f"{best_name!r} (score={best_score})"
    )
    return best_name, best_manifest


def rank_tools(
    user_text: str,
    tool_names: List[str],
    top_k: int = 10,
) -> List[str]:
    """
    Rank a list of tool names by relevance to `user_text`.
    Returns the top-k tool names, ordered best-first.
    Used as a fast pre-filter before embedding-based ranking.
    """
    scored: List[Tuple[int, str]] = []
    for name in tool_names:
        manifest = get_manifest(name)
        score = _keyword_score(user_text, manifest.description)
        if name.lower() in user_text.lower():
            score += 5
        scored.append((score, name))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [name for _, name in scored[:top_k]]
