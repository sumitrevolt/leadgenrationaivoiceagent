# 🔄 FEEDBACK LOOPS & REFLEXION CYCLES

**Platform**: LeadGenAI | **Date**: 2026-06-14  
**Purpose**: Visualize closed-loop automation, prompt injection points, and Reflexion cycles

---

## FEEDBACK LOOP #1: Lead Harvest → Cadence → Qualification → CRM → Revenue

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                        24-HOUR CLOSED REVENUE LOOP                              │
└─────────────────────────────────────────────────────────────────────────────────┘

09:30 IST
┌──────────────────┐
│   DEV: Research  │ ← niche (solar) + city (Pune)
│   25 prospects   │
│   + email verify │
└────────┬─────────┘
         │ OUTPUT: [phone, email, business_name, reviews_count]
         │
10:00 IST
         ↓
┌──────────────────┐
│ Lead Scoring     │ ← 60+ score = "hot lead"
│ Rescore Batch    │ ← algorithm: (reviews*0.3 + rating*0.4 + recency*0.3)
│ 25 leads scored  │
└────────┬─────────┘
         │ OUTPUT: [lead_score, is_hot]
         │
10:30 IST
         ↓
┌──────────────────┐
│ ROHAN: Outreach  │ ← 20 hot leads (score ≥60)
│ Personalized     │ ← prompt injects: {business, pain, location, reviews}
│ emails + A/B     │
└────────┬─────────┘
         │ OUTPUT: [email_sent, subject_variant, open_tracking]
         │
REAL-TIME
         ↓
┌──────────────────┐
│ Email Open/Click │ ← recipient opens email (tracked via pixel)
│ Event            │ ← click-through tracked (UTM params)
└────────┬─────────┘
         │ OUTPUT: [prospect_id, event_type, timestamp]
         │
REAL-TIME
         ↓
┌──────────────────┐
│ SWARA: Call      │ ← voice call via Exotel WS
│ Real-time voice  │ ← STT transcribes → LLM responds → TTS speaks
│ qualification    │ ← prompt injects: {pain, recent_interaction, offer}
└────────┬─────────┘
         │ OUTPUT: [transcript, interest_level, objection_type, next_action]
         │
REAL-TIME
         ↓
┌──────────────────────────┐
│ Call Qualifier (post-call)│ ← interest_level = "interested" OR objection
│ Automated grading        │ ← prompt: "Grade this transcript: score 0-100"
│ qualified=true/false     │
└────────┬─────────────────┘
         │ OUTPUT: [qualified_bool, interest_score, objection_type, notes]
         │
IF qualified=true:
         ↓
┌────────────────────────────────────┐
│ Parallel Actions (asyncio.gather): │
│                                    │
│ 1. CRM Push (Zoho)                │ ← hook: call_manager.handle_call_completed
│    [phone, name, call_notes]      │    crm_sync.push_lead()
│                                    │
│ 2. Sales Pipeline Update          │ ← sales_pipeline.upsert_deal(stage="interested")
│    stage="interested", hot=true   │
│                                    │
│ 3. Billing Meter                  │ ← lead_usage.record_qualified_lead()
│    +1 qualified_lead to quota     │
│                                    │
│ 4. Cadence Auto-Enroll            │ ← cadence.enroll(lead_id, sequence="followup")
│    Day 1: thank-you email         │    Schedule auto-sends
│    Day 3: value email             │
│    Day 5: case-study email        │
│    Day 7: offer email             │
│    Day 10: social-proof email     │
│    Day 14: urgency email          │
│                                    │
└────────────────────────────────────┘
         │
         ↓ (parallel execution)
