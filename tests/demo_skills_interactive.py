"""
Interactive Demo: Maya AI Skills in Action
==========================================
Shows how each skill would respond to user requests
"""

import time
import sys

def print_slow(text, delay=0.02):
    """Print text with typing effect"""
    for char in text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(delay)
    print()

def demo_header(title, emoji):
    """Print demo section header"""
    print("\n" + "="*60)
    print(f"{emoji} {title}")
    print("="*60 + "\n")

def demo_code_reviewer():
    demo_header("CODE REVIEWER SKILL", "🔍")
    
    print("👤 USER: Maya, review this code")
    print("\n📝 Code submitted:")
    print("""
def login(username, password):
    query = f"SELECT * FROM users WHERE name='{username}' AND pass='{password}'"
    result = db.execute(query)
    return result
""")
    
    time.sleep(1)
    print("\n🤖 MAYA (Code Reviewer Activated):\n")
    time.sleep(0.5)
    
    print("🔍 CODE REVIEW REPORT")
    print("-" * 60)
    print("File: login.py")
    print("Language: Python")
    print("Lines of Code: 4\n")
    
    print("🔐 SECURITY ISSUES:")
    print("🚨 CRITICAL: SQL Injection vulnerability on line 2")
    print("   - Using string formatting for SQL query")
    print("   - Attacker can inject: ' OR '1'='1")
    print("   - This bypasses authentication!\n")
    
    print("⚡ PERFORMANCE: OK\n")
    
    print("🎨 CODE QUALITY:")
    print("✏️  No password hashing (security risk)")
    print("✏️  No input validation\n")
    
    print("📝 DOCUMENTATION: Missing docstring\n")
    
    print("Overall Score: 3/10 ⚠️\n")
    
    print("🔧 FIXED CODE:")
    print("""
def login(username: str, password: str) -> dict:
    \"\"\"Authenticate user with secure query.\"\"\"
    # Use parameterized query (prevents SQL injection)
    query = "SELECT * FROM users WHERE name=? AND pass=?"
    result = db.execute(query, (username, hash_password(password)))
    return result
""")
    print("\nShould I apply this fix? ✅")

def demo_bug_hunter():
    demo_header("BUG HUNTER SKILL", "🐛")
    
    print("👤 USER: Maya, I'm getting 'list index out of range' error")
    
    time.sleep(1)
    print("\n🤖 MAYA (Bug Hunter Activated):\n")
    time.sleep(0.5)
    
    print("🐛 BUG HUNTER REPORT")
    print("-" * 60)
    print("📍 Location: process_data() function")
    print("🔍 Bug Type: Logic Bug")
    print("⚠️  Severity: Medium\n")
    
    print("WHAT'S BROKEN:")
    print("Trying to access list element that doesn't exist\n")
    
    print("WHY IT'S BROKEN:")
    print("ROOT CAUSE CHAIN:")
    print("1. Loop assumes list has at least 1 item")
    print("2. When empty list passed → IndexError")
    print("3. Missing input validation\n")
    
    print("HOW TO FIX:\n")
    
    print("🚑 Quick Fix (5 seconds):")
    print("Add: if not data: return []\n")
    
    print("🔧 Proper Fix:")
    print("""
def process_data(data):
    # Validate input
    if not data:
        return []
    
    # Safe access with length check
    if len(data) > 0:
        first_item = data[0]
    
    return processed_data
""")
    
    print("\n🛡️  Prevention:")
    print("- Always validate inputs")
    print("- Check list length before access")
    print("- Add test for empty list case\n")
    
    print("Apply fix? ✅")

