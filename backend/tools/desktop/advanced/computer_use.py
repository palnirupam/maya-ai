"""
Maya AI — Background Computer Use
Provides two tools:
  1. background_app_control() — Windows UIA API, no mouse, no focus change
  2. vision_guided_action()   — Screenshot → Gemini Vision → action loop

Design:
- Layer 1: pywinauto (Windows UIA) — fully background, no mouse at all
- Layer 2: vision_guided_action loop — screenshot + Gemini decides actions
- Layer 3 (fallback only): pyautogui — used sparingly, with notification
"""
import asyncio
import json
import logging
import re
import time
from collections import deque

logger = logging.getLogger(__name__)

VISION_LOOP_SYSTEM_PROMPT = """You are a computer automation agent for Maya AI.
You see a screenshot and a task instruction. Output ONLY a valid JSON object.

Available actions:
{"action": "click_element",    "title": "...",  "control_type": "Button|Edit|MenuItem|TabItem|CheckBox"}
{"action": "type_text",        "text": "...",   "target_title": "(optional element title)"}
{"action": "press_key",        "key": "enter|tab|escape|ctrl+s|ctrl+a|ctrl+c|ctrl+v|ctrl+z|alt+f4"}
{"action": "open_app",         "name": "notepad|calc|explorer|chrome|word|excel|powerpoint"}
{"action": "scroll",           "direction": "up|down", "amount": 3}
{"action": "read_screen",      "question": "what does the screen show?"}
{"action": "TASK_COMPLETE",    "summary": "exactly what was accomplished"}
{"action": "TASK_FAILED",      "reason": "why the task cannot be completed"}

Rules:
- Output ONLY raw JSON. No markdown, no explanation, no prefix text.
- For clicking a button that is clearly labeled, use click_element.
- For typing text, use type_text. If target_title is blank, text goes to focused element.
- If previous actions are repeating (same action 3 times), use TASK_FAILED.
- If the task is done, always use TASK_COMPLETE with a clear summary.
"""


def _run_pywinauto_sync(func, *args, **kwargs):
    """Run a sync pywinauto call and return the result or an error string."""
    try:
        return func(*args, **kwargs)
    except Exception as e:
        return f"ERROR: {e}"


