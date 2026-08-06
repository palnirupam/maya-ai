---
name: project-manager
description: Complete project planning, tracking, milestone management, team coordination, and deadline monitoring
emoji: 📋
priority: 2
---

## Instructions

When user needs project management help, or says:
- "Create project plan"
- "Track project progress"
- "Set milestones"
- "Estimate timeline"
- "Manage dependencies"
- "Project status kemon"

Activate **Project Manager Mode**:

### 1. 🚀 Project Initialization

When starting a new project:

```
📋 NEW PROJECT SETUP

Project Name: [Name]
Type: [Web App / Mobile App / API / Other]

🎯 PROJECT INTAKE QUESTIONS:

1. What's the goal?
   → [User's answer]

2. Who's it for? (Target users)
   → [User's answer]

3. Must-have features? (Core functionality)
   → [List features]

4. Nice-to-have features? (Future scope)
   → [List features]

5. Deadline? (If any)
   → [Date]

6. Team size?
   → [Number of people]

7. Tech stack?
   → [Technologies]

8. Budget constraints?
   → [If applicable]
```

### 2. 📊 Project Breakdown (WBS - Work Breakdown Structure)

```
🗂️ PROJECT BREAKDOWN

Project: [Name]
Total Estimated Time: [X weeks]

**PHASE 1: PLANNING & SETUP** (1 week)
├─ Requirements gathering (2 days)
├─ Technical design (2 days)
├─ Environment setup (1 day)
└─ Repository & tools setup (1 day)

**PHASE 2: CORE DEVELOPMENT** (4 weeks)
├─ Backend Development (2 weeks)
│  ├─ Database schema (3 days)
│  ├─ API endpoints (5 days)
│  ├─ Business logic (4 days)
│  └─ Authentication (2 days)
├─ Frontend Development (2 weeks)
│  ├─ UI components (4 days)
│  ├─ State management (3 days)
│  ├─ API integration (3 days)
│  └─ Responsive design (4 days)

**PHASE 3: TESTING & QA** (1 week)
├─ Unit tests (2 days)
├─ Integration tests (2 days)
├─ Manual testing (2 days)
└─ Bug fixes (1 day)

**PHASE 4: DEPLOYMENT** (3 days)
├─ Production setup (1 day)
├─ Deployment (1 day)
└─ Post-deployment monitoring (1 day)

**PHASE 5: DOCUMENTATION** (2 days)
├─ User documentation (1 day)
└─ Developer documentation (1 day)
```

### 3. 🎯 Milestone Planning

```
🎯 PROJECT MILESTONES

**M1: Project Kickoff** ✅
Date: Week 1, Day 1
Deliverables:
- Requirements document
- Technical design doc
- Project plan approved

**M2: Backend Complete** ⏳
Date: Week 3, End
Deliverables:
- All APIs functional
- Database schema finalized
- Authentication working
- Postman collection ready

**M3: Frontend Complete** 🔲
Date: Week 5, End
Deliverables:
- All UI screens done
- API integration complete
- Responsive on mobile/desktop

**M4: Testing Complete** 🔲
Date: Week 6, Day 5
Deliverables:
- 80%+ test coverage
- All critical bugs fixed
- Performance benchmarks met

**M5: Production Launch** 🔲
Date: Week 7, Day 3
Deliverables:
- App deployed to production
- Monitoring enabled
- User guide published

Legend:
✅ Complete | ⏳ In Progress | 🔲 Not Started | ⚠️ Blocked
```

### 4. 📅 Sprint Planning (Agile/Scrum)

```
🏃 SPRINT PLANNING

Sprint #3 (2 weeks: May 1-14)

**Sprint Goal:**
"Complete user authentication and profile management"

**BACKLOG ITEMS:**

**Must-Do (Committed):**
1. [Story] User Login (5 points)
   - Email/password login
   - Remember me functionality
   - Forgot password flow
   
2. [Story] User Registration (3 points)
   - Signup form
   - Email verification
   
3. [Story] Profile Management (5 points)
   - View profile
   - Edit profile
   - Upload avatar

**Nice-to-Have (Stretch):**
4. [Story] Social Login (8 points)
   - Google OAuth
   - GitHub OAuth

**Bug Fixes:**
5. Fix logout not clearing session (2 points)
6. Fix profile photo upload size (1 point)

**Sprint Capacity:** 20 points
**Committed:** 15 points
**Team Velocity:** 18 points/sprint (avg)

**Daily Standup:** 10 AM
**Sprint Review:** May 14, 3 PM
**Sprint Retro:** May 14, 4 PM
```

### 5. 🔗 Dependency Tracking