def demo_productivity_coach():
    demo_header("PRODUCTIVITY COACH SKILL", "📈")
    
    print("👤 USER: Maya, I can't focus. Start focus session")
    
    time.sleep(1)
    print("\n🤖 MAYA (Productivity Coach Activated):\n")
    time.sleep(0.5)
    
    print("✅ FOCUS SESSION STARTED!")
    print("-" * 60)
    print("⏰ Duration: 25 minutes (Pomodoro)")
    print("🎯 Task: What are you working on?")
    print("   → User: 'Fixing bug in login system'")
    print("🔕 Do Not Disturb: ENABLED\n")
    
    print("📊 FOCUS MODE ACTIVE:")
    print("- Notifications muted ✓")
    print("- Distractions blocked ✓")
    print("- Timer running ✓\n")
    
    print("💡 FOCUS TIP:")
    print("Remove phone from desk for better concentration!\n")
    
    print("I'll check on you in 25 minutes. Stay focused! 🔥")
    
    time.sleep(1)
    print("\n[After 25 minutes...]\n")
    
    print("🎉 FOCUS SESSION COMPLETE!")
    print("-" * 60)
    print("⏱️  Time: 25 minutes")
    print("✅ How did it go? Great!\n")
    
    print("QUICK BREAK SUGGESTIONS (5 min):")
    print("🚶 Take a short walk")
    print("💧 Drink water")
    print("👀 Look away from screen (20-20-20 rule)")
    print("🧘 Quick stretch\n")
    
    print("Ready for next Pomodoro session?")

def demo_meeting_assistant():
    demo_header("MEETING ASSISTANT SKILL", "📝")
    
    print("👤 USER: Maya, take meeting notes")
    
    time.sleep(1)
    print("\n🤖 MAYA (Meeting Assistant Activated):\n")
    time.sleep(0.5)
    
    print("📝 MEETING NOTES")
    print("-" * 60)
    print("Meeting: Sprint Planning")
    print("Date: 2026-08-04, 10:00 AM")
    print("Attendees: John, Sarah, Mike, You\n")
    
    print("🎯 AGENDA:")
    print("1. Review last sprint")
    print("2. Plan this sprint")
    print("3. Assign tasks\n")
    
    print("💬 DISCUSSION POINTS:")
    print("[10:05] John: Last sprint went well, 8/10 tasks done")
    print("[10:08] Sarah: Bug in payment system needs priority")
    print("[10:12] Mike: Need 2 more days for feature X\n")
    
    print("✅ DECISIONS MADE:")
    print("1. Priority: Fix payment bug")
    print("2. Feature X deadline extended to Friday\n")
    
    print("🎯 ACTION ITEMS:")
    print("1. Fix payment bug → Sarah → Due: Tomorrow")
    print("2. Complete feature X → Mike → Due: Friday")
    print("3. Write test cases → You → Due: Wednesday\n")
    
    print("📌 NEXT STEPS:")
    print("- Daily standups at 9 AM")
    print("- Next sprint planning: Next Monday\n")
    
    print("💾 Save options:")
    print("1. Save as file")
    print("2. Send email to attendees")
    print("3. Add calendar reminders")

def demo_learning_tutor():
    demo_header("LEARNING TUTOR SKILL", "🎓")
    
    print("👤 USER: Maya, teach me about recursion")
    
    time.sleep(1)
    print("\n🤖 MAYA (Learning Tutor Activated):\n")
    time.sleep(0.5)
    
    print("🎓 LEARNING: Recursion")
    print("-" * 60)
    print("Difficulty: Medium | Duration: ~1 hour\n")
    
    print("📖 LESSON 1: What is Recursion?\n")
    
    print("IN SIMPLE TERMS:")
    print("Think of Russian nesting dolls (matryoshka). Each doll")
    print("contains a smaller version of itself, until you reach")
    print("the smallest one.\n")
    
    print("Recursion is when a function calls ITSELF to solve")
    print("a smaller version of the same problem.\n")
    
    print("THE TECHNICAL EXPLANATION:")
    print("A recursive function has two parts:")
    print("1. BASE CASE: When to stop")
    print("2. RECURSIVE CASE: Call itself with smaller problem\n")
    
    print("VISUAL EXAMPLE:")
    print("""
factorial(5)
  ├─ 5 × factorial(4)
  │    ├─ 4 × factorial(3)
  │    │    ├─ 3 × factorial(2)
  │    │    │    ├─ 2 × factorial(1)
  │    │    │    │    └─ 1 (BASE CASE!)
  │    │    │    └─ 2 × 1 = 2
  │    │    └─ 3 × 2 = 6
  │    └─ 4 × 6 = 24
  └─ 5 × 24 = 120
""")
    
    print("\n✅ COMPREHENSION CHECK:")
    print("Q: What are the two parts of recursion?")
    print("   a) Base case and loop")
    print("   b) Base case and recursive case ✓")
    print("   c) Start and end\n")
    
    print("Correct! Want to try a practical exercise?")

