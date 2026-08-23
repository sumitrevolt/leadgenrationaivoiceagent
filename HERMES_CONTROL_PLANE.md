# HERMES CONTROL PLANE
# Architectural overview of the Hermes orchestration layer for LeadGen AI

## Core Philosophy
Hermes is the **control/orchestration layer** that sits above the 31 specialized AI agents (staff) and coordinates them through 8 department-level bots.
It does NOT replace the existing agents; it gives them purpose, priority, and coordination.

## Structural Hierarchy
```
OWNER ORCHESTRATOR (Boss)
       ↓
┌─────────┴─────────┬─────────┴─────────┬─────────┴─────────┬─────────┴─────────┐
REVENUE/CRO    LEAD INTELLIGENCE  OUTREACH/CONVERSATION   VOICE/SWARA    MARKETING/CONTENT   ENGINEERING/SRE   QA/ANALYTICS/FINANCE   (Department Bots)
       ↓              ↓                  ↓                   ↓              ↓                   ↓                   ↓                     ↓
[Agents]         [Agents]             [Agents]              [Agents]       [Agents]            [Agents]            [Agents]              [Agents]
```
Each department bot owns a subset of the 31 agents (see `HERMES_AGENT_ROSTER.yaml`).

## Key Responsibilities by Layer

### 1. Owner / Orchestrator (Boss)
- Sets business objectives (revenue targets, growth goals)
- Maintains the global priority queue of tasks
- Assigns work to department bots based on impact and urgency
- Resolves conflicts between bots (e.g., revenue vs. compliance)
- Enforces safety policy (compliance gates, kill switches, budget limits)
- Owns the revenue dashboard and approves architecture decisions
- Prevents duplicate work across bots

### 2. Department Bots (8 total)
Each bot owns:
- A clear set of duties (see `HERMES_AGENT_ROSTER.yaml`)
- The agents assigned to it (their duties, schedules, and KPIs)
- A local task queue for its agents
- Escalation paths to the Owner bot
- Ownership of specific revenue funnel stages or operational areas

### 3. Specialized Agents (31 existing agents)
- Perform the actual work (lead discovery, outreach, voice calls, etc.)
- Report status and results to their department bot
- Follow schedules and duties defined in `app/platform/team.py`
- Are NOT modified; their existing capabilities are reused

## Communication & Coordination Mechanisms

### Task Authority System
- Every task has: ID, business outcome, priority, owner bot, assigned agent, status, dependencies, acceptance criteria, evidence.
- Statuses: BACKLOG → READY → RUNNING → BLOCKED → VERIFYING → DONE → FAILED
- Only the Owner bot can create or reprioritize tasks in the global queue.
- Department bots pull tasks from the global queue that match their domain.
- Agents report task completion to their department bot.

### Bot-to-Bot Event System
Each bot publishes standardized events to a shared event bus (Redis-backed):
- **HEARTBEAT**: bot, current task, status, last action, blocker, next action (every 30s)
- **TASK_COMPLETE**: task ID, changes, tests, evidence, deployment status, remaining risks
- **BLOCKER**: task, exact blocker, affected revenue path, attempted fixes, required escalation
The Owner bot continuously maintains the authoritative operational state from these events.

### 24×7 Operation Model
- Scheduler: Celery beat with persistent queues
- Workers: Celery workers with concurrency limits
- Heartbeat: Each bot publishes liveness via the event system
- Watchdog: Monitors heartbeats, restarts stalled workers, reassigns tasks
- Retry policy: Exponential backoff with dead-letter queue
- Circuit breakers: For external providers (Vobiz, WhatsApp, etc.)
- Budget controls: Per-bot and per-channel spend caps
- Kill switches: Immediate halt for dangerous external actions (voice, WhatsApp bulk)

## Integration with Existing Systems
- Uses existing `app/platform/team.py` for agent metadata and event logging
- Uses existing Redis instance for event streaming and task queuing
- Uses existing HTTP endpoints for agent triggering (where available)
- Does NOT modify existing agent code; works through established interfaces
- Leverages existing scheduler jobs (growth, email_outreach, etc.) as agent tasks

## Safety & Compliance
- All external actions (voice, WhatsApp, email) are gated by existing compliance systems (DND fail-closed, TRAI windows, consent ledger)
- Hermes itself does not bypass any compliance gates; it only orchestrates within them
- Budget caps and kill switches are enforced at the orchestrator level
- No agent or bot can execute irreversible actions without explicit Owner approval (where required)

## Implementation Technology
- Built as DeepSeek Harness (Dsh) Cordis plugins for dynamic, hot-reloadable orchestration
- Communicates with existing LeadGen AI system via:
  - HTTP internal APIs (for agent triggering and status)
  - Redis pub/sub (for bot-to-bot events and heartbeats)
  - Direct database reads (for read-only status checks, never writes)
- Plugins are versioned, approvable, and rollbackable via the Dsh system

## Deployment & Operation
- Deployed as a set of Dsh plugins alongside the existing LeadGen AI containers
- Does not require changes to the existing docker-compose.vps.yml
- Runs in the same network as the app, worker, and scheduler containers
- Monitored via the existing health endpoints and new Hermes-specific endpoints
- Can be updated or rolled back without downtime using Dsh's versioning system

