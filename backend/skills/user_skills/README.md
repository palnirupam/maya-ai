# 🛠️ Maya User Skills

Place your custom markdown-based skills in this folder.

## How to Create a New Skill?

1. Create a new subdirectory inside user_skills/:
   ```
   user_skills/
     my_skill/
       SKILL.md
   ```

2. Add your instructions to the `SKILL.md` file:
   ```markdown
   ---
   name: my_skill
   description: My custom skill description
   emoji: 🎯
   priority: 10
   ---

   ## Instructions

   When the user says:
   - "trigger phrase 1"
   - "trigger phrase 2"

   Follow this workflow:
   1. First, do X
   2. Then, do Y
   ```

3. Save the file — Maya will hot-reload and load it automatically! ♻️

## Tips
- Add `disable: true` in the frontmatter to temporarily disable a skill.
- Increase `priority: 20` to override default builtin skills with the same name.
- You can ask Maya "create a new skill" and she will guide you through the process.