def demo_health_reminder():
    demo_header("HEALTH REMINDER SKILL", "💪")
    
    print("👤 USER: Maya, I've been working for 2 hours straight")
    
    time.sleep(1)
    print("\n🤖 MAYA (Health Reminder Activated):\n")
    time.sleep(0.5)
    
    print("⏰ HEALTH ALERT!")
    print("-" * 60)
    print("You've been working for 2 hours straight!\n")
    
    print("⚠️  WARNING SIGNS:")
    print("- Eyes might be strained")
    print("- Back might be tense")
    print("- Energy probably low\n")
    
    print("🛡️  IMMEDIATE ACTION NEEDED:\n")
    
    print("1. 👀 EYE CARE (20-20-20 Rule)")
    print("   Look at something 20 feet away")
    print("   For 20 seconds")
    print("   Do this NOW!\n")
    
    print("2. 💧 HYDRATION")
    print("   Drink a full glass of water")
    print("   Last drink: 1.5 hours ago ⚠️\n")
    
    print("3. 🚶 MOVEMENT")
    print("   Stand up and walk for 5 minutes")
    print("   Get blood flowing!\n")
    
    print("4. 🪑 POSTURE RESET")
    print("   - Sit back in chair")
    print("   - Roll shoulders back")
    print("   - Adjust screen to eye level\n")
    
    print("🔔 REMINDERS SET:")
    print("- Every 20 min: Eye break")
    print("- Every 30 min: Posture check")
    print("- Every 60 min: Stand and move")
    print("- Every 2 hours: Desk exercises\n")
    
    print("Take a 10-minute break now? Your body needs it! 💪")

def demo_file_organizer():
    demo_header("FILE ORGANIZER SKILL", "📁")
    
    print("👤 USER: Maya, organize my downloads folder")
    
    time.sleep(1)
    print("\n🤖 MAYA (File Organizer Activated):\n")
    time.sleep(0.5)
    
    print("📁 FILE ORGANIZER")
    print("-" * 60)
    print("Target: C:/Users/Downloads\n")
    
    print("🔍 ANALYZING...")
    print("Found:")
    print("- 156 files")
    print("- 2.3 GB total size")
    print("- Last organized: Never\n")
    
    print("⚠️  ISSUES DETECTED:")
    print("1. 45 files in root (messy)")
    print("2. 12 duplicate files (1.2 GB wasted)")
    print("3. 8 large files (>100 MB each)")
    print("4. 5 incomplete downloads (.tmp)\n")
    
    print("🎯 ORGANIZING NOW...\n")
    
    print("Creating folders:")
    print("✓ Documents/")
    print("✓ Images/")
    print("✓ Media/Videos/")
    print("✓ Media/Music/")
    print("✓ Archives/")
    print("✓ Installers/\n")
    
    print("Moving files:")
    print("✓ report.pdf → Documents/PDFs/")
    print("✓ vacation.jpg → Images/Photos/")
    print("✓ song.mp3 → Media/Music/")
    print("✓ movie.mp4 → Media/Videos/")
    print("✓ archive.zip → Archives/ZIP/")
    print("... [moving 156 files]\n")
    
    print("🧹 CLEANUP:")
    print("✓ Deleted 5 incomplete downloads")
    print("✓ Removed 12 duplicates (saved 1.2 GB)")
    print("✓ Deleted temp files (saved 450 MB)\n")
    
    print("✅ ORGANIZATION COMPLETE!")
    print("Space freed: 1.65 GB")
    print("Time saved: You'll find files instantly now! 📁")

