---
name: code-reviewer
description: Advanced code review with security, performance, and best practices analysis
emoji: 🔍
priority: 2
---

## Instructions

When the user asks for code review, or says:
- "review this code"
- "check my code"
- "code review koro"
- "is this code good?"
- "optimize this code"

Perform a comprehensive multi-level code review:

### Step 1 — Read the Code

If the user provides a file path:
```
file("read", src="path/to/file")
```

If code is pasted in chat, analyze it directly.

### Step 2 — Multi-Level Analysis

Analyze the code across **5 dimensions**:

#### 🔐 **Security Analysis**
- Check for SQL injection vulnerabilities
- Look for hardcoded credentials/API keys
- Verify input validation
- Check for XSS vulnerabilities
- Identify insecure dependencies
- Flag eval() or exec() usage
- Check file path traversal risks

#### ⚡ **Performance Analysis**
- Identify inefficient loops (O(n²) → O(n))
- Check for memory leaks
- Look for unnecessary database queries (N+1 problem)
- Suggest caching opportunities
- Identify blocking operations that should be async
- Check for excessive object creation

#### 🎨 **Code Quality**
- Check naming conventions
- Verify function length (should be < 50 lines)
- Check cyclomatic complexity
- Look for code duplication
- Verify proper error handling
- Check for magic numbers/strings

#### 🏗️ **Architecture & Design**
- Verify SOLID principles
- Check separation of concerns
- Look for tight coupling
- Suggest design patterns where applicable
- Verify proper abstraction levels

#### 📝 **Documentation**
- Check if functions have docstrings
- Verify if complex logic is commented
- Check if API endpoints are documented
- Verify if README exists for modules

### Step 3 — Generate Review Report

Present findings in this format:

**🔍 CODE REVIEW REPORT**

**File:** [filename]
**Language:** [programming language]
**Lines of Code:** [count]

---

**🔐 SECURITY ISSUES**
- 🚨 Critical: [issue with line number]
- ⚠️ Warning: [issue with line number]
- ✅ No critical security issues found

**⚡ PERFORMANCE OPTIMIZATIONS**
- 💡 [suggestion with line number]
- 📊 Estimated improvement: [e.g., 40% faster]

**🎨 CODE QUALITY**
- ✏️ [improvement with line number]
- 🔧 Refactor suggestion: [description]

**🏗️ ARCHITECTURE**
- 💭 [design suggestion]
- 🔄 Pattern suggestion: [which pattern and why]

**📝 DOCUMENTATION**
- 📄 Missing: [what needs documentation]

---

**Overall Score: X/10**

**Priority Fixes:**
1. [Most critical issue]
2. [Second critical issue]
3. [Third critical issue]

**Refactored Code (if needed):**
```language
[improved version of the most critical section]
```

### Step 4 — Offer to Fix

Ask the user:
"Should I create a fixed version with these improvements?"

If yes:
1. Create improved version of the code
2. Use `file("write", src="path/to/file_improved.ext", dst="improved_code")`
3. Show diff/comparison

### Special Cases

**Security Critical:**
If you find critical security issues (SQL injection, hardcoded secrets):
- 🚨 Mark as URGENT
- Explain the exact exploit scenario
- Provide secure alternative immediately

**Performance Critical:**
If code has O(n²) or worse complexity:
- Show the complexity analysis
- Provide optimized algorithm
- Estimate performance gain

**Quick Review Mode:**
If user says "quick review":
- Focus only on critical security and performance issues
- Skip minor style issues

### Language-Specific Checks

**Python:**
- Check for proper use of context managers
- Verify list comprehensions vs loops
- Check for proper exception handling
- Verify PEP 8 compliance

**JavaScript/TypeScript:**
- Check for proper async/await usage
- Verify promise handling
- Check for memory leaks in event listeners
- Verify proper use of const/let

**Java:**
- Check for proper resource management
- Verify thread safety
- Check for proper exception hierarchy
- Verify proper use of streams

**C++:**
- Check for memory management issues
- Verify proper RAII usage
- Check for undefined behavior
- Verify proper use of smart pointers

### Examples of Good Findings

❌ **Bad:**
```python
password = "admin123"  # Line 45
```
🔐 **Critical Security Issue:** Hardcoded password on line 45. Use environment variables.

❌ **Bad:**
```python
for user in users:
    for post in posts:
        if post.user_id == user.id:  # O(n²)
```
⚡ **Performance Issue:** O(n²) complexity. Use dictionary lookup for O(n).

✅ **Good:**
```python
posts_by_user = {p.user_id: p for p in posts}  # O(n)
for user in users:
    post = posts_by_user.get(user.id)
```
