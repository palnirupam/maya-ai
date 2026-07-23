import os
import shutil
import time
import logging
import asyncio
from contextvars import ContextVar

from backend.config.runtime_paths import STATE_DIR

logger = logging.getLogger(__name__)

CANVAS_DIR = str((STATE_DIR / "canvas").resolve())

MAX_CANVAS_SIZE = 1024 * 1024  # 1MB
MAX_UPDATES_PER_MIN = 20

# ContextVar to track the active session ID for the currently executing LLM tool call
active_session_id: ContextVar[str] = ContextVar("active_session_id", default="main")

# In-memory store for tracking session update timestamps for rate limiting
# session_id -> list of float timestamps
_session_update_times = {}

def validate_canvas_path(session_id: str, filename: str) -> str:
    """
    Validates that the path resolves strictly inside the session's canvas directory.
    Prevents path traversal attacks. Returns the absolute path if valid.
    """
    safe_session = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
    session_dir = os.path.join(CANVAS_DIR, safe_session)
    
    # Resolve absolute target path
    target_abs = os.path.abspath(os.path.join(session_dir, filename))
    
    try:
        common = os.path.commonpath([session_dir, target_abs])
        # Allow target to be index.html or other static files in the directory
        if common != session_dir:
            raise ValueError("Path traversal detected in canvas filename.")
    except Exception as e:
        raise ValueError(f"Invalid canvas filename: {e}")
        
    return target_abs

def write_canvas_state(session_id: str, html: str, css: str = "", js: str = "") -> str:
    """
    Combines HTML, CSS, and JS, applies rate limiting and size checks,
    and writes the assets atomically to disk under the session directory.
    Returns the absolute path to the written index.html.
    """
    # 1. Enforce combined size limit
    combined_size = len(html) + len(css) + len(js)
    if combined_size > MAX_CANVAS_SIZE:
        raise ValueError(f"Canvas size limit exceeded. Combined payload must be < 1MB (got {combined_size} bytes)")

    # 2. Enforce sliding-window rate limit (20 updates / minute)
    now = time.time()
    update_list = _session_update_times.setdefault(session_id, [])
    # Filter out timestamps older than 60s
    update_list[:] = [t for t in update_list if now - t <= 60]
    if len(update_list) >= MAX_UPDATES_PER_MIN:
        raise RuntimeError("Rate limit exceeded. Maximum of 20 canvas updates per minute allowed.")
    update_list.append(now)

    # 3. Create target directory
    safe_session = "".join(c for c in session_id if c.isalnum() or c in ("-", "_"))
    session_dir = os.path.join(CANVAS_DIR, safe_session)
    os.makedirs(session_dir, exist_ok=True)

    # 4. Inject canvas_bridge.js script and merge styling
    bridge_script = """
    <script>
      window.Maya = {
        triggerAgent: function(prompt) {
          window.parent.postMessage({ type: "trigger_agent", prompt: prompt }, "*");
        }
      };
    </script>
    """
    
    head_tag = "</head>"
    body_tag = "</body>"
    
    full_html = html
    
    if css:
        style_block = f"\n<style>\n{css}\n</style>\n"
        if head_tag in full_html:
            full_html = full_html.replace(head_tag, f"{style_block}{head_tag}", 1)
        else:
            full_html = f"{style_block}{full_html}"
            
    if head_tag in full_html:
        full_html = full_html.replace(head_tag, f"{bridge_script}{head_tag}", 1)
    else:
        full_html = f"{bridge_script}{full_html}"

    if js:
        js_block = f"\n<script>\n{js}\n</script>\n"
        if body_tag in full_html:
            full_html = full_html.replace(body_tag, f"{js_block}{body_tag}", 1)
        else:
            full_html = f"{full_html}{js_block}"

    # 5. Write to temp file then atomic replace
    index_path = os.path.join(session_dir, "index.html")
    temp_path = index_path + ".tmp"
    with open(temp_path, "w", encoding="utf-8") as f:
        f.write(full_html)
        
    os.replace(temp_path, index_path)
    logger.info(f"[Canvas] Wrote canvas state for session '{session_id}' to {index_path}.")
    
    # Broadcast update event to frontend React app
    try:
        from backend.api.websocket.manager import manager
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(manager.broadcast_event("canvas_update", {"session_id": session_id}))
            logger.info(f"[Canvas] Broadcast canvas_update event for session '{session_id}'.")
        except RuntimeError:
            # No running event loop in this thread — schedule via asyncio.run_coroutine_threadsafe
            import threading
            logger.warning(f"[Canvas] No running event loop in current thread — trying thread-safe broadcast.")
            try:
                import asyncio as _asyncio
                for task_loop in [getattr(t, '_loop', None) for t in threading.enumerate()]:
                    if task_loop and task_loop.is_running():
                        _asyncio.run_coroutine_threadsafe(
                            manager.broadcast_event("canvas_update", {"session_id": session_id}),
                            task_loop
                        )
                        logger.info(f"[Canvas] Thread-safe broadcast sent for session '{session_id}'.")
                        break
            except Exception as thread_e:
                logger.error(f"[Canvas] Thread-safe broadcast failed: {thread_e}")
    except Exception as e:
        logger.warning(f"[Canvas] Failed to broadcast update: {e}")

    return index_path