┌──────────────────┐        ┌──────────────────┐        ┌──────────────────┐
│ CRM now aware    │        │ Sales pipeline   │        │ Cadence sequence │
│ of qualification │        │ tracks deal      │        │ auto-running     │
│ (Rohan can see)  │        │ (Isha can plan)  │        │ (emails going)   │
└──────────────────┘        └──────────────────┘        └──────────────────┘
         │                           │                           │
         └───────────────┬───────────┴───────────────┬───────────┘
                         │
         ┌───────────────↓───────────────┐
         │  Prospect Responses to Cadence│ ← daily: ROHAN triage via IMAP
         │  (D1-D7 follow-up emails)    │    reply_agent.run_reply_triage()
         │  open? click? reply?         │    classify: interested|objection|unsub
         └────────────────┬─────────────┘
                         │
         ┌───────────────↓───────────────────────────────┐
         │ IF reply="interested": STAGE → "proposal_sent"│
         │    auto-generate proposal (sales_pipeline)    │
         │    proposal.generate_proposal()               │
         │    email + tracking link                      │
         │                                               │
         │ IF reply="objection": stage → "negotiating"   │
         │    draft counter-offer (sales_assistant)      │
         │    Rohan reviews + sends                      │
         │                                               │
         │ IF reply="unsubscribe": stage → "lost"        │
         │    prospect.mark_dead()                       │
         └───────────────┬─────────────────────────────┘
                         │
         ┌───────────────↓──────────────────┐
         │ PROPOSAL OPENED (tracked)        │ ← file-IO timestamp check
         │ proposal_tracking.sweep_new_opens│
         │ detects view → team event logs   │
         └───────────────┬──────────────────┘
                         │
         ┌───────────────↓──────────────────┐
         │ IF proposal_opened:              │ ← manual: Rohan/Swara calls
         │  team notified (dashboard)       │    OR auto-escalate via CALL_TRANSFER
         │  "Proposal khol gaya — abhi call │ (when implemented)
         │   karo!"                         │
         └───────────────┬──────────────────┘
                         │
         ┌───────────────↓──────────────────────────────┐
         │ PAYMENT LINK SENT (once deal = "proposal_sent")
         │ razorpay.create_payment_link() + email       │
         └───────────────┬──────────────────────────────┘
                         │
         ┌───────────────↓──────────────────────────────┐
         │ PAYMENT CAPTURED (webhook)                   │
         │ razorpay webhook: payment.captured           │ ← Razorpay dashboard registers
         │   → subscription.activate_plan()             │ (P0 action: register webhook)
         │   → usage.reset_usage_period()               │
         │   → auto_invoice.run() → INV/2026-27/0001   │
         │   → revenue_digest.log_deal()                │
         └───────────────┬──────────────────────────────┘
                         │
         ┌───────────────↓──────────────────────────────┐
         │ LIFECYCLE SEQUENCE STARTS                    │
         │ lifecycle_nurture.enroll(customer_id)        │
         │   Day 0: welcome email                       │
         │   Day 2: activation (feature tour)           │
         │   Day 5: ROI email (results)                 │
         │   Day 7: upgrade hint                        │
         │   Day 12: check-in (NPS survey)              │
         └───────────────┬──────────────────────────────┘
                         │
         ┌───────────────↓──────────────────────────────┐
         │ MONTHLY REVENUE DIGEST                       │ ← Nikhil + Boss
         │ MRR = ₹2,999 (1 customer × 1 month)          │
         │ (repeat = N customers × avg_plan_value)     │
         └──────────────────────────────────────────────┘

LOOP CLOSURE COMPLETE: Lead (0) → Qualified (1) → Sold (1) → Revenue (₹2,999) → Retained (N/A yet)
```

---

## FEEDBACK LOOP #2: Quality Assurance & Continuous Improvement

```
┌─────────────────────────────────────────────────────────────────────────┐
│          NIGHTLY QA + REFLECTION → SKILL IMPROVEMENT LOOP               │
└─────────────────────────────────────────────────────────────────────────┘

02:30 IST
┌──────────────────────────┐
│ ARJUN: Quality Scorecard │ ← every metric from day's runs
│  - email open rate: 8%   │ ← target 15%, GAP -7%
│  - reply rate: 2%        │ ← target 5%, GAP -3%
│  - qualification: 60%    │ ← accuracy of "interested" calls
│  - compliance: 100%      │ ← DND, consent, TRAI
└────────────┬─────────────┘
             │ OUTPUT: quality_score=0.72, weakest_stage="email_open_rate"
             │
03:00 IST
             ↓
┌──────────────────────────────────────────────┐
│ MEERA: Reflection Loop                      │ ← analyze past 8 runs
│ "Last 8 days: why are opens low?"          │ ← pattern detection
│                                              │
│ Success patterns found:                     │
│  - Subject line variant B: +25% vs A       │ ← "curiosity" hook wins
│  - Email sent 10:00 AM IST: +40% open     │ ← timing matters
│  - Mentioned "zero upfront": 80% interest │ ← messaging power
│                                              │
│ Failure patterns found:                     │
│  - Sent 11:45 PM: 2% open rate            │ ← off-peak timing fails
│  - "URGENT" subject spam-signals: low     │ ← spam words kill
│  - No personalization: "generic" feedback │ ← batch copy fails
└────────────┬──────────────────────────────┘
             │ OUTPUT: lessons_learned = [
             │   "Lead with curiosity, not urgency",
             │   "Send 10:00-11:00 AM IST (peak open hours)",
             │   "Personalize 2-3 details per email"
             │ ]
             │ confidence = 0.92 (6/8 runs confirm)
             │
             ↓