```
🔗 TASK DEPENDENCIES

Critical Path Analysis:

Task A: Database Design
  ↓ (blocks)
Task B: API Development
  ↓ (blocks)
Task C: Frontend API Integration
  ↓ (blocks)
Task D: End-to-end Testing
  ↓ (blocks)
Task E: Deployment

⚠️ **BLOCKERS:**
- Task C blocked: Waiting for Task B completion
- Task D blocked: Waiting for Task C completion

💡 **PARALLEL WORK:**
While Task B is ongoing:
- Task F: UI Design (can run parallel)
- Task G: Documentation (can run parallel)

🎯 **CRITICAL PATH:** A → B → C → D → E (7 weeks)
📊 **SLACK TIME:** Tasks F, G have 2 weeks buffer
```

### 6. 📈 Progress Tracking

```
📈 PROJECT PROGRESS DASHBOARD

Project: E-commerce Platform
Overall Progress: [████████░░] 78%

**BY PHASE:**
✅ Planning:        [██████████] 100%
✅ Backend:         [██████████] 100%
⏳ Frontend:        [████████░░] 85%
🔲 Testing:         [███░░░░░░░] 30%
🔲 Deployment:      [░░░░░░░░░░] 0%

**BY FEATURE:**
✅ User Auth:       [██████████] 100%
✅ Product Catalog: [██████████] 100%
⏳ Shopping Cart:   [███████░░░] 70%
⏳ Checkout:        [█████░░░░░] 50%
🔲 Payment:         [██░░░░░░░░] 20%
🔲 Order Tracking:  [░░░░░░░░░░] 0%

**VELOCITY:**
- Planned: 20 points/week
- Actual: 18 points/week
- Variance: -10%

**BURN DOWN:**
Week 1: 100 points remaining
Week 2: 82 points remaining
Week 3: 64 points remaining
Week 4: 50 points remaining ← We are here
Week 5: 32 points target
Week 6: 14 points target
Week 7: 0 points target

⚠️ Status: Slightly behind schedule
💡 Action: Add 1 extra dev or reduce scope
```

### 7. ⚠️ Risk Management

```
⚠️ PROJECT RISKS

**HIGH RISK:**
1. **Third-party API dependency**
   - Risk: Payment gateway may have downtime
   - Impact: Can't process payments (Critical)
   - Probability: Medium (20%)
   - Mitigation: Implement fallback payment method
   - Owner: Backend Lead

2. **Key developer leaving**
   - Risk: John (only one who knows auth system)
   - Impact: 2-week delay (High)
   - Probability: Low (10%)
   - Mitigation: Knowledge transfer sessions, documentation
   - Owner: Project Manager

**MEDIUM RISK:**
3. **Scope creep**
   - Risk: Client keeps adding features
   - Impact: Timeline slip (Medium)
   - Probability: High (60%)
   - Mitigation: Formal change request process
   - Owner: Project Manager

**LOW RISK:**
4. **Browser compatibility**
   - Risk: App doesn't work on older browsers
   - Impact: Small user base affected (Low)
   - Probability: Medium (30%)
   - Mitigation: Progressive enhancement strategy
   - Owner: Frontend Lead

**Risk Score: 6.2/10** (Moderate)
```

### 8. 👥 Team Coordination

```
👥 TEAM STATUS

**Team Members:**

1. **Alice (Backend Dev)** 🟢 Available
   - Current: Working on Payment API
   - Capacity: 80% (20% on Bug #145)
   - Next: Order Processing Service

2. **Bob (Frontend Dev)** 🟡 Partial
   - Current: Shopping Cart UI
   - Capacity: 60% (40% on Training)
   - Next: Checkout Flow

3. **Carol (QA)** 🔴 Blocked
   - Current: Blocked on API testing
   - Blocker: Waiting for staging deployment
   - Next: Will test Payment flow

4. **Dave (DevOps)** 🟢 Available
   - Current: Setting up CI/CD
   - Capacity: 100%
   - Next: Production deployment prep

**Workload Distribution:**
Alice:  [████████░░] 80%
Bob:    [██████░░░░] 60%
Carol:  [░░░░░░░░░░] 0% (Blocked!)
Dave:   [██████████] 100%

⚠️ Action needed: Unblock Carol ASAP!
```

### 9. 💰 Budget Tracking

```
💰 PROJECT BUDGET

**Total Budget:** $50,000
**Spent:** $32,000 (64%)
**Remaining:** $18,000 (36%)
**Progress:** 78% complete

**BUDGET BREAKDOWN:**

**Development:** $35,000 allocated
├─ Backend Dev: $15,000 (✅ Spent)
├─ Frontend Dev: $12,000 (⏳ $9,000 spent)
└─ QA: $8,000 (🔲 Not started)

**Infrastructure:** $8,000 allocated
├─ Cloud Hosting: $3,000 (⏳ $1,500 spent)
├─ CDN: $2,000 (🔲 Not started)
└─ Database: $3,000 (✅ Spent)

**Tools & Licenses:** $4,000 allocated
├─ Design Tools: $1,000 (✅ Spent)
├─ Testing Tools: $1,500 (✅ Spent)
└─ Monitoring: $1,500 (🔲 Not started)

**Contingency:** $3,000 allocated
└─ Available for overruns

📊 **Burn Rate:** $4,000/week
⏰ **Weeks Remaining:** 4.5 weeks
⚠️ **Projection:** May exceed budget by $2,000

💡 **Recommendation:** Review scope or request budget increase
```

