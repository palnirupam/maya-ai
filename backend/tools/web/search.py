import time
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS
import re

_last_search_time = 0
_search_count = 0
_search_window_start = 0
_MIN_INTERVAL = 3.0   # seconds between requests

def sanitize_html(text: str) -> str:
    """Basic HTML sanitization to strip tags."""
    return re.sub(r'<[^>]+>', '', text)

def web_search(query: str, max_results: int = 5) -> str:
    """
    Search the web using DuckDuckGo directly (no API key required).
    Returns a summarized list of results including titles, URLs, and text snippets.
    
    Args:
        query (str): The search query to look up (max 200 chars).
        max_results (int): The number of results to return (default 5, max 10).
    """
    global _last_search_time, _search_count, _search_window_start

    # Enforce input limits
    query = query[:200]
    max_results = min(max_results, 10)

    current_time = time.time()

    # Enforce minimum interval — sleep instead of hard-failing
    elapsed = current_time - _last_search_time
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)

    # Rate limit: max 10 searches per 60 seconds
    if current_time - _search_window_start > 60:
        _search_window_start = current_time
        _search_count = 0

    if _search_count >= 10:
        return "ERROR: Rate limit exceeded. Maximum 10 searches per minute."

    _last_search_time = time.time()
    _search_count += 1

    # Retry up to 3 times on transient failures
    last_error = None
    for attempt in range(3):
        try:
            results = []
            with DDGS() as ddgs:
                ddgs_gen = ddgs.text(query, max_results=max_results)
                if not ddgs_gen:
                    return "No results found."

                for r in ddgs_gen:
                    title = sanitize_html(r.get("title", ""))
                    body = sanitize_html(r.get("body", ""))[:500]
                    url = r.get("href", "")

                    if not url.startswith(("http://", "https://")):
                        continue

                    results.append(f"Title: {title}\nURL: {url}\nSnippet: {body}\n")

            if not results:
                return "No valid results found."

            return "\n".join(results)

        except Exception as e:
            last_error = e
            if attempt < 2:
                time.sleep(2)

    return f"Search failed after 3 attempts: {str(last_error)}"