async def _run_in_executor(func, *args, **kwargs):
    """Run a synchronous function in a thread pool to avoid blocking the event loop."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


# ─────────────────────────────────────────────────────────────────────────────
# Tool 1: background_app_control
# ─────────────────────────────────────────────────────────────────────────────

def _background_app_control_sync(app_name: str, action: str, params: dict = None) -> str:
    """
    Synchronous implementation — runs in executor to avoid blocking asyncio.
    Uses pywinauto UIA backend for true background operation.
    """
    if params is None:
        params = {}

    APP_EXE_MAP = {
        "notepad":     "notepad.exe",
        "calc":        "calc.exe",
        "calculator":  "calc.exe",
        "explorer":    "explorer.exe",
        "chrome":      "chrome.exe",
        "word":        "WINWORD.EXE",
        "excel":       "EXCEL.EXE",
        "powerpoint":  "POWERPNT.EXE",
        "paint":       "mspaint.exe",
        "cmd":         "cmd.exe",
    }

    try:
        if action == "open":
            import subprocess
            exe = APP_EXE_MAP.get(app_name.lower().strip(), app_name)
            subprocess.Popen(exe, shell=True)
            time.sleep(1.8)
            return f"SUCCESS: Opened '{app_name}'"

        if action == "close":
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            wins = desktop.windows(title_re=f".*{app_name}.*", visible_only=True)
            if not wins:
                return f"No window found matching '{app_name}'"
            wins[0].close()
            return f"SUCCESS: Closed window matching '{app_name}'"

        # Connect without requiring focus
        try:
            import re as _re
            from pywinauto import Desktop
            desktop = Desktop(backend="uia")
            # (?i) = case-insensitive; app_name could be 'notepad' matching 'hello.txt - Notepad'
            win = desktop.window(title_re=f"(?i).*{_re.escape(app_name.strip())}.*", visible_only=True)
            if not win.exists(timeout=2):
                return f"ERROR: No window found for '{app_name}'. Is it running?"
        except Exception as e:
            return f"ERROR connecting to '{app_name}': {e}"

        if action == "get_all_text":
            texts = []
            for ctrl in win.wrapper_object().descendants():
                try:
                    t = ctrl.window_text()
                    if t and t.strip() and len(t.strip()) > 1:
                        texts.append(t.strip())
                except Exception:
                    pass
            # Deduplicate while preserving order
            seen = set()
            unique = []
            for t in texts:
                if t not in seen:
                    seen.add(t)
                    unique.append(t)
            return "\n".join(unique) if unique else "No readable text found."

        elif action == "click_element":
            title   = params.get("title", "")
            c_type  = params.get("control_type", "Button")
            try:
                ctrl = win.child_window(title=title, control_type=c_type, found_index=0)
                ctrl.invoke()  # invoke() works without focus or mouse
                return f"SUCCESS: Invoked element '{title}' (type: {c_type})"
            except Exception:
                # Try by partial title
                try:
                    ctrl = win.child_window(title_re=f".*{title}.*", control_type=c_type, found_index=0)
                    ctrl.invoke()
                    return f"SUCCESS: Invoked element matching '{title}'"
                except Exception as e2:
                    return f"ERROR: Could not find/invoke element '{title}': {e2}"

        elif action == "type_in":
            element_title = params.get("element", "")
            text          = params.get("text", "")
            try:
                ctrl_edit = win.child_window(title=element_title, control_type="Edit", found_index=0) if element_title else win.child_window(control_type="Edit", found_index=0)
                ctrl_doc = win.child_window(title=element_title, control_type="Document", found_index=0) if element_title else win.child_window(control_type="Document", found_index=0)
                
                if ctrl_edit.exists(timeout=0.5):
                    ctrl = ctrl_edit
                elif ctrl_doc.exists(timeout=0.5):
                    ctrl = ctrl_doc
                else:
                    return f"ERROR: Could not find Edit or Document control."
                
                # set_foreground=False keeps window from stealing focus
                ctrl.type_keys(text, with_spaces=True, set_foreground=False)
                return f"SUCCESS: Typed '{text[:30]}...' into element"
            except Exception as e:
                return f"ERROR typing into element: {e}"

        elif action == "get_value":
            element_title = params.get("element", "")
            try:
                ctrl = win.child_window(title=element_title) if element_title else win.wrapper_object()
                return ctrl.get_value() or ctrl.window_text()
            except Exception as e:
                return f"ERROR getting value: {e}"

        elif action == "get_buttons":
            buttons = []
            for ctrl in win.wrapper_object().descendants():
                try:
                    if ctrl.element_info.control_type == "Button":
                        t = ctrl.window_text()
                        if t and t.strip():
                            buttons.append(t.strip())
                except Exception:
                    pass
            return f"Buttons found: {', '.join(buttons)}" if buttons else "No buttons found."

        return f"ERROR: Unknown action '{action}' for background_app_control."

    except Exception as e:
        return f"ERROR in background_app_control('{app_name}', '{action}'): {e}"


async def background_app_control(app_name: str, action: str, params: dict = None) -> str:
    """
    Control a Windows application programmatically without moving the mouse or
    stealing window focus. Uses Windows UI Automation API (pywinauto UIA backend).

    Args:
        app_name (str): The application name to control (e.g. 'notepad', 'chrome', 'word').
                        Use the window title keyword if the exe name is not known.
        action (str): One of:
            'open'         — Launch the application
            'close'        — Close the application window
            'get_all_text' — Extract all visible text from the window (no OCR needed)
            'click_element'— Click a UI element by title (e.g. a button). Pass params.
            'type_in'      — Type text into an Edit field. Pass params.
            'get_value'    — Get the current value/text of an element.
            'get_buttons'  — List all clickable buttons in the window.
        params (dict): Extra args depending on action:
            For 'click_element': {"title": "OK", "control_type": "Button"}
            For 'type_in':       {"element": "Name field", "text": "Hello"}
            For 'get_value':     {"element": "Address bar"}

    Returns: A plain-text result string.
    """
    return await _run_in_executor(_background_app_control_sync, app_name, action, params)


# ─────────────────────────────────────────────────────────────────────────────
# Tool 2: vision_guided_action
# ─────────────────────────────────────────────────────────────────────────────

async def vision_guided_action(instruction: str, max_rounds: int = 8) -> str:
    """
    Executes a multi-step task on the desktop by combining screenshot capture
    with Gemini Vision reasoning. Each round: take screenshot → ask Gemini
    what to do next → execute the action → repeat until TASK_COMPLETE.

    Use this for complex UI tasks that require visual understanding — e.g.:
    'Open Paint and draw a rectangle', 'Fill in the sign-up form',
    'Find and click the Settings gear icon'.

    Args:
        instruction (str): Natural language task description.
        max_rounds (int): Maximum action rounds before giving up (default 8).

    Returns: Final summary string of what was accomplished or why it failed.
    """
    from backend.vision.capture.screen_capture import screen_capture
    from backend.brain.providers.gemini_adapter import gemini_adapter

    action_history: deque = deque(maxlen=30)    # full log
    last_3_actions: deque = deque(maxlen=3)     # for dedup detection

    for round_num in range(max_rounds):
        # ── 1. Capture screen ────────────────────────────────────────────────
        screenshot_b64 = await _run_in_executor(screen_capture.capture_as_base64)
        if not screenshot_b64 or screenshot_b64 == "ERROR_SENSITIVE_APP":
            return "BLOCKED: Sensitive app on screen. Cannot proceed."

        # ── 2. Build prompt with history ─────────────────────────────────────
        history_text = "\n".join(
            f"Round {i+1}: {h}" for i, h in enumerate(action_history)
        ) if action_history else "(none yet)"

        prompt = (
            f"Task: {instruction}\n\n"
            f"Actions taken so far:\n{history_text}\n\n"
            "Look at the screenshot and output the next single action as JSON."
        )
        context = [
            {"role": "system", "content": VISION_LOOP_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ]

        # ── 3. Ask Gemini Vision ─────────────────────────────────────────────
        try:
            gemini_response = await gemini_adapter.generate_response(
                context, prompt,
                image_base64=screenshot_b64,
                override_tools=[]   # no tools here — pure vision reasoning
            )
        except Exception as e:
            logger.error(f"vision_guided_action: Gemini call failed round {round_num}: {e}")
            gemini_response = '{"action": "TASK_FAILED", "reason": "Gemini API error"}'

        # ── 4. Parse JSON (robust — 3-layer fallback) ────────────────────────
        action_data = None
        raw = gemini_response.strip()

        # Layer 1: direct parse
        try:
            action_data = json.loads(raw)
        except json.JSONDecodeError:
            pass

        # Layer 2: extract first {...} block
        if action_data is None:
            match = re.search(r'\{[^{}]*\}', raw, re.DOTALL)
            if match:
                try:
                    action_data = json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        # Layer 3: safe default — press Escape and continue
        if action_data is None:
            logger.warning(f"vision_guided_action: unparseable JSON round {round_num}: {raw[:200]}")
            action_data = {"action": "press_key", "key": "escape"}

        action_name = action_data.get("action", "unknown")

        # ── 5. Dedup detection — abort if stuck in a loop ────────────────────
        last_3_actions.append(action_name)
        if len(last_3_actions) == 3 and len(set(last_3_actions)) == 1 and action_name not in ("TASK_COMPLETE", "TASK_FAILED"):
            return (
                f"⚠️ Vision loop stuck: same action '{action_name}' repeated 3 times. "
                f"Task may need a different approach. History: {list(action_history)[-5:]}"
            )

        action_history.append(f"{action_name}: {json.dumps(action_data)}")
        logger.info(f"[vision_guided_action] Round {round_num+1}/{max_rounds}: {action_name}")

        # ── 6. Execute action ─────────────────────────────────────────────────
        if action_name == "TASK_COMPLETE":
            return f"✅ {action_data.get('summary', 'Task completed successfully.')}"

        elif action_name == "TASK_FAILED":
            return f"❌ Task failed: {action_data.get('reason', 'Unknown reason.')}"

        elif action_name == "open_app":
            result = await background_app_control(action_data.get("name", ""), "open")
            await asyncio.sleep(1.5)

        elif action_name == "click_element":
            title    = action_data.get("title", "")
            c_type   = action_data.get("control_type", "Button")
            # Try pywinauto first (background, no mouse)
            import pygetwindow as gw
            active_win = gw.getActiveWindow()
            app_hint = active_win.title if active_win else "any"
            result = await background_app_control(
                app_hint, "click_element",
                {"title": title, "control_type": c_type}
            )
            # Fallback to OCR click only if UIA failed
            if "ERROR" in result:
                from .vision_tools import find_and_click
                result = await _run_in_executor(find_and_click, title, 4.0)
            await asyncio.sleep(0.6)

        elif action_name == "type_text":
            text  = action_data.get("text", "")
            target = action_data.get("target_title", "")
            import pygetwindow as gw
            active_win = gw.getActiveWindow()
            app_hint = active_win.title if active_win else "any"
            if target:
                result = await background_app_control(app_hint, "type_in", {"element": target, "text": text})
            else:
                # No specific element — send keys to whatever has focus
                # This is the one case where pyautogui is needed
                import pyautogui
                pyautogui.write(text, interval=0.03)
                result = f"Typed: {text[:50]}"
            await asyncio.sleep(0.4)

        elif action_name == "press_key":
            key = action_data.get("key", "")
            import pyautogui
            if "+" in key:
                parts = key.split("+")
                pyautogui.hotkey(*parts)
            else:
                pyautogui.press(key)
            result = f"Pressed key: {key}"
            await asyncio.sleep(0.4)

        elif action_name == "scroll":
            direction = action_data.get("direction", "down")
            amount    = int(action_data.get("amount", 3))
            import pyautogui
            pyautogui.scroll(amount if direction == "up" else -amount)
            result = f"Scrolled {direction} by {amount}"
            await asyncio.sleep(0.3)

        elif action_name == "read_screen":
            # Just take a screenshot — Gemini will describe it next round
            result = "Screenshot captured. Analyzing in next round."

        else:
            result = f"Unknown action '{action_name}' — skipping."

        logger.info(f"[vision_guided_action] Result: {str(result)[:120]}")
        await asyncio.sleep(0.5)   # Brief pause between rounds

    return (
        f"⚠️ Reached max rounds ({max_rounds}) without completing task. "
        f"Last actions: {list(action_history)[-3:]}"
    )
