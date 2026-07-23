"""LLM-facing file operation router — single tool covers 10+ actions."""
import asyncio
import os
from ..handlers.file_ops import handle_file

# Extracted text past this length gets compacted into a "fast" tier summary
# instead of being resent raw (and re-resent on every later turn — see
# orchestrator.py's mutable shared session history).
_SUMMARY_THRESHOLD = 4000
_SUMMARY_CACHE_MAX = 64
# Keyed by (abspath, mtime, size) so an unchanged file is only summarized once.
_summary_cache: dict = {}

_SUMMARY_SYSTEM_PROMPT = (
    "You compactly summarize extracted document/file text for another AI agent's "
    "context window. Preserve key facts, numbers, names, dates, and any errors "
    "verbatim. Target 1200-1800 characters. Do not add commentary about the task."
)


async def file(action: str = "", src: str = "", dst: str = "", name: str = "", n: int = 5, path: str = "") -> str:
    """
    Universal file operation router.

    Actions:
      copy src dst        — Copy file/folder (cross-drive, auto-dedupe)
      move src dst        — Move file/folder (cross-drive, auto-dedupe)
      rename src newname  — Rename within same directory
      delete src          — Delete file or folder
      mkdir path          — Create folder
      read src            — Read a file (text, PDF, DOCX, or image-via-OCR).
                             Large results are auto-summarized to save tokens.
      write src content   — Write text file (pass content in dst)
      ls [path]           — List directory contents
      search name [n]     — Find files by name across all drives
      delete_by_name name [n] — Find+delete by name (n=max results, default 5)
      organize path       — Auto-organize folder by type
    """
    result = await asyncio.to_thread(handle_file, action, src, dst, name, n, path)

    if action == "read" and isinstance(result, str) and not result.startswith("ERR:") \
            and len(result) > _SUMMARY_THRESHOLD:
        try:
            summary = await _summarize(src, result)
            if summary is not None:
                return summary
        except Exception:
            pass  # summarization is best-effort; never block a successful read

    return result


async def _summarize(src: str, text: str) -> str | None:
    st = os.stat(src)
    key = (os.path.abspath(src), st.st_mtime, st.st_size)
    cached = _summary_cache.get(key)
    if cached is not None:
        return cached

    from ....brain.providers.gemini_adapter import gemini_adapter

    user_msg = f"Summarize this file content:\n\n{text}"
    summary = await gemini_adapter.generate_response(
        [
            {"role": "system", "content": _SUMMARY_SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ],
        user_msg,
        override_tools=[],
        model_tier="fast",
    )
    labeled = f"[Summarized — original {len(text)} chars]\n\n{summary}"

    if len(_summary_cache) >= _SUMMARY_CACHE_MAX:
        _summary_cache.pop(next(iter(_summary_cache)))  # FIFO evict oldest
    _summary_cache[key] = labeled
    return labeled