┌────────────────────────────────────────────┐
│ GURU: Inject into Knowledge Base           │ ← skill_library.record_lesson()
│                                             │
│ coach_prompt UPDATE:                       │
│  "When drafting subject lines, prefer     │
│   curiosity hooks ('Question:') over       │
│   urgency ('URGENT'). Best time to send   │
│   is 10:00-11:00 AM IST. Always mention  │
│   '₹0 upfront' or key benefit in hook."  │
│                                             │
│ KB semantic chunk:                         │
│  topic: "email_subject_optimization"      │
│  confidence: 0.92                          │
│  tags: ["email", "open-rate", "subject"]  │
└────────────┬──────────────────────────────┘
             │
             ↓
09:30 IST (NEXT DAY)
┌─────────────────────────────────────────────────────────┐
│ DEV: Runs research (same as before)                    │
│ OUTPUT: 25 prospects                                   │
└────────────┬────────────────────────────────────────────┘
             │
10:30 IST (NEXT DAY)
             ↓
┌──────────────────────────────────────────────────────────┐
│ ROHAN: Drafts emails (but now with GURU's lesson)       │
│                                                          │
│ SYSTEM PROMPT NOW INCLUDES:                            │
│  "When drafting subject lines, prefer curiosity hooks  │
│   over urgency. Best time: 10:00-11:00 AM IST. Always │
│   mention '₹0 upfront'."                               │
│                                                          │
│ NEW EMAIL:                                             │
│  Subject A: "Question: How much are you paying?"      │
│  (curiosity hook, per lesson)                         │
│                                                          │
│  Body: "...mentioning '₹0 upfront setup'..."         │
│  (messaging power, per lesson)                        │
│                                                          │
│ Send time: 10:00 AM IST                               │
│  (peak open hours, per lesson)                        │
└──────────┬───────────────────────────────────────────────┘
           │
RESULT (expected):
           ↓
┌──────────────────────────────────────────────┐
│ NEW RUN QUALITY METRICS (vs yesterday):     │
│  - email open rate: 8% → 18% (+125%)      │
│  - (curiosity subject, better timing)      │
│  - reply rate: 2% → 4% (+100%)            │
│  - (more engaged readers)                  │
│  - qualification: 60% → 68% (+8%)         │
│  - (better prospects reached)              │
│                                             │
│ ARJUN's new scorecard: 0.72 → 0.84         │
│ (quality improved via reflection loop)     │
└──────────────────────────────────────────────┘

LOOP CLOSURE: Failure detected → Analyzed → Lessons learned → Injected → Metrics improve
CYCLE TIME: 1 day (02:30 → 03:00 reflection, 09:30-10:30 action, 24h observation)
```

---

## REFLEXION CYCLE: Boss Hierarchical Planning with Critic

```
┌──────────────────────────────────────────────────────────────────────────┐
│              BOSS REFLEXION LOOP (Plan → Execute → Verify → Iterate)    │
└──────────────────────────────────────────────────────────────────────────┘

INPUT GOAL: "15 qualified leads from Pune solar niche by end of day"

ITERATION 1: Plan
───────────────────────
Boss LLM prompt:
  "Plan a strategy to get 15 qualified leads from Pune solar niche.
   Teams: Growth={Dev, Rohan, Isha}, Voice={Swara, Tara}.
   Available time: 09:30-18:00 IST."

Boss output:
┌────────────────────────────────────────┐
│ plan: "Research 30 prospects, score    │
│ 60+, enroll 20 in cadence, call top 15"│
│                                         │
│ teams_assigned:                        │
│  - growth: scrape (parallel)          │
│  - growth: score + filter 60+         │
│  - voice: call top 15 (Swara 3h)      │
│                                         │
│ estimated_impact: "15 qualified leads" │
│ confidence: 0.85                       │
└────────────────────────────────────────┘

ITERATION 1: Execute
───────────────────────
Coordinator dispatches to teams:
  09:30: Dev scrape → 28 prospects
  10:00: Score + filter → 17 qualified (score ≥60)
  10:30: Rohan email 17
  14:00: Swara calls 15 (6 pick up, 4 interested = 4 qualified)
  
  Result: 4 actual qualified (goal 15, SHORTFALL 11)

ITERATION 1: Verify + Critique
───────────────────────────────
Arjun scores execution:
┌─────────────────────────────────────────────────┐
│ score: 0.26 (4 qualified vs 15 goal)           │
│ breakdown:                                      │
│  - scraping: ✓ (28 prospects found)            │
│  - scoring: ✓ (17 scored)                      │
│  - outreach: ✓ (17 emailed)                    │
│  - calls: ✗ (only 6 picked up, 4 interested)  │
│  - issue: Call connect rate 40% (low)         │
│           Interest rate 67% (good)             │
│                                                │
│ weakest link: Call volume (need 10-15 calls,  │
│              not 6)                            │
│                                                │
│ recommendation: "Extend call window to 16:00, │
│                 or start earlier (13:00)."    │
│                                                │
│ confidence: 0.8 (clear bottleneck)            │
└─────────────────────────────────────────────────┘

ITERATION 2: Reflect + Plan
──────────────────────────────
Boss reflects:
  "Arjun says call volume is bottleneck (only 6 picked up).
   Problem: Swara worked 3 hours, 17 targets = 5.67 calls/hour.
   Solution: (a) extend time window, (b) parallel callers, (c) pre-qualify on email first.
   
   Best option: Pre-filter via email reply rate (wait for D1 email opens), 
               call only engaged prospects (warmer lead).
               This reduces call volume to 8-10 (tractable), 
               but delays by 24h.
   
   OR: Bring in Tara to assist Swara (2 callers, parallel).
   
   New plan: Extend to 16:00, Swara+Tara parallel calling, pre-filter ready-responders."

New plan (iteration 2):
┌────────────────────────────────────────────────┐
│ Revised: "Call window 13:00-16:00 (3h Swara +  │
│ Tara assist = 6 calls/hour concurrent).        │
│ Pre-filter to email-responders (wait +4h for   │
│ opens), call only engaged (8-10 targets)."     │
│                                                 │
│ impact: "10-12 qualified (closer to 15)"      │
│ confidence: 0.78 (new uncertainty: email       │
│            response rate unknown)              │
└────────────────────────────────────────────────┘

