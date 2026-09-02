> Verbatim deep-dives on the 4 execution loops (self-improve / coordinator / process-engine / chatbot-manual): best-for, pros, cons, cost, triggers. See SKILL.md for the decision tree.

## Pattern 1: Self-Improve Loop

**Location**: `app/agents/self_improve.py`

**Best for**:
- Daily recurring tasks (scrape leads, send emails, generate content, run QA)
- Tasks with measurable outcomes (leads found, emails sent, quality score)
- Hands-off optimization (pick task daily, learn from results)

**Example goals**:
- "Keep scraping Pune solar prospects daily"
- "Auto-send cold-emails daily (with cadence + reply-tracking)"
- "Generate weekly blog posts and schedule them"
- "Monitor system health hourly and alert on degradation"

**Pros**:
- Fully automated (180s cycle, runs 24/7)
- Learns daily (bandit picks best task)
- No cost cap (but quota-limited)
- Self-healing (dead-man restarts)

**Cons**:
- Slow (180s per cycle = max 480 tasks/day)
- Requires stable task definitions
- Outcomes must be measurable
- Can't handle one-off goals well

**Cost**: ~$20-50/day (LLM calls + API quota)

**Trigger**:
```bash
# Enable in .env
SELF_IMPROVE_LOOP=1

# Monitor
python scripts/selfimprove_audit.py --last-run
python scripts/selfimprove_audit.py --skill-stats
```

**When NOT to use**:
- You need instant action (loop is slow)
- Task success is hard to measure
- Regulatory/compliance-critical (use process-engine)

---

## Pattern 2: Coordinator

**Location**: `app/agents/coordinator.py`

**Best for**:
- NOW goals (1-3 min execution, immediate result)
- Multi-step strategies (research + plan + draft)
- Specific, one-off tasks
- Quality-critical decisions (use advanced mode)

**Example goals**:
- "Research Pune solar market + draft outreach plan" (1 min)
- "Compare 3 competitors + recommend positioning" (2 min)
- "Design 30-day growth strategy with quality bar" (3 min)
- "Analyze churn patterns + propose 5 solutions" (2 min)

**Pros**:
- Fast (1-3 min)
- On-demand (whenever you need)
- 4 modes (sequential, parallel, hierarchical, advanced)
- Quality-gated (advanced mode loops for quality)
- Learning (episodic memory via reflection)

**Cons**:
- Manual initiation (no automation)
- Cost per run ($1-4)
- Better for strategy than automation

**Cost**: ~$1-4 per run (LLM calls)

**Trigger**:
```bash
# Sequential (default)
curl -X POST http://localhost:8000/api/agents/coordinate \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"goal": "Your goal here"}'

# Advanced (with quality gate + learning)
curl -X POST http://localhost:8000/api/agents/coordinate-advanced \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{
    "goal": "Your goal here",
    "quality_bar": 0.8,
    "max_iterations": 3
  }'
```

**When to use**:
- You need immediate output
- Hands-on decision (want to review + approve)
- One-time or ad-hoc goal
- Strategic planning

**When NOT to use**:
- Daily recurring task (use self-improve)
- Compliance workflow (use process-engine)
- Need to scale to thousands of items (too slow)

---

## Pattern 3: Process-Engine

**Location**: `app/agents/process_engine.py`

**Best for**:
- Deterministic workflows (explicit ordered steps)
- Human approval gates (no auto-execution)
- Repeatable processes (lead_campaign, client_onboard)
- Compliance/audit-critical tasks

**Example goals**:
- Lead campaign: harvest → score → **BREAKPOINT** (human OK?) → cadence enroll
- Client onboarding: add → KB seed → setup → **BREAKPOINT** → activate
- Invoice generation: collect → calculate → **BREAKPOINT** → send
- Audit: scan code → find issues → **BREAKPOINT** (human decide) → fix

**Pros**:
- Explicit steps (code-as-workflow, deterministic)
- Human breakpoints (no auto-execution)
- Event-sourced journal (replay, audit trail)
- Crash-safe (resume from breakpoint)
- Repeatable (same workflow every time)

**Cons**:
- Manual authoring (code steps)
- Slower than coordinator (approval waits)
- More verbose (explicit every step)

**Cost**: $0.5-2 per run (LLM calls only for decisions, not execution)

**Trigger**:
```bash
# Start process
curl -X POST http://localhost:8000/api/growth/process/start \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"process_id": "lead_campaign", "context": {...}}'

# At breakpoint: approve
curl -X POST http://localhost:8000/api/growth/process/run/{run_id}/approve \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{}'

# Or reject
curl -X POST http://localhost:8000/api/growth/process/run/{run_id}/reject \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -d '{"reason": "Too many duplicates"}'
```

**When to use**:
- Need explicit audit trail (compliance, regulatory)
- Human must approve at key steps
- Repeatable workflow (run weekly/monthly)
- Risk-mitigation critical

**When NOT to use**:
- Need speed (approval adds latency)
- One-off task (overkill)
- Fully automatable (use self-improve)

---

## Pattern 4: Chatbot / Manual

**Best for**:
- Interactive conversations (sales calls, customer support)
- Custom one-offs (human judgment needed)
- Real-time decisions (can't wait for workflow)

**Example goals**:
- "Call prospect and qualify interest" (human dials, AI co-pilot)
- "Customer asks about features" (live chat, AI suggests answers)
- "I need a custom report" (manually request, AI assists)

**Pros**:
- Human in control (low risk)
- Real-time feedback
- Handles edge cases (no rigid workflow)

**Cons**:
- Manual labor (doesn't scale)
- Slow (human throughput)

**Trigger**:
- Human manually initiates (phone call, chat, custom request)
- AI assists but human decides

**When to use**:
- Prospect conversation (live sales)
- Customer support
- Custom one-off requests
