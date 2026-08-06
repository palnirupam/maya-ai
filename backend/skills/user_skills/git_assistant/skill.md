---
name: git-assistant
description: Git workflow automation, commit message generation, branch management, merge conflict resolution, and best practices
emoji: 🔀
priority: 2
---

## Instructions

When user needs Git help, or says:
- "Git command ki?"
- "Commit message generate koro"
- "Merge conflict resolve koro"
- "Branch strategy suggest koro"
- "Git history clean koro"

Activate **Git Assistant Mode**:

### 1. 🚀 Quick Git Commands

```
🔀 GIT QUICK REFERENCE

**DAILY COMMANDS:**

# Check status
git status

# See changes
git diff

# Stage files
git add file.py
git add .  # All files

# Commit
git commit -m "message"

# Push
git push origin branch-name

# Pull latest
git pull origin main

# Create branch
git checkout -b feature/new-feature

# Switch branch
git checkout main

# See branches
git branch -a
```

### 2. ✍️ Smart Commit Message Generator

When user says "generate commit message":

```
✍️ COMMIT MESSAGE GENERATOR

Analyzing changes...

**Files Changed:**
- src/auth/login.py (modified)
- src/auth/signup.py (new file)
- tests/test_auth.py (modified)

**Changes Detected:**
- Added password validation
- Implemented email verification
- Updated test cases

**🎯 SUGGESTED COMMIT MESSAGE:**

```
feat(auth): add email verification and password validation

- Implement email verification flow with 6-digit code
- Add password strength validation (min 8 chars, 1 number, 1 special)
- Update unit tests for auth module
- Fix: password hash not storing correctly

Closes #123
```

**Format:** [Conventional Commits]
- feat: New feature
- fix: Bug fix
- docs: Documentation
- style: Code style (formatting)
- refactor: Code refactoring
- test: Add/update tests
- chore: Build/tooling changes

Use this message? ✅
```

### 3. 🌿 Branch Strategy

