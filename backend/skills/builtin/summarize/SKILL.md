---
name: summarize
description: Summarize any content into a structured, clear format
emoji: 📋
priority: 3
---

## Instructions

Trigger when the user asks to summarize content — a webpage, document, text, news, code, or any pasted content.

Trigger phrases include: "summarize", "short version", "key points", "tldr", "what does this say", or pasting a URL/document with a question.

### Output Format

Always structure the summary as follows:

**Topic:** [1 line — what this is about]

**Key Points:**
- Point 1
- Point 2
- Point 3
(5 points maximum, each under 15 words)

**Takeaway:** [1–2 sentences — the single most important thing]

**Details:** [Only include if the user explicitly asks for depth]

### Rules

1. **Language matching** — Respond in the same language the user used to ask.
2. **Length** — Default is SHORT. If the user asks for "detailed" or "full summary", expand.
3. **For code** — Explain what it does in plain language, not how it works internally, unless asked.
4. **For news** — Always cover: who, what, when, where in the key points.
5. **For long documents** — If the content is over 2000 words, ask which section to focus on before summarizing.