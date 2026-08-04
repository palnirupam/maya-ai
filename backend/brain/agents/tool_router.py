"""
Tool Router
===========
Relevance-ranks a large candidate tool set down to the few tools actually
relevant to a request, using cached embeddings. This slashes the function-call
schema tokens Gemini receives on the heavy OS_EXECUTOR path (~55 tools -> ~12)
which are otherwise re-sent on every tool-round, without touching the already
lean CHAT/CODER/RESEARCHER paths (they fall under ROUTER_SIZE_GATE).

Design guarantees (this must never make Maya worse):
  * Never raises — any failure returns all candidates (pre-router behavior).
  * Never returns an empty list when candidates is non-empty.
  * Embeds each tool signature ONCE (cached in-memory + on disk); per turn only
    the short query is embedded (one small call), or nothing if embeddings are
    unavailable (keyword fallback).
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re

import numpy as np

# Reused as a module-level name so tests can monkeypatch it cleanly.
from ..memory.long_term_memory import _get_embedding

logger = logging.getLogger(__name__)

# ── Tunable knobs ────────────────────────────────────────────────────────────
ROUTER_SIZE_GATE = 18     # only route candidate sets larger than this
TOP_K = 12                # max relevance-ranked tools to keep (pre always-include)
MIN_SIMILARITY = 0.25     # cosine floor for a tool to count as clearly relevant
_RANK_FLOOR_K = 6         # if nothing clears MIN_SIMILARITY, keep this many by rank
_SIG_MAX_CHARS = 200
_KW_MIN_HITS = 3          # keyword hits below this = weak signal -> send all

# Tools that must survive filtering for OS_EXECUTOR regardless of the query:
# post-action verification + control-token tools (mode change / shutdown), so
# those flows never break just because the query didn't mention them.
ALWAYS_INCLUDE = {
    "take_verified_screenshot",
    "change_interaction_mode",
    "manage_system_state",
    # Universal system router (volume/lock/processes + WiFi + Bluetooth). One
    # cheap schema that covers ~20 controls; cross-lingual queries ("blootooth
    # on koro") rank poorly against its signature, so never let it drop.
    "pc",
    "capture_camera_preview",
}

# When the user explicitly asks to send/deliver something, these "final delivery"
# tools MUST survive ranking. Dropping them silently half-completes the task —
# e.g. RESEARCHER fetches the news but OS_EXECUTOR, lacking whatsapp_send_message,
# can only print it instead of sending. Query-gated (see _SEND_INTENT_RE) so they
# never bloat unrelated OS turns like volume/brightness.
_DELIVERY_TOOLS = {
    "whatsapp_send_message",
    "whatsapp_send_file",
    "whatsapp_send_multiple_files",
    "whatsapp_call",
    "get_contact_number",
    "send_background_email",
}
# Includes the write/tell verbs (likho/lekho…) because the message-content turn
# of a send flow often carries ONLY those ("Likho je valo achis" after "Pintu ke
# hi send kor") — without them the net never fires and ranking starves the send
# tools mid-flow. Verb stems are prefix-matched (patha\w*) so conjugations
# (pathao/pathabi/bhejo/likhe…) all count.
_SEND_INTENT_RE = re.compile(
    r"\b(send|forward|reply|message|msg|email|mail|whatsapp|telegram"
    r"|patha\w*|pathi\w*|bhej\w*|vej\w*|likh\w*|lekh\w*)\b"
    r"|পাঠা|বার্তা|মেসেজ|লিখ|লেখ",
    re.IGNORECASE,
)

# When the user asks to save/read/manage a file, the unified `file` tool MUST
# survive ranking. Its terse signature ("Universal file operation router") ranks
# poorly against phrasings like "desktop e save koro new.txt", so a dropped
# `file` tool leaves OS_EXECUTOR unable to write — it can only announce intent
# and stall. Query-gated (see _FILE_INTENT_RE) so it never bloats unrelated OS
# turns like volume/brightness.
_FILE_TOOLS = {"file", "create_pdf"}
_FILE_INTENT_RE = re.compile(
    r"\bfiles?\b|\bfolders?\b|\bdocuments?\b|\bdownloads?\b|ফাইল|ফোল্ডার"
    r"|\.txt|\.md|\.csv|\.json|\.log|\.pdf|\bpdf\b|\.docx?|\.xlsx?|\.py|\.html?"
    r"|text file|save.*(desktop|documents|downloads|\.txt|file|folder)"
    r"|desktop e save|documents e save|save.*desktop"
    r"|(create|delete|move|rename|read|write).*(file|folder)",
    re.IGNORECASE,
)

# Media playback is a narrow, high-confidence capability family.  Semantic
# ranking can otherwise retain generic browser/audio tools while dropping the
# only functions that can actually start or stop headless playback.  Keep both
# directions available because short follow-ups such as "eta bondho koro" use
# the same stable tool set for the whole agent loop.
_MEDIA_TOOLS = {
    "play_youtube_background",
    "stop_youtube_background",
    "pause_media",
}
_MEDIA_INTENT_RE = re.compile(
    r"\b(youtube|yt|video|song|music|audio|gaan|gan|gaanta|sur|sangeet|geet)\b"
    r"|গান|ভিডিও|সঙ্গীত",
    re.IGNORECASE,
)

# backend/data/cache/tool_embeddings.json  (three dirs up from this file = backend/)
_CACHE_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "data", "cache", "tool_embeddings.json",
)

# cache_key -> embedding vector (list[float]); shared in-memory across turns.
_vec_cache: dict[str, list] = {}
_disk_loaded = False


# ── Signatures & cache ───────────────────────────────────────────────────────
def _get_tool_name(tool) -> str:
    """Extract tool name for both callable functions and dict tool schemas."""
    if hasattr(tool, "__name__"):
        return str(getattr(tool, "__name__"))
    if isinstance(tool, dict):
        if tool.get("type") == "function":
            fn = tool.get("function") or {}
            name = fn.get("name")
        else:
            name = tool.get("name")
        if name:
            return str(name)
    return ""


def _signature(tool) -> str:
    """A short, stable text fingerprint of a tool: name + first docstring line."""
    if hasattr(tool, "__name__"):
        name = getattr(tool, "__name__", "") or ""
        doc = (getattr(tool, "__doc__", "") or "").strip()
    elif isinstance(tool, dict):
        if tool.get("type") == "function":
            fn = tool.get("function") or {}
            name = fn.get("name", "") or ""
            doc = (fn.get("description", "") or "").strip()
        else:
            name = tool.get("name", "") or ""
            doc = (tool.get("description", "") or "").strip()
    else:
        name = ""
        doc = ""
    first_line = doc.split("\n", 1)[0].strip() if doc else ""
    sig = f"{name}: {first_line}" if first_line else name
    return sig[:_SIG_MAX_CHARS]


def _cache_key(name: str, signature: str) -> str:
    digest = hashlib.sha1(signature.encode("utf-8")).hexdigest()[:12]
    return f"{name}:{digest}"


def _load_disk_cache() -> None:
    global _disk_loaded
    if _disk_loaded:
        return
    _disk_loaded = True
    try:
        if os.path.exists(_CACHE_PATH):
            with open(_CACHE_PATH, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if isinstance(data, dict):
                _vec_cache.update(data)
                logger.debug(f"[ToolRouter] Loaded {len(data)} cached tool vectors.")
    except Exception as exc:
        logger.warning(f"[ToolRouter] Could not load embedding cache: {exc}")


def _save_disk_cache() -> None:
    try:
        os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
        with open(_CACHE_PATH, "w", encoding="utf-8") as fh:
            json.dump(_vec_cache, fh)
    except Exception as exc:
        logger.warning(f"[ToolRouter] Could not save embedding cache: {exc}")


def _embed_tools(candidates) -> dict:
    """Return name -> (signature, vector|None), embedding cache-misses once.

    Only call this when the embedder is known to work (query embedded OK), so we
    never fire dozens of doomed embedding calls during an outage.
    """
    _load_disk_cache()
    result: dict = {}
    dirty = False
    for tool in candidates:
        name = _get_tool_name(tool)
        if not name:
            continue
        sig = _signature(tool)
        key = _cache_key(name, sig)
        vec = _vec_cache.get(key)
        if vec is None:
            vec = _get_embedding(sig)
            if vec is not None:
                _vec_cache[key] = vec
                dirty = True
        result[name] = (sig, vec)
    if dirty:
        _save_disk_cache()
    return result


# ── Ranking strategies ───────────────────────────────────────────────────────
def _rank_semantic(query_vec, tool_data: dict, top_k: int, min_similarity: float) -> set:
    """Cosine-rank tools against the query embedding. Returns a set of names."""
    qa = np.array(query_vec, dtype=float)
    qn = np.linalg.norm(qa)
    if qn == 0 or not np.isfinite(qa).all():
        return set()

    scored: list = []
    for name, (_sig, vec) in tool_data.items():
        if vec is None:
            continue
        b = np.array(vec, dtype=float)
        bn = np.linalg.norm(b)
        if bn == 0 or not np.isfinite(b).all():
            continue
        scored.append((float(np.dot(qa, b) / (qn * bn)), name))

    if not scored:
        return set()

    scored.sort(reverse=True)
    above = [n for s, n in scored if s >= min_similarity][:top_k]
    if above:
        return set(above)
    # Weak absolute similarity (e.g. cross-lingual query): keep the top few by
    # pure rank so we still shrink the set instead of falling back to everything.
    return {n for _s, n in scored[: min(_RANK_FLOOR_K, len(scored))]}


def _rank_keyword(query: str, tool_data: dict) -> set:
    """Fallback used when embeddings are unavailable: token substring match."""
    tokens = {w for w in re.findall(r"[a-z0-9_]+", (query or "").lower()) if len(w) > 2}
    if not tokens:
        return set()
    hits = set()
    for name, (sig, _vec) in tool_data.items():
        haystack = f"{name} {sig}".lower()
        if any(tok in haystack for tok in tokens):
            hits.add(name)
    return hits


# ── MCP (external) tool routing ──────────────────────────────────────────────
# MCP schemas arrive as provider-neutral dicts ({"name", "description", ...}),
# not native callables, so they need their own signature/embedding path.
def _mcp_signature(tool: dict) -> str:
    """Short text fingerprint of an MCP schema: namespaced name + first doc line."""
    name = (tool.get("name") if isinstance(tool, dict) else "") or ""
    desc = (tool.get("description") if isinstance(tool, dict) else "") or ""
    first_line = desc.strip().split("\n", 1)[0].strip()
    sig = f"{name}: {first_line}" if first_line else name
    return sig[:_SIG_MAX_CHARS]


def _embed_mcp_tools(mcp_tools: list) -> dict:
    """Return name -> (signature, vector|None) for dict-form MCP schemas.

    Mirrors ``_embed_tools`` but for external MCP schemas. Signatures are cached
    on the same in-memory/disk store, so each MCP tool is embedded only once.
    """
    _load_disk_cache()
    result: dict = {}
    dirty = False
    for tool in mcp_tools:
        name = tool.get("name") if isinstance(tool, dict) else None
        if not name:
            continue
        sig = _mcp_signature(tool)
        key = _cache_key(name, sig)
        vec = _vec_cache.get(key)
        if vec is None:
            vec = _get_embedding(sig)
            if vec is not None:
                _vec_cache[key] = vec
                dirty = True
        result[name] = (sig, vec)
    if dirty:
        _save_disk_cache()
    return result


def select_relevant_mcp_tools(
    query: str,
    mcp_tools: list,
    *,
    top_k: int = TOP_K,
    min_similarity: float = MIN_SIMILARITY,
) -> list:
    """Return the subset of external ``mcp_tools`` relevant to ``query``.

    Deliberately UNLIKE :func:`select_relevant_tools`: there is **no rank-floor
    and no pass-through-all net**. For external MCP schemas the correct answer to
    an unrelated request is *zero* tools. Generic knowledge-graph / memory
    schemas ("search nodes", "read graph") otherwise ride along on every
    OS_EXECUTOR turn, baiting the model into empty lookups and spamming
    HIGH-risk approvals instead of doing what the user actually asked.

    Never raises. When embeddings are down it falls back to keyword matching; a
    total miss returns ``[]`` (MCP is opt-in, so an empty result is correct, not
    a failure to be papered over).
    """
    try:
        mcp_tools = list(mcp_tools)
        if not mcp_tools:
            return mcp_tools

        by_name: dict = {}
        for tool in mcp_tools:
            name = tool.get("name") if isinstance(tool, dict) else None
            if name:
                by_name[name] = tool
        if not by_name:
            return []

        query_vec = _get_embedding(query) if query else None
        if query_vec is not None:
            tool_data = _embed_mcp_tools(mcp_tools)
        else:
            tool_data = {n: (_mcp_signature(t), None) for n, t in by_name.items()}

        have_vectors = query_vec is not None and any(
            v is not None for (_s, v) in tool_data.values()
        )

        if have_vectors:
            # Cosine-rank, keep only the clearly relevant (>= min_similarity).
            # No _RANK_FLOOR_K: an off-topic turn keeps nothing.
            selected = _rank_semantic(
                query_vec, tool_data, top_k, min_similarity
            )
            # _rank_semantic falls back to its own floor when nothing clears the
            # bar; strip that here so MCP stays strictly threshold-gated.
            scored_above = {
                n for n in selected
                if _cosine(query_vec, tool_data.get(n, (None, None))[1]) >= min_similarity
            }
            selected = scored_above
        else:
            # Embeddings unavailable → keyword match. Empty is an acceptable
            # (opt-in) result, so there is no "weak signal → send all" net.
            selected = _rank_keyword(query, tool_data)

        return [by_name[n] for n in selected if n in by_name]
    except Exception as exc:
        logger.warning(
            f"[ToolRouter] select_relevant_mcp_tools failed ({exc}); "
            "dropping MCP tools this turn"
        )
        return []


def _cosine(query_vec, vec) -> float:
    """Cosine similarity with defensive guards; returns -1.0 on any bad input."""
    if vec is None:
        return -1.0
    try:
        qa = np.array(query_vec, dtype=float)
        b = np.array(vec, dtype=float)
        qn = np.linalg.norm(qa)
        bn = np.linalg.norm(b)
        if qn == 0 or bn == 0 or not np.isfinite(qa).all() or not np.isfinite(b).all():
            return -1.0
        return float(np.dot(qa, b) / (qn * bn))
    except Exception:
        return -1.0


# ── Public API ───────────────────────────────────────────────────────────────
def select_relevant_tools(
    query: str,
    candidates: list,
    *,
    top_k: int = TOP_K,
    min_similarity: float = MIN_SIMILARITY,
    always_include_names=ALWAYS_INCLUDE,
) -> list:
    """Return the subset of ``candidates`` most relevant to ``query``.

    Falls back to all candidates on any weak signal or failure, and always
    unions in ``always_include_names`` present in the candidate set.
    """
    try:
        candidates = list(candidates)
        if not candidates:
            return candidates

        by_name = {}
        for tool in candidates:
            name = _get_tool_name(tool)
            if name:
                by_name[name] = tool

        # Embed the (short) query first — this also probes whether embeddings
        # are working at all before we bother embedding the tools.
        query_vec = _get_embedding(query) if query else None

        if query_vec is not None:
            tool_data = _embed_tools(candidates)
        else:
            tool_data = {
                name: (_signature(tool), None)
                for name, tool in by_name.items()
            }

        have_vectors = query_vec is not None and any(
            v is not None for (_s, v) in tool_data.values()
        )

        selected: set = set()
        used_keyword = False
        if have_vectors:
            selected = _rank_semantic(query_vec, tool_data, top_k, min_similarity)

        if not selected:
            selected = _rank_keyword(query, tool_data)
            used_keyword = True

        # Weak keyword-only signal → don't risk dropping the needed tool.
        if used_keyword and len(selected) < _KW_MIN_HITS:
            logger.info("[ToolRouter] weak signal; passing through all candidates")
            return candidates

        # Safety net: keep verification / control-token tools if present.
        for name in always_include_names:
            if name in by_name:
                selected.add(name)

        # Query-gated delivery safety net: when the user asks to send/deliver,
        # never let ranking drop the send tool (see _DELIVERY_TOOLS).
        if _SEND_INTENT_RE.search(query or ""):
            for name in _DELIVERY_TOOLS:
                if name in by_name:
                    selected.add(name)

        # Query-gated file safety net: when the user asks to save/read/manage a
        # file, never let ranking drop the `file` tool (see _FILE_INTENT_RE).
        if _FILE_INTENT_RE.search(query or ""):
            for name in _FILE_TOOLS:
                if name in by_name:
                    selected.add(name)

        # Query-gated media safety net: a routed OS/media request must never
        # reach the model without its real background playback functions.
        if _MEDIA_INTENT_RE.search(query or ""):
            for name in _MEDIA_TOOLS:
                if name in by_name:
                    selected.add(name)

        result = [by_name[n] for n in selected if n in by_name]
        return result or candidates
    except Exception as exc:
        logger.warning(f"[ToolRouter] select_relevant_tools failed ({exc}); using all candidates")
        try:
            return list(candidates)
        except Exception:
            return candidates
