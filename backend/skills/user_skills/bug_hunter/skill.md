---
name: bug-hunter
description: Intelligent bug detection, root cause analysis, and fix suggestions
emoji: 🐛
priority: 1
---

## Instructions

When user reports a bug or error, or says:
- "why is this not working?"
- "I'm getting an error"
- "bug ache"
- "this is broken"
- Shows an error screenshot
- Shares error logs

Activate **Bug Hunter Mode** and follow this systematic debugging workflow:

### Step 1 — Gather Bug Evidence

Collect all available information:

1. **Error Message/Logs:**
   - If screenshot shared: analyze with vision
   - If file path given: `file("read", src="log_file.txt")`
   - If terminal error: read from chat

2. **Relevant Code:**
   - `file("read", src="failing_file.py")`
   - Read surrounding files if needed

3. **System Context:**
   - `pc("stats")` - check system resources
   - `pc("process_list")` - check running processes
   - Ask user about recent changes

### Step 2 — Bug Classification

Classify the bug type:

#### 🔴 **Crash Bugs** (Application stops)
- Segmentation fault
- Null pointer exception
- Out of memory
- Stack overflow

#### 🟡 **Logic Bugs** (Wrong output)
- Incorrect calculation
- Wrong data returned
- Unexpected behavior
- Edge case failures

#### 🟠 **Integration Bugs** (External service issues)
- API call failures
- Database connection errors
- Network timeouts
- File not found

#### 🔵 **Performance Bugs** (Slow/hangs)
- Infinite loops
- Memory leaks
- Slow queries
- Blocking operations

#### 🟣 **UI/UX Bugs** (Display issues)
- Layout broken
- Missing elements
- Wrong colors/styling
- Responsive issues

### Step 3 — Root Cause Analysis

Use **5 Whys Technique**:

```
🔍 BUG ANALYSIS REPORT

Bug Type: [Classification from above]
Severity: Critical | High | Medium | Low

SYMPTOM:
[What the user sees/experiences]

ERROR MESSAGE:
[Exact error text with line numbers]

ROOT CAUSE CHAIN:
1. Why did this happen? → [immediate cause]
2. Why did that happen? → [deeper cause]
3. Why did that happen? → [even deeper]
4. Why did that happen? → [root cause found]
5. Why did that happen? → [systemic issue]

🎯 ROOT CAUSE:
[The fundamental issue that caused this bug]
```

### Step 4 — Generate Fix Strategy

Provide **3-tier fix approach**:

#### 🚑 **Immediate Workaround** (Right now)
```
Quick fix to unblock the user immediately
[Code or command to apply]
```

#### 🔧 **Proper Fix** (Correct solution)
```
The right way to fix this permanently
[Corrected code with explanation]
```

#### 🛡️ **Prevention** (Stop recurrence)
```
How to prevent this bug class in the future
- Add validation here
- Add test case for this scenario
- Add error handling pattern
```

### Step 5 — Offer to Apply Fix

Ask: "Should I apply this fix to your code?"

If yes:
1. Create backup: `file("copy", src="file.py", dst="file.py.backup")`
2. Apply fix: `file("write", src="file.py", dst="fixed_code")`
3. Suggest testing: "Run the code and let me know if it works!"

### Special Bug Types

#### **Null Pointer / AttributeError**
```python
# ❌ Bug
user.profile.name  # profile might be None

# ✅ Fix
user.profile.name if user.profile else "Unknown"
# or
getattr(user.profile, 'name', 'Unknown')
```

#### **Race Condition**
```python
# ❌ Bug
if not os.path.exists(file):
    create_file(file)  # Another thread might create it here

# ✅ Fix
try:
    with open(file, 'x') as f:  # 'x' = exclusive creation
        pass
except FileExistsError:
    pass
```

#### **Memory Leak**
```javascript
// ❌ Bug
element.addEventListener('click', handler);
// handler never removed, memory leak

// ✅ Fix
element.addEventListener('click', handler);
// Later:
element.removeEventListener('click', handler);
```

#### **SQL Injection**
```python
# ❌ Bug
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# ✅ Fix
cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
```

#### **Infinite Loop**
```python
# ❌ Bug
while user.has_items():
    process(user.items[0])  # Never removes item!

# ✅ Fix
while user.has_items():
    item = user.items.pop(0)
    process(item)
```

### Step 6 — Verify Fix Works

After applying fix:

1. **Test the fix:**
   - Suggest test cases
   - Run the code if possible
   - Check edge cases

2. **Monitor for side effects:**
   - Check if fix broke something else
   - Verify all related features still work

3. **Document the fix:**
   - Add comment explaining why this was needed
   - Update changelog if applicable

### Advanced Debugging Techniques

#### **Binary Search Debugging**
If bug location is unclear:
1. Comment out half the code
2. Does bug still occur?
3. If yes → bug is in other half
4. If no → bug is in commented half
5. Repeat until found

#### **Rubber Duck Debugging**
If stuck, explain the code line by line to the user. Often reveals the bug.

#### **Compare with Working Version**
If it "used to work":
- Ask user: "What changed?"
- Compare with git history
- Check recent commits

#### **Reproduce Minimally**
Create smallest possible code that shows the bug:
```python
# Instead of debugging 1000 lines
# Create a 10-line reproduction
```

### Response Format

```
🐛 BUG HUNTER REPORT

📍 **Location:** [file:line]
🔍 **Bug Type:** [Classification]
⚠️ **Severity:** [Critical/High/Medium/Low]

**WHAT'S BROKEN:**
[Clear description in user's language]

**WHY IT'S BROKEN:**
[Root cause in simple terms]

**HOW TO FIX:**

🚑 **Quick Fix (5 seconds):**
[Immediate workaround]

🔧 **Proper Fix:**
```language
[Fixed code with comments]
```

🛡️ **Prevention:**
- [How to prevent this class of bugs]

**TESTING:**
Test these scenarios after fixing:
1. [Normal case]
2. [Edge case 1]
3. [Edge case 2]
```

### Pro Tips

- **Read error messages carefully** - they often tell you exactly what's wrong
- **Check line numbers** - errors often point to the exact location
- **Look one level up** - sometimes the error appears in one place but is caused by code calling it
- **Check recent changes** - bugs are usually in code that was just modified
- **Test edge cases** - empty lists, null values, zero, negative numbers
