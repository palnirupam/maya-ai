---
name: meeting-assistant
description: Smart meeting preparation, note-taking, action item tracking, and follow-up automation
emoji: 📝
priority: 4
---

## Instructions

When user needs meeting help, or says:
- "I have a meeting"
- "Take meeting notes"
- "Meeting e ki ki discuss hobe"
- "Prepare for meeting"
- "Meeting summary"

Activate **Meeting Assistant Mode**:

### Pre-Meeting (Preparation)

When user says "I have a meeting about [topic] in [time]":

```
📅 MEETING PREP CHECKLIST

Meeting: [Topic]
Time: [When]
Duration: [How long]

✅ **PREPARATION TASKS:**

1. 📋 Agenda Ready?
   - Review meeting invite
   - List discussion points
   - Prepare questions

2. 📊 Materials Ready?
   - Presentation slides
   - Data/reports needed
   - Screen to share

3. 🎯 Your Objectives:
   - What do you want to achieve?
   - What decisions need to be made?
   - What info do you need?

4. 👥 Attendees Research:
   - Who will be there?
   - What are their concerns?
   - Any background needed?

⏰ REMINDER SET: [10 minutes before meeting]

💡 Pro tip: Join 2 minutes early to test audio/video
```

Set reminder:
- 10 mins before: "Meeting in 10 minutes! Got your materials?"
- 2 mins before: "Time to join! Link: [if provided]"

### During Meeting (Real-time Notes)

**Structured Note-Taking:**

```
📝 MEETING NOTES

**Meeting:** [Title]
**Date:** [Date and Time]
**Attendees:** [List of people]
**Facilitator:** [Who's running it]

---

**🎯 AGENDA:**
1. [Agenda item 1]
2. [Agenda item 2]
3. [Agenda item 3]

---

**💬 DISCUSSION POINTS:**

[Timestamp] **[Speaker Name]:**
- [Key point raised]
- [Important opinion/concern]
- [Decision made]

[Next timestamp] **[Speaker Name]:**
- [Their response]
- [Additional information]

---

**✅ DECISIONS MADE:**
1. [Decision 1] - Decided by: [Name]
2. [Decision 2] - Decided by: [Name]

---

**🎯 ACTION ITEMS:**
1. [Task] → Assigned to: [Name] → Due: [Date]
2. [Task] → Assigned to: [Name] → Due: [Date]
3. [Task] → Assigned to: [Name] → Due: [Date]

---

**❓ OPEN QUESTIONS:**
1. [Question that needs follow-up]
2. [Unclear point to clarify]

---

**📌 NEXT STEPS:**
- [What happens next]
- Next meeting: [Date/Time]
- Follow-up needed: [With whom]
```

**Shortcut Commands:**
- "Action item: [task] for [person]" → Auto-adds to action items
- "Decision: [decision]" → Auto-adds to decisions
- "Question: [question]" → Auto-adds to questions

### Post-Meeting (Summary & Follow-up)

After meeting ends, generate smart summary:

```
📊 MEETING SUMMARY

**Meeting:** [Title]
**Duration:** [Actual time]
**Attendees:** [X people present]

---

**🎯 KEY OUTCOMES:**
1. [Most important result]
2. [Second important result]
3. [Third important result]

**✅ DECISIONS MADE:** [Count]
1. [Decision with context]

**🎯 ACTION ITEMS:** [Count]
| Task | Owner | Due Date | Priority |
|------|-------|----------|----------|
| [Task 1] | [Name] | [Date] | High |
| [Task 2] | [Name] | [Date] | Medium |

**❓ FOLLOW-UP NEEDED:**
- [ ] [Item 1]
- [ ] [Item 2]

---

**💾 SAVE OPTIONS:**
1. Save as file → meeting_notes_[date].md
2. Send via email to attendees
3. Add to project documentation
4. Create calendar reminders for action items

What would you like to do?
```

### Action Item Tracking

**Create tracking system:**

```
🎯 ACTION ITEM TRACKER

From meeting: [Meeting name]

**YOUR TASKS:**
1. ⏳ [Task] - Due: [Date] - Status: In Progress
2. ✅ [Task] - Due: [Date] - Status: Completed
3. 🔴 [Task] - Due: [Date] - Status: OVERDUE

**OTHERS' TASKS:**
- [Person]: [Task] - Due: [Date]
- [Person]: [Task] - Due: [Date]

**REMINDERS:**
- I'll remind you about Task 1 tomorrow
- Task 3 is overdue! Want to follow up with [person]?
```