## Relation to Agent-OS
The existing agent-os framework (in `agent-os/`) continues to define the 31 agents' identities, duties, and schedules.
Hermes does not replace agent-os; it uses it as the foundation for agent metadata and integrates with its event logging and scheduling systems.
The 8 department bots are new orchestration constructs that sit above the agent-os layer.

## Diagram of Data Flow
```
[Owner Bot] <---> [Event Bus (Redis)] <---> [Department Bot 1] <---> [Agent A]
      ↑                      ↑                         ↑
      │                      │                         │
      │                      │                         │
[Owner Bot] <---> [Event Bus (Redis)] <---> [Department Bot 2] <---> [Agent B]
      ↑                      ↑                         ↑
      │                      │                         │
      │                      │                         │
[Owner Bot] <---> [Event Bus (Redis)] <---> [Department Bot N] <---> [Agent Z]
```
Owner bot communicates with department bots via events; department bots communicate with their agents via existing agent-os mechanisms (task assignment, scheduling, etc.).

## Conclusion
Hermes provides the missing orchestration layer to turn the 31 specialized agents into a coordinated, revenue-focused organization.
It preserves all existing agent capabilities while adding clear ownership, prioritization, and 24×7 operational discipline.
---

## HERMES NEXT DIRECTIVE — 2026-08-23 09:15 IST (from opencode admin loop)

**Money state:** Collected Rs 7,997 / Target Rs 5,00,000 / Gap Rs 4,92,003 / Prod 20ce9552 healthy.
**Armed today:** trial_nudge job 09:50 IST daily (TRIAL_NUDGE_ENABLED=1). EXPECTED first run = sent 0 (koi eligible trial nahi — Fresh Test Biz 42 email-null+active).

### TASKS (no duplicates; evidence-first)
- **HX-01 [P0][Sales/Owner]** Hot Queue 42 warm leads — top-10 ko UPI follow-up OWNER 1-click se AAJ. Surface: /app/inbox (UPI cards PR #430 live). Success = >=2 replies/conversations logged.
- **HX-02 [P0][CS]** Jiya Combo-upsell + Kamal inputs-request drafts READY hain: VPS `data/upsell_drafts_2026-08-23.md`. Owner WhatsApp 1-click send karo. Success = dono tak delivered (WAHA ***2607 WORKING).
- **HX-03 [P1][QA/Automation]** 09:50 ke baad `trial_nudge` run verify: team event log me 'nikhil/trial_nudge' entry; expected sent=0 skipped counts>0. Error ho to full log capture + escalate, FIX MAT KARO bina root cause.
- **HX-04 [P2][Lead Intel]** Trial-funnel bharo: real /start signups pe trial flag + email capture hona chahiye (abhi eligible trials ZERO). Prospecting daily jobs apne caps me chalte rahenge.
- **HX-05 [P3][Engineering]** Backlog only: trial-nudge admin stats tab + Sharma-trials source reconcile (memory/backlog.md).

### OWNER GATES (in wait)
upi_12 approve/reject · Kamal brand-kit colors/tagline + FB/Insta connect · agent-arm rollout decision (30 agents unarmed).

### RULES REMINDER
Cold-WA OFF · email cap 25/day · DND/TRAI gates untouched · koi fake metric nahi — har claim ke saath prod evidence.

---

## HERMES DESKTOP = OWNER ADMIN COCKPIT — WIRED & LIVE (2026-08-23 12:45 IST, ADR-188)

**Status:** LeadGen prod MCP → Hermes Desktop **CONNECTED, 54 tools registered** (gateway log 12:34:33).
Owner ab Hermes GUI **ya Telegram DM** me seedha admin-data maang sakta hai.

**Kya kaam karta hai (proven):**
- ✅ **END-TO-END VERIFIED 13:20 IST:** Hermes one-shot agent ne khud `mcp__leadgen__ops_revenue_summary` call karke live jawab diya — `fy_gross_inr=7996.0, total=16`. Pura chain: LLM → MCP SSE (Bearer JWT) → middleware → require_admin → invoice ledger.
- `ops_revenue_summary` → collected revenue + invoice ledger (REST probe bhi 200)
- `ops_hot_queue` (+ action: done/park) → HX-01 warm leads ka cockpit surface (live: SOUTH interested-inquiry SLA-breach + Nashik solar question + 4x Pune solar call-flag "interested")
- + 51 aur Platform/Data/Agents tools (companies search, company details, etc.)

**Auth model:** FASTAPI_MCP_TOKEN ab valid super_admin service-JWT hai (1825d) — middleware gate +
route-level require_admin dono pass. Owner password-reset = token revoke → re-mint (ADR-188 runbook).

**Rollback:** VPS `.env.bak-mcpgw-20260823_065853` restore + app recreate; Hermes `config.yaml.bak-leadgenmcp-20260823_123327`.

**Owner quick-start (GUI/Telegram me type karo):**
- "revenue summary batao" → collected ₹ + recent invoices
- "hot queue dikhao" → warm leads + next action hint
- "HX tasks" context is file se; evidence-first discipline wahi rahega.

**Observations (pre-existing, alag fix):** Telegram polling conflict-retry loop (~70s, self-heals —
koi doosra getUpdates consumer active lag raha hai) · kanban.db not-writable warnings desktop plugin me.