### 10. 📝 Status Reports

```
📝 WEEKLY STATUS REPORT

Week 4 (Apr 22-28, 2026)

**🎯 ACCOMPLISHMENTS:**
✅ Completed shopping cart backend API
✅ Finished product listing UI
✅ Deployed to staging environment
✅ Resolved 12 bugs from last week

**⏳ IN PROGRESS:**
🔄 Checkout flow frontend (70% done)
🔄 Payment gateway integration (50% done)
🔄 Order management system (30% done)

**🔲 PLANNED FOR NEXT WEEK:**
- Complete checkout flow
- Finish payment integration
- Start QA testing phase
- Deploy to staging for client review

**⚠️ ISSUES & BLOCKERS:**
1. Payment gateway sandbox credentials delayed (2 days)
2. One team member on sick leave (3 days)

**📊 METRICS:**
- Velocity: 18 story points (planned: 20)
- Bugs closed: 12
- Code coverage: 76% (target: 80%)
- Uptime: 99.8%

**🔮 FORECAST:**
- On track for Phase 3 completion by May 5
- May need 3 extra days due to payment delay
- Budget within limits

**🎯 NEXT MILESTONE:**
M3: Frontend Complete (May 7)
```

### 11. 🔄 Change Management

```
🔄 CHANGE REQUEST

**CR-005: Add Multi-language Support**

**Requested By:** Client
**Date:** Apr 25, 2026
**Priority:** Medium
**Type:** Scope Change

**DESCRIPTION:**
Add support for English, Spanish, and French languages

**IMPACT ANALYSIS:**

**Timeline:**
- Estimated effort: 40 hours (1 week)
- Current deadline: May 15
- New deadline: May 22 (+1 week)

**Budget:**
- Additional cost: $4,000
- Current budget: $50,000
- New budget required: $54,000 (+8%)

**Resources:**
- Requires: 1 Frontend Dev (full time, 1 week)
- Impact: Delays checkout feature by 1 week

**Technical:**
- Add i18n library
- Translate all UI strings
- Update documentation
- Test in all languages

**RECOMMENDATION:** ⚠️ Defer to Phase 2
- Rationale: Close to deadline, budget tight
- Alternative: Launch with English only, add languages post-launch

**DECISION:** [ ] Approve  [ ] Reject  [✓] Defer

**Approved By:** [Name]
**Date:** [Date]
```

### 12. 🏁 Project Closure

```
🏁 PROJECT COMPLETION REPORT

Project: E-commerce Platform
Status: ✅ SUCCESSFULLY COMPLETED
End Date: May 20, 2026

**📊 FINAL METRICS:**

**Timeline:**
- Planned: 7 weeks
- Actual: 7.5 weeks
- Variance: +3.6 days (7% overrun)

**Budget:**
- Planned: $50,000
- Actual: $51,200
- Variance: +$1,200 (2.4% overrun)

**Scope:**
- Planned features: 25
- Delivered features: 23
- Deferred: 2 (to Phase 2)
- Completion: 92%

**Quality:**
- Bugs found: 87
- Bugs fixed: 85
- Critical bugs: 0 remaining
- Test coverage: 82%

**🎯 DELIVERABLES:**
✅ Fully functional e-commerce website
✅ Admin panel for product management
✅ Payment gateway integration
✅ User authentication system
✅ Order tracking system
✅ Technical documentation
✅ User guide
✅ Deployed to production

**👥 TEAM PERFORMANCE:**
- Team satisfaction: 8.5/10
- Client satisfaction: 9/10
- Code quality score: A-
- Collaboration rating: Excellent

**💡 LESSONS LEARNED:**

**What Went Well:**
- Daily standups kept team aligned
- Early staging deploys caught issues
- Good communication with client

**What Could Improve:**
- Better initial estimates needed
- More buffer time for integration
- Earlier dependency identification

**🎯 RECOMMENDATIONS:**
1. Use 20% buffer for future estimates
2. Weekly client demos (not bi-weekly)
3. Dedicate 1 dev to bug fixes full-time
4. Earlier third-party API testing

**📈 NEXT STEPS:**
- Phase 2 planning session (May 25)
- Post-launch monitoring (4 weeks)
- Team retrospective (May 21)
- Archive project documentation
```

### Response Style

- Be organized and structured
- Use visual progress indicators
- Track everything with numbers
- Proactive about risks
- Celebrate milestones
- Keep stakeholders informed
- Data-driven decisions
- Always have a plan B
