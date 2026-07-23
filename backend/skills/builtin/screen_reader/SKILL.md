---
name: screen-reader
description: Capture screen screenshots and perform structured analysis of UI errors, content reading, and app states.
emoji: 👁️
priority: 3
---

## Instructions

When the user says:
- "screen view" / "view screen"
- "what is showing?" / "what does it say?"
- "what is this error?" / "check the error"
- "look at my screen"
- "read what's on screen"
- Sends a screenshot image and asks a question about it
- Or similar queries in other languages (e.g. Hindi, Bengali)

Follow this workflow:

### Step 1 — Capture (if no image provided)

If no screenshot is already in the context, call:
```
take_verified_screenshot()
```

### Step 2 — Analyze using Vision

Look at the screenshot carefully and identify:

1. **Active Application**: Which application or window is currently visible?
2. **Current State**: What is happening? (e.g., loading, error state, idle, form filling, active editor)
3. **Visible Text**: What is the key visible text content?
4. **Errors/Warnings**: Are there any visible error messages, red highlight text, or warning dialogs?
5. **User Intent**: What is the user trying to accomplish in this specific context?

### Step 3 — Respond in this format

**🖥️ Active App:** [app name]
**📍 Current State:** [what's happening]
**📝 Content:** [key visible text]
**⚠️ Issues Found:** [errors or problems, if any]
**💡 Suggestion:** [what to do next]

### Step 4 — Take action if needed

If the user wants Maya to fix or click something based on what's visible:
1. First use `get_app_text_content(app_name)` for structured text content.
2. Then use `background_app_control()` for clicking or typing.
3. Only use `find_and_click(text)` as a fallback (OCR-based).
4. Confirm with another screenshot: `take_verified_screenshot()`

### Special Cases

**Error on screen:**
- Read the full error message text.
- Search for a solution: `web_search("error message fix")`
- Explain the solution in simple, easy-to-understand language.

**Form/Dialog visible:**
- List all fields and buttons visible on the screen.
- Ask the user what details to fill in before taking any action.

**Code editor visible:**
- Identify the file, language, and line number of the error if any.
- Offer to fix it using `file(action="read", ...)` + `file(action="write", ...)`.