def update_canvas(html: str, css: str = "", js: str = "") -> str:
    """
    MANDATORY TOOL for visual/interactive output. Call this tool IMMEDIATELY when the user asks to:
    - Build a tracker (habit tracker, task tracker, expense tracker, mood tracker, etc.)
    - Create a to-do list, planner, checklist, or kanban board
    - Make a calculator, timer, countdown, stopwatch, or clock
    - Build a dashboard, chart, graph, or data visualization
    - Create any game, quiz, form, or interactive widget
    - Make any HTML/CSS/JS UI component

    DO NOT just reply with text when user asks for a visual tool. ALWAYS call this tool.

    Args:
        html: Complete self-contained HTML document (include DOCTYPE, head, body).
              Make it visually stunning with dark theme (#0f0f1a background), purple/blue gradients,
              smooth animations, modern fonts (Google Fonts), and glassmorphism effects.
        css: Additional CSS styles to inject (optional if already in html <style> tags).
        js: Additional JavaScript to inject (optional if already in html <script> tags).

    Returns success or error message.
    """
    session_id = active_session_id.get()
    try:
        write_canvas_state(session_id, html, css, js)
        return f"SUCCESS: Canvas updated successfully for session {session_id}."
    except Exception as e:
        logger.error(f"[Canvas] Tool execution failed: {e}")
        return f"ERROR: Failed to update canvas: {e}"


async def clean_inactive_sessions_loop():
    """Periodic background task that cleans up directories inactive for more than 24 hours.

    Bug fix: on Windows (NTFS) and most Linux filesystems, a directory's mtime
    is only updated when directory *entries* are added/removed — not when the
    content of existing files inside changes.  Using os.path.getmtime(dir) alone
    would delete active canvases whose HTML was last overwritten more than 24 h
    ago.  We now compare against the newest mtime among ALL files inside the dir.
    """
    while True:
        try:
            await asyncio.sleep(3600)  # check every hour
            now = time.time()
            if not os.path.exists(CANVAS_DIR):
                continue

            for name in os.listdir(CANVAS_DIR):
                path = os.path.join(CANVAS_DIR, name)
                if not os.path.isdir(path):
                    continue

                # Determine the most recent modification across the directory
                # entry itself and every file inside it.
                last_modified = os.path.getmtime(path)
                try:
                    for fname in os.listdir(path):
                        fpath = os.path.join(path, fname)
                        try:
                            last_modified = max(last_modified, os.path.getmtime(fpath))
                        except OSError:
                            pass
                except OSError:
                    pass

                if now - last_modified > 86400:  # 24 hours
                    shutil.rmtree(path)
                    logger.info(f"[Canvas] Cleaned up inactive canvas session directory: {path}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"[Canvas] Error in cleanup loop: {e}")