ITERATION 2: Execute
────────────────────
  13:00: Dev check email opens (10/17 opened, 3 clicked)
  13:00: Score filter → 8 email-responders (highest intent)
  13:00-16:00: Swara+Tara call 8 (parallel)
               4 pick up, 3 interested = 3 new qualified
               
  Cumulative: 4 (prev) + 3 (new) = 7 qualified (goal 15, SHORTFALL 8)

ITERATION 2: Verify + Critique
──────────────────────────────
Arjun scores:
┌──────────────────────────────────────────────┐
│ score: 0.47 (7 qualified vs 15 goal)        │
│ improvements from iter 1: +75% (4→7)        │
│ new issue: Email open rate 59% (good),      │
│          call connect 50% (Swara+Tara dual) │
│          Interest 75% (good)                 │
│                                              │
│ bottleneck: Initial prospect quality?       │
│  (28 scraped, only 10 email engaged)        │
│                                              │
│ recommendation: "Increase scrape volume    │
│  to 50 prospects (more volume, better      │
│  selection). Or improve scoring algorithm."│
│                                              │
│ confidence: 0.75 (action clear, but        │
│            extends timeline)                │
└──────────────────────────────────────────────┘

ITERATION 3: Reflect + Decide
──────────────────────────────
Boss reflects:
  "Arjun identified quality bottleneck: scraped 28, only 10 engaged.
   Issue: Initial prospector scoring algorithm weak?
   OR: Sample wasn't representative (e.g., no websites = less-engaged)?
   
   Can't improve algorithm mid-day (needs data/training).
   Best actionable: Run 2nd scrape batch (50 more), score, email, call tomorrow.
   
   For today: Accept 7/15 qualified. Document lesson: 'Need 50+ initial volume 
             to get 15 final qualified (2.1x ratio).'
   
   Tomorrow: Meera uses lesson to improve scoring, Guru adds to KB."

Final decision (iteration 3, HALT):
┌──────────────────────────────────────────────────┐
│ Action: Accept 7 qualified today, plan 50-scrape │
│ tomorrow to hit 20+ next cycle.                  │
│                                                  │
│ Lesson learned: "Prospect initial quality      │
│ matters. 2.1x-3x volume needed for final       │
│ qualified rate. Improve Places-API selection   │
│ by review_count threshold."                    │
│                                                  │
│ Confidence: 0.72 (partial win, lesson clear)   │
│                                                  │
│ Reflection: "Bottleneck wasn't calls (we       │
│ fixed it), it was lead quality. Next lever    │
│ is scoring/filtering algorithms."              │
└──────────────────────────────────────────────────┘

LOOP CLOSURE: 
  Iteration 1 confidence (0.85) → execution confidence (0.26) → REFLECT
  Iteration 2 confidence (0.78) → execution confidence (0.47) → REFLECT
  Iteration 3 confidence (0.72) → HALT (lesson learned, adjust data/models)