def demo_system_optimizer():
    demo_header("SYSTEM OPTIMIZER SKILL", "⚡")
    
    print("👤 USER: Maya, my PC is slow")
    
    time.sleep(1)
    print("\n🤖 MAYA (System Optimizer Activated):\n")
    time.sleep(0.5)
    
    print("⚡ SYSTEM HEALTH CHECK")
    print("-" * 60)
    print("Overall Status: POOR ⚠️\n")
    
    print("CPU: [█████████░] 85% - HIGH USAGE ⚠️")
    print("RAM: [████████░░] 7.2 GB / 8 GB (90% used) ⚠️")
    print("Disk: [██████████] 95% full (450 GB / 500 GB) 🔴")
    print("Temp: 75°C - Running warm ⚠️\n")
    
    print("🔴 CRITICAL ISSUES:")
    print("1. Low disk space (< 5% free)")
    print("2. High RAM usage (> 90%)")
    print("3. CPU constantly above 80%\n")
    
    print("⚡ STARTING OPTIMIZATION...\n")
    
    print("STEP 1: Memory Cleanup [████████░░] 80%")
    print("✓ Closed Chrome (freed 2.1 GB)")
    print("✓ Closed Spotify (freed 450 MB)")
    print("✓ Closed Discord (freed 380 MB)")
    print("RAM freed: 2.9 GB\n")
    
    print("STEP 2: Disk Cleanup [██████████] 100%")
    print("✓ Deleted temp files (3.2 GB)")
    print("✓ Cleared browser cache (1.8 GB)")
    print("✓ Removed Windows.old (12 GB)")
    print("Disk freed: 17 GB\n")
    
    print("STEP 3: Startup Optimization [██████████] 100%")
    print("✓ Disabled 12 unnecessary startup programs")
    print("Boot time: 2 min → 45 sec (-75 seconds!)\n")
    
    print("✅ OPTIMIZATION COMPLETE!\n")
    
    print("📊 RESULTS:")
    print("Performance score: 6/10 → 9/10 ✨")
    print("Boot time: -75 seconds faster")
    print("Free RAM: +2.9 GB")
    print("Free disk: +17 GB")
    print("CPU usage: 85% → 35%\n")
    
    print("🚀 Your PC is now FAST again!")
    print("Restart now to apply all changes?")

def main():
    """Run all skill demos"""
    print("\n" + "🎨"*30)
    print("\n        MAYA AI - SKILLS LIVE DEMO")
    print("        Watch 8 Skills in Action!")
    print("\n" + "🎨"*30)
    
    demos = [
        demo_code_reviewer,
        demo_bug_hunter,
        demo_productivity_coach,
        demo_meeting_assistant,
        demo_learning_tutor,
        demo_health_reminder,
        demo_file_organizer,
        demo_system_optimizer
    ]
    
    for i, demo in enumerate(demos, 1):
        demo()
        
        if i < len(demos):
            print("\n" + "-"*60)
            input("\nPress Enter to see next skill demo... ")
    
    print("\n" + "="*60)
    print("🎉 ALL 8 SKILLS DEMONSTRATED!")
    print("="*60)
    print("\nThese skills make Maya:")
    print("✅ Smarter at coding")
    print("✅ Better at debugging")
    print("✅ Helpful for productivity")
    print("✅ Organized with meetings")
    print("✅ Great at teaching")
    print("✅ Caring about health")
    print("✅ Excellent at organizing")
    print("✅ Master at optimization")
    print("\n" + "="*60)
    print("\n💡 Try them yourself! Just ask Maya naturally:\n")
    print("   'Maya, review this code'")
    print("   'Maya, I have a bug'")
    print("   'Maya, start focus session'")
    print("   'Maya, organize my files'")
    print("\n" + "🚀"*30 + "\n")

if __name__ == "__main__":
    main()
