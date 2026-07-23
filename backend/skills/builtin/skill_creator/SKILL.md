---
name: skill-creator
description: Help the user create new SKILL.md workflow files for Maya
emoji: 🧩
priority: 5
---

## Instructions

Trigger when the user says anything like:
- "create a skill", "make a skill", "add a skill"
- "teach you to do X", "add workflow for X"
- "I want you to remember how to do X"
- Or any variation in Bengali / Hindi

### Step 1 — Gather requirements (ask all at once, not one by one)

Ask the user these 3 questions together:
1. **Name** — What should this skill be called? (e.g. `morning-routine`, `code-review`, `daily-standup`)
2. **Trigger** — What does the user say to activate this skill? (e.g. "do my morning routine", "review my code")
3. **Steps** — What exactly should Maya do, step by step?

### Step 2 — Generate the SKILL.md content

Use this exact template:

```markdown
---
name: <skill-name>
description: <one-line description in English>
emoji: <relevant emoji>
priority: 10
---

## Instructions

When the user says: <trigger phrase(s)>

1. Step one
2. Step two
3. Step three

### Notes
- Any edge cases or special rules
```

### Step 3 — Save the file

Use `file(action="write", src="<path>", dst="<content>")` to save it at:
```
c:\maya-ai\backend\skills\user_skills\<skill-name>\SKILL.md
```

After saving, confirm:
> "Skill '<name>' has been created and will be active in the next conversation."

### Rules
- Never duplicate what is already in Maya's core personality (WhatsApp, Gmail, YouTube — already built in)
- Skills should add NEW multi-step workflows only
- Always write skill instructions in English
- Keep instructions numbered, clear, and specific