```
🌿 GIT BRANCHING STRATEGY

**RECOMMENDED: Git Flow**

**MAIN BRANCHES:**
- `main` - Production code (always stable)
- `develop` - Integration branch for features

**SUPPORTING BRANCHES:**
- `feature/*` - New features
- `bugfix/*` - Bug fixes
- `hotfix/*` - Emergency production fixes
- `release/*` - Release preparation

**WORKFLOW:**

1. **New Feature:**
```bash
git checkout develop
git pull origin develop
git checkout -b feature/user-authentication
# ... work on feature ...
git add .
git commit -m "feat: add user authentication"
git push origin feature/user-authentication
# Create Pull Request to develop
```

2. **Bug Fix:**
```bash
git checkout develop
git checkout -b bugfix/login-error
# ... fix bug ...
git commit -m "fix: resolve login timeout issue"
git push origin bugfix/login-error
```

3. **Hotfix (Production):**
```bash
git checkout main
git checkout -b hotfix/critical-security
# ... fix critical issue ...
git commit -m "fix: patch security vulnerability"
git push origin hotfix/critical-security
# Merge to BOTH main AND develop
```

**BRANCH NAMING:**
✅ feature/add-payment-gateway
✅ bugfix/fix-cart-total
✅ hotfix/security-patch-v1.2
❌ new_feature
❌ mybranch
❌ test123
```

### 4. 🔄 Merge Conflict Resolution

```
🔄 MERGE CONFLICT HELPER

**Conflict Detected!**

File: `src/config.py`

```python
<<<<<<< HEAD (your changes)
API_URL = "https://api.prod.example.com"
TIMEOUT = 30
=======
API_URL = "https://api.staging.example.com"
TIMEOUT = 60
>>>>>>> feature/new-api (incoming changes)
```

**CONFLICT ANALYSIS:**

Issue: Both branches modified same variables
- `HEAD`: Production API + 30s timeout
- `feature/new-api`: Staging API + 60s timeout

**RESOLUTION OPTIONS:**

**Option 1: Keep your changes**
```python
API_URL = "https://api.prod.example.com"
TIMEOUT = 30
```

**Option 2: Accept incoming**
```python
API_URL = "https://api.staging.example.com"
TIMEOUT = 60
```

**Option 3: Keep both (recommended)**
```python
# Use environment variable
import os
API_URL = os.getenv("API_URL", "https://api.prod.example.com")
TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
```

**STEPS TO RESOLVE:**
1. Edit the file and choose resolution
2. Remove conflict markers (<<<<<<<, =======, >>>>>>>)
3. Test the code
4. Stage the file: `git add src/config.py`
5. Continue merge: `git merge --continue`
6. Push: `git push`

Want me to apply Option 3?
```

### 5. 📜 Git History Management

```
📜 GIT HISTORY CLEANUP

**Current Situation:**
- 45 commits in feature branch
- Many "WIP", "fix typo", "oops" commits
- Hard to review

**SOLUTION: Interactive Rebase**

```bash
# Squash last 45 commits into logical commits
git rebase -i HEAD~45
```

**BEFORE:** (Messy)
```
feat: add login
fix typo
fix typo again
WIP
add validation
fix validation
more fixes
oops forgot file
final fix i promise
```

**AFTER:** (Clean)
```
feat(auth): implement user login system

- Add login form with email/password
- Implement JWT authentication
- Add input validation
- Add error handling
- Update tests
```

**REBASE COMMANDS:**
- `pick` = keep commit
- `squash` = merge with previous
- `reword` = change commit message
- `drop` = delete commit
- `edit` = modify commit

**EXAMPLE:**
```
pick abc1234 feat: add login
squash def5678 fix typo
squash ghi9012 add validation
squash jkl3456 fix validation
reword mno7890 final commit
```

Clean history = Easy code review! ✅
```

### 6. 🔍 Git Detective (Find Issues)

```
🔍 GIT DETECTIVE

**Who broke the code?**

```bash
# Find who changed a specific line
git blame src/payment.py

# Output:
^abc1234 (John Doe  2026-03-15) def process_payment():
def5678^ (Jane Smith 2026-04-01)     if amount < 0:  # BUG HERE!
ghi9012^ (John Doe  2026-04-05)         return Error
```

Result: Jane Smith introduced the bug on April 1

**When did it break?**

```bash
# Binary search to find breaking commit
git bisect start
git bisect bad              # Current version is broken
git bisect good abc1234     # This commit was working
# Git will checkout commits to test
# Mark each as good or bad until found
```

**What changed in a file?**

```bash
# See file history
git log --follow src/payment.py

# See changes over time
git log -p src/payment.py
```

**Search commit messages:**

```bash
# Find commits mentioning "payment"
git log --grep="payment"

# Find commits by author
git log --author="John"

# Find commits in date range
git log --since="2 weeks ago"
```
```

### 7. ⚡ Git Shortcuts & Aliases

```
⚡ GIT PRODUCTIVITY HACKS

**SET UP ALIASES:**

```bash
# Add to ~/.gitconfig

[alias]
    st = status
    co = checkout
    br = branch
    ci = commit
    unstage = reset HEAD
    last = log -1 HEAD
    visual = log --graph --oneline --all
    undo = reset --soft HEAD~1
```

**USAGE:**
```bash
# Instead of: git status
git st

# Instead of: git checkout main
git co main

# Instead of: git commit -m "message"
git ci -m "message"

# Undo last commit (keep changes)
git undo

# Beautiful commit graph
git visual
```

**SHORTCUTS:**

```bash
# Stage and commit in one line
git commit -am "message"

# Amend last commit
git commit --amend

# Stash changes (temporary save)
git stash
git stash pop  # Restore

# Cherry-pick specific commit
git cherry-pick abc1234

# Show changes in last commit
git show

# Diff between branches
git diff main..develop
```
```

### 8. 🛡️ Git Best Practices

```
🛡️ GIT BEST PRACTICES

**COMMIT GUIDELINES:**

✅ DO:
- Commit often (small, logical changes)
- Write descriptive messages
- Test before committing
- Keep commits atomic (one purpose)

❌ DON'T:
- Commit broken code
- Use "WIP" or "fix" as messages
- Commit large binary files
- Commit secrets (API keys, passwords)

**COMMIT MESSAGE FORMAT:**

```
<type>(<scope>): <subject>

<body>

<footer>
```

**Example:**
```
feat(auth): add two-factor authentication

Implement 2FA using TOTP (Time-based One-Time Password).
Users can enable 2FA in their security settings.

Closes #456
Breaking Change: Requires users to re-login
```

**TYPES:**
- feat: New feature
- fix: Bug fix
- docs: Documentation only
- style: Formatting (no code change)
- refactor: Code restructuring
- perf: Performance improvement
- test: Add/update tests
- build: Build system changes
- ci: CI/CD changes
- chore: Maintenance tasks

**BRANCH PROTECTION:**

```bash
# Protect main branch (GitHub/GitLab)
Settings → Branches → Branch protection rules

✅ Require pull request reviews
✅ Require status checks to pass
✅ Require branches to be up to date
✅ Restrict who can push
✅ Require linear history (no merge commits)
```
```

### 9. 🔐 Git Security

```
🔐 GIT SECURITY CHECKLIST

**⚠️ NEVER COMMIT:**
- API keys (.env files)
- Passwords
- Private keys (SSH, SSL)
- Database credentials
- OAuth tokens
- AWS keys

**IF YOU ACCIDENTALLY COMMITTED SECRETS:**

**IMMEDIATE ACTION:**

1. **Rotate the secret** (generate new key)
2. **Remove from history:**

```bash
# Remove file from ALL commits
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch .env" \
  --prune-empty --tag-name-filter cat -- --all

# Force push (rewrites history)
git push origin --force --all
```

3. **Add to .gitignore:**
```
.env
.env.local
*.key
*.pem
secrets/
config/secrets.yml
```

**PREVENTION:**

Install pre-commit hook:
```bash
# .git/hooks/pre-commit
#!/bin/sh
if git diff --cached | grep -E 'API_KEY|PASSWORD|SECRET'; then
    echo "⚠️  WARNING: Possible secret detected!"
    echo "Please remove secrets before committing."
    exit 1
fi
```

**SCAN FOR SECRETS:**
```bash
# Use tools like:
- git-secrets
- truffleHog
- detect-secrets
```
```

### 10. 🚀 Advanced Git Workflows

```
🚀 ADVANCED GIT WORKFLOWS

**1. FEATURE FLAGS (Trunk-Based Development)**

```bash
# All features merged to main, but hidden behind flags
git checkout main
git checkout -b feature/new-dashboard
# Develop feature with flag
if FEATURE_FLAGS['new_dashboard']:
    show_new_dashboard()
else:
    show_old_dashboard()
# Merge to main even if incomplete
git checkout main
git merge feature/new-dashboard
# Enable flag when ready in production
```

**2. PULL REQUEST TEMPLATES**

Create `.github/pull_request_template.md`:
```markdown
## Description
[Describe your changes]

## Type of Change
- [ ] Bug fix
- [ ] New feature
- [ ] Breaking change

## Testing
- [ ] Unit tests pass
- [ ] Manual testing done

## Checklist
- [ ] Code follows style guide
- [ ] Docs updated
- [ ] No new warnings
```

**3. AUTOMATED RELEASES (Semantic Versioning)**

```bash
# Using semantic-release or similar
git commit -m "feat: add new feature"  # → v1.1.0
git commit -m "fix: patch bug"         # → v1.1.1
git commit -m "feat!: breaking change" # → v2.0.0
```

**4. MONOREPO MANAGEMENT**

```bash
# Git subtrees for subprojects
git subtree add --prefix=packages/auth auth-repo main

# Git submodules for dependencies
git submodule add https://github.com/user/lib.git lib/
git submodule update --init --recursive
```

**5. CI/CD INTEGRATION**

```yaml
# .github/workflows/ci.yml
on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - name: Run tests
        run: npm test
      - name: Check commit message
        run: npx commitlint --from HEAD~1
```
```

### Response Style

- Be clear about git commands
- Always show expected output
- Warn before destructive operations
- Provide rollback instructions
- Use visual diagrams for branching
- Explain why, not just how
- Safety first, always backup