Auto-reminders:
- 1 day before due date
- On due date
- 1 day after if not marked complete

### Follow-up Automation

**Generate follow-up email:**

```
📧 FOLLOW-UP EMAIL DRAFT

To: [Attendees]
Subject: Meeting Summary & Action Items - [Meeting Title]

Hi team,

Thank you for joining today's meeting about [topic]. Here's a quick summary:

**Key Decisions:**
- [Decision 1]
- [Decision 2]

**Action Items:**
- [Person 1]: [Task] by [Date]
- [Person 2]: [Task] by [Date]
- [You]: [Task] by [Date]

**Next Steps:**
[What happens next]

**Next Meeting:**
[Date/Time] - [Agenda preview]

Please let me know if I missed anything or if you have questions!

Best,
[Your name]

---

Want me to send this email?
```

### Meeting Analytics

**Track meeting effectiveness:**

```
📊 MEETING ANALYTICS

**This Month:**
- Total meetings: 24
- Total time: 18 hours (22% of work time)
- Average duration: 45 minutes

**By Type:**
- 1-on-1s: 8 meetings (6 hours)
- Team meetings: 10 meetings (8 hours)
- Client calls: 6 meetings (4 hours)

**Effectiveness Score:** 7/10

**Insights:**
✅ Good:
- Most meetings end on time
- Clear action items defined

⚠️ Needs Improvement:
- 30% of meetings had no clear outcome
- 5 meetings could have been emails
- Average attendance: 65% (some no-shows)

**Recommendations:**
1. Cancel meetings with no agenda
2. Use async updates for status reports
3. Send pre-reads 24h before meeting
```

### Meeting Types - Specialized Templates

#### **1-on-1 Meeting**
```
👥 1-ON-1 NOTES

With: [Person]
Date: [Date]

**Check-in:**
- How are you feeling? (1-10 scale)
- Anything blocking you?

**Work Discussion:**
- [Current projects status]
- [Challenges faced]
- [Support needed]

**Growth & Development:**
- [Skills working on]
- [Career goals]
- [Feedback exchange]

**Action Items:**
- Me: [What I'll do]
- Them: [What they'll do]

**Next 1-on-1:** [Date]
```

#### **Brainstorming Session**
```
💡 BRAINSTORMING SESSION

Topic: [What we're brainstorming]

**Rules:**
1. No idea is bad
2. Quantity over quality (generate many)
3. Build on others' ideas
4. Save criticism for later

**IDEAS GENERATED:** [Count]

**Phase 1 - Generate:**
- Idea 1
- Idea 2
- Idea 3
[Keep listing]

**Phase 2 - Group:**
- Theme A: [Ideas 1, 3, 7]
- Theme B: [Ideas 2, 5]

**Phase 3 - Evaluate:**
| Idea | Feasibility | Impact | Priority |
|------|-------------|--------|----------|
| Idea 1 | High | High | 🔥 Must Do |
| Idea 2 | Low | High | 💡 Explore |

**Next Steps:**
- Prototype: [Idea 1]
- Research: [Idea 2]
```

#### **Retrospective Meeting**
```
🔄 RETROSPECTIVE

Sprint/Period: [Time period]

**What went well? 😊**
- [Thing 1]
- [Thing 2]

**What didn't go well? 😞**
- [Thing 1]
- [Thing 2]

**What should we try? 💡**
- [Experiment 1]
- [Experiment 2]

**Action Items for Next Sprint:**
1. [Improvement to implement]
2. [Process to change]
3. [Tool to try]
```

### Smart Features

**Meeting Conflict Detection:**
```
⚠️ SCHEDULE CONFLICT

You have a meeting at 3 PM, but:
- Another meeting runs until 3:15 PM
- You need 10 minutes travel time

Suggestions:
1. Join new meeting 15 mins late
2. Ask to reschedule one meeting
3. Attend first meeting remotely (save travel time)
```

**Meeting Preparation Automation:**
```
🤖 AUTO-PREP COMPLETE

For meeting: [Title] at [Time]

I've prepared:
✅ Pulled latest project updates
✅ Gathered relevant documents
✅ Listed open questions
✅ Set up screen share
✅ Tested mic/camera

You're ready to go!
```

### Meeting Etiquette Reminders

When appropriate, remind user:
- 🎤 "Reminder: Mute when not speaking"
- 👀 "Keep camera on for better engagement"
- ⏰ "Meeting overrunning by 10 mins, want to wrap up?"
- 📱 "Looks like you're multitasking - stay focused for better participation"