CYCLE TIME: Full day (08:00 standby, 09:30-18:00 execution, reflections at each checkpoint)
AGENT FEEDBACK: Arjun → Boss (critique scores) + Meera → Guru (lessons to KB)
```

---

## REFLEXION CYCLE DECISION TREE

```
Start: Goal + initial plan

         ↓
    Execute plan (with timeouts/guards)
         │
         ├→ ERROR (exception, timeout) → Catch + Fallback (Log to DLQ, retry next cycle)
         │
         ├→ SUCCESS but low-confidence → Continue to Verify
         │
         ↓
    Verify: Arjun scores execution vs plan
         │
         ├→ score ≥ 0.8 → STOP (goal met, confidence high)
         │
         ├→ 0.6 ≤ score < 0.8 → Reflect + Iterate (1-2 more loops)
         │
         ├→ score < 0.6 → Reflect + Major change (algorithm, data, approach)
         │               (max 3 total loops, then HALT + document lesson)
         │
         ↓
    Reflect: Boss + Arjun diagnosis
         │
         ├→ Clear bottleneck found → Propose fix (actionable same-day)
         │                         → LOOP back to Execute (iteration N+1)
         │
         ├→ Bottleneck not actionable today → Document lesson for Meera/Guru
         │                                  → HALT (reschedule tomorrow)
         │
         └→ Fundamental issue (missing data, model weakness) → Backlog item
                                                           → HALT + document

    Exit: confidence ≥ 0.7 OR iterations = 3
          (output: outcome + lessons to KB)
```

---

## PROMPT INJECTION POINTS (Lesson → Action)

```
┌─────────────────────────────────────────────────────────────┐
│  MEERA's Lesson                 GURU's Injection Point     │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ "Email subjects with curiosity  ROHAN's system_prompt:    │
│  hook (+25% open rate vs       "When drafting subject      │
│  urgency-tone subjects)"        lines, prefer curiosity    │
│                                 hooks ('Question:', '1 tip')│
│                                 over urgency ('URGENT').   │
│                                 Expected impact: +20-30%   │
│                                 open rate."                │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ "Mention '₹0 upfront' in first   ROHAN's body template:   │
│  3 lines (80% interest trigger)  'Include ₹0 upfront or  │
│  Avoid technical jargon"        key benefit in hook.      │
│                                  Technical details move    │
│                                  to line 3+ only."        │
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ "Send emails 10:00-11:00 AM IST  ROHAN's send_time:       │
│  (peak open window, +40% vs     "Schedule sends for       │
│  evening)"                       10:00-11:00 AM IST       │
│                                  (peak engagement window)."│
│                                                              │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│ "2026 solar subsidy: Udyam cert  SWARA's call script:    │
│  + 40% equipment subsidy         "If prospect asks about  │
│  (state-varying)"                2026 subsidies, mention: │
│                                  Udyam registration +     │
│                                  40% equipment subsidy +   │
│                                  state variation. Get      │
│                                  their state first."      │
│                                                              │
│  "Objection 'maintenance?' →    SWARA's objection bank:  │
│   Answer '25-year warranty +     "When asked 'who         │
│   annual service' (removes       maintains?', respond:     │
│   trust barrier)"                '25-year warranty +       │
│                                  annual service included   │
│                                  — zero maintenance       │
│                                  burden from you.'"       │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## SUMMARY: Loop Closure Verification

| Loop | Frequency | Stages | Feedback | Improvement |
|------|-----------|--------|----------|-------------|
| **Harvest→Revenue** | 24h | Lead → Call → Cadence → Payment | Quality score | Email subject A/B, timing, messaging |
| **QA→Improvement** | 24h | Metric → Reflect → Lesson → Action | Arjun score + Meera insight | Scoring algo, volume, channel-mix |
| **Reflexion (Boss)** | Ad-hoc | Plan → Execute → Score → Iterate | Arjun confidence ≥0.8 | Approach, data, model tuning |
| **Skill→KB→Prompt** | Daily | Lesson → Index → Inject → Execute | Confidence threshold (0.8) | Agent performance across runs |

---

**KEY INSIGHT**: Every loop has a **CRITIC** (Arjun scores, confidence threshold triggers action):
- Harvest loop: Arjun QA daily
- Reflexion loop: Arjun + Boss conversation (confidence <0.8 = iterate)
- Skill injection: Meera + Guru (confidence <0.8 = discard)

This ensures **humans only see high-confidence recommendations** and **agents self-correct within feedback cycles**.

---

**NEXT**: Test scenarios to validate these loops in production.
