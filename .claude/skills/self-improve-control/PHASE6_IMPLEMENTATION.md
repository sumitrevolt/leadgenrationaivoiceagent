# Phase 6: Safety Gates for Self-Improve Loop
## Implementation: Cost Tracking + Approval UI

**Date**: 2026-06-14  
**Status**: COMPLETE  
**Scope**: Cost transparency + human approval gates for self-improve loop

---

## Overview

Phase 6 adds two critical safety layers to the self-improve continuous loop:

1. **Cost Tracking** — daily budget cap ($) + per-action cost logging
2. **Approval Queue** — human approval gates for LLM-heavy actions (gated `SELF_IMPROVE_APPROVAL`)

Together, they prevent uncontrolled LLM spending and give admins control over high-risk autonomous actions.

---

## Architecture

### Backend (Python)

#### `app/agents/self_improve.py` — Core classes

**`CostTracker` class**
```python
class CostTracker:
    """Daily cost cap + per-task tracking."""
    def __init__(self, daily_cap: float = 50.0)
    def can_afford(self, task_name: str, estimated_cost: float) -> bool
    def record_cost(self, task_name: str, actual_cost: float) -> None
    def get_daily_status(self) -> dict
    def _reset_if_new_day(self) -> None
```

- Tracks daily LLM cost (estimated by action type: LLM-heavy=$2.5, light=$0.5)
- Resets at UTC midnight
- Blocks tasks exceeding daily budget
- Logs per-task cost to `/data/self_improve_runs.jsonl`

**`ApprovalQueue` class**
```python
class ApprovalQueue:
    """Human approval gates for high-risk actions."""
    def __init__(self, approval_required: bool = False)
    def queue_task(self, task_name: str, reason: str, cost_estimate: float) -> bool
    def get_pending(self) -> list
    def approve(self, task_id: str) -> bool
    def reject(self, task_id: str, reason: str = "") -> bool
    def is_approved(self, task_id: str) -> bool
```

- Queues LLM-heavy actions when `SELF_IMPROVE_APPROVAL=1`
- Returns `False` if approval needed (loop waits), `True` if auto-approved
- Logs approval/rejection to `/data/self_improve_approvals.jsonl`
- Audit trail: who approved, when, for what reason

**Global instances** (persist across `run_once()` calls)
```python
_cost_tracker: CostTracker | None = None
_approval_queue: ApprovalQueue | None = None

def _get_cost_tracker() -> CostTracker
def _get_approval_queue() -> ApprovalQueue
```

**Updated `run_once()` loop**
```python
async def run_once():
    # ... existing code ...
    
    # NEW: Cost check (Phase 6)
    ct = _get_cost_tracker()
    estimated_cost = 2.5 if IS_LLM_HEAVY else 0.5
    if not ct.can_afford(action, estimated_cost):
        return {"skipped": "budget_cap", "cost_status": ct.get_daily_status()}
    
    # NEW: Approval check (Phase 6)
    if aq.approval_required and IS_LLM_HEAVY:
        aq.queue_task(action, reason=..., cost_estimate=estimated_cost)
        return {"skipped": "approval_pending", "pending_approvals": len(aq.get_pending())}
    
    # ... execute action ...
    ct.record_cost(action, estimated_cost)
```

**New helper functions**
```python
def cost_status() -> dict:
    """Return current daily cost tracking status."""
    
def approval_status() -> dict:
    """Return current approval queue status."""
```

---

#### `app/api/growth.py` — API endpoints

**GET `/api/growth/selfimprove/cost-status`** (admin)
```json
{
  "date": "2026-06-14",
  "cap": 50.0,
  "spent": 12.5,
  "remaining": 37.5,
  "pct_used": 25.0,
  "tasks": [
    {"task": "content_pack", "cost": 2.5, "time": "2026-06-14T10:30:00Z"},
    {"task": "sales_deepdive", "cost": 2.5, "time": "2026-06-14T10:45:00Z"},
    {"task": "harvest_leads", "cost": 0.5, "time": "2026-06-14T11:00:00Z"}
  ]
}
```

**GET `/api/growth/selfimprove/approvals-pending`** (admin)
```json
{
  "approval_required": true,
  "pending_count": 2,
  "pending": [
    {
      "id": "abc123",
      "task": "sales_deepdive",
      "reason": "[auto] weakest stage 'outreach_quality' improve via sales_deepdive — LLM-heavy action",
      "cost": 2.5,
      "timestamp": "2026-06-14T10:30:00Z",
      "status": "waiting"
    }
  ],
  "approved_count": 3
}
```

**PATCH `/api/growth/selfimprove/approval/{task_id}/approve`** (admin)
- Approves pending task
- Task execution resumes on next `run_once()` tick
- Logs to agent_events

**PATCH `/api/growth/selfimprove/approval/{task_id}/reject`** (admin)
- Rejects pending task
- Reason logged to audit trail
- Task discarded, loop continues

---

### Frontend (HTML/JS)

#### `/app/automation` — Approvals tab

**New sections added to `sec-approvals`:**

1. **💰 Self-Improve Cost Tracking**
   - "Cost status load" button
   - Dynamic progress bar (red >80%, yellow 50-80%, green <50%)
   - Daily spent / remaining / cap
   - Per-task breakdown table (task name, cost, time)

2. **✋ Self-Improve Approval Queue**
   - "Pending load" button (auto-refresh)
   - Card per pending task:
     - Task name + timestamp
     - Cost ($2.5 or $0.5)
     - Reason (why it's LLM-heavy)
     - ✅ Approve button
     - ❌ Reject button (opens prompt for reason)
   - Badge on tab showing pending count
   - Message "✅ Koi pending approvals nahi" when none

3. **📥 Process Breakpoints + Code Patches** (existing)
   - No changes

**JavaScript functions added:**

```javascript
async function apCostStatus()
  // Load cost-status API → render budget bar + task table

async function apSelfImprovePending()
  // Load approvals-pending API → render task cards
  // Update tab badge with pending count

async function apSelfImproveApprove(taskId)
  // PATCH /approval/{id}/approve → log + refresh

async function apSelfImproveReject(taskId)
  // PATCH /approval/{id}/reject → log + refresh
```

**AUTOLOAD integration:**
```javascript
approvals: function() {
  apCostStatus();
  apSelfImprovePending();
  apLoad();  // existing process breakpoints
}
```

---

## Configuration

### Environment variables

```bash
# Phase 6 Safety Gates
SELF_IMPROVE_APPROVAL=0                # 0=auto-approve (default), 1=human gate
SELFIMPROVE_COST_CAP=50                # Daily budget cap ($)
```

**Modes:**

| `SELF_IMPROVE_APPROVAL` | Behavior |
|---|---|
| `0` (default) | All tasks execute immediately; cost tracked but not gated |
| `1` | LLM-heavy tasks queue for approval; loop pauses until approved/rejected |

**Cost model:**

| Action | LLM-heavy? | Estimated cost |
|---|---|---|
| harvest_leads | ✗ | $0.5 |
| scrape_leads | ✗ | $0.5 |
| revenue_sweep | ✗ | $0.5 |
| code_scan | ✗ | $0.5 |
| content_pack | ✓ | $2.5 |
| seo_pages | ✓ | $2.5 |
| sales_deepdive | ✓ | $2.5 |
| social_drafts | ✓ | $2.5 |
| channel_experiments | ✓ | $2.5 |
| optimizer | ✓ | $2.5 |
| reflection | ✓ | $2.5 |
| study_skills | ✓ | $2.5 |

---

## Data Model

### Logs

**Cost tracking: `/data/self_improve_runs.jsonl`** (existing, updated)

Each run now includes `cost` field:
```json
{
  "id": "abc123",
  "action": "content_pack",
  "cost": 2.5,
  "ok": true,
  "at": "2026-06-14T10:30:00Z"
}
```

**Approval audit: `/data/self_improve_approvals.jsonl`** (new)

Append-only log of approval events:
```json
{
  "id": "task_xyz",
  "task": "sales_deepdive",
  "reason": "...",
  "cost": 2.5,
  "timestamp": "2026-06-14T10:30:00Z",
  "status": "waiting"
}
{
  "id": "task_xyz",
  "task": "sales_deepdive",
  "status": "approved",
  "approved_at": "2026-06-14T10:35:00Z"
}
```

---

## Safety Guarantees

### Budget cap
- ✅ Hard limit: task rejected if `cost + spent > cap`
- ✅ Reset: daily at UTC 00:00
- ✅ Fail-open: if env var unset, defaults to $50/day

### Approval gate
- ✅ LLM-heavy only: approval skipped for light actions
- ✅ Opt-in: default OFF (`SELF_IMPROVE_APPROVAL=0`)
- ✅ Audit trail: every approval/rejection logged
- ✅ No double-execute: approved task only executes once (status: "approved")

### Never raises
- ✅ API returns error dict, never throws (fail-open)
- ✅ File I/O failures logged, don't crash loop
- ✅ JSON parse errors caught, graceful skip

---

## Testing

### Unit tests: `scripts/test_phase6_safety_gates.py`

```bash
python scripts/test_phase6_safety_gates.py
```

Tests:
1. CostTracker: budget check, daily reset, pct calculation
2. ApprovalQueue: queue, approve, reject, auto-approve logic
3. Global instances: singleton behavior
4. Helper functions: cost_status(), approval_status()
5. Environment variables: parsing, validation

### Integration tests: `tests/test_phase6_self_improve.py` (optional)

Would test:
- `run_once()` respects budget cap
- `run_once()` respects approval gate
- Cost logged to data files
- Approval logged to audit trail

### Manual testing: `/app/automation` → Approvals tab

1. Set `SELF_IMPROVE_APPROVAL=1`, `SELFIMPROVE_COST_CAP=5` (low cap to force approval)
2. Click "🗓️ Schedule" tab → "▶️ Ek tick abhi" (trigger one loop tick)
3. Switch to "📥 Approvals" tab
4. Verify:
   - ✅ Cost chart shows budget spent
   - ✅ Pending card appears with LLM-heavy action
   - ✅ Approve button → "✅ Approved" toast + task executes next tick
   - ✅ Reject button → "❌ Rejected" toast + task discarded

---

## Rollback / Disable

To disable Phase 6 gates:

```bash
SELF_IMPROVE_APPROVAL=0           # Approval gates OFF
SELFIMPROVE_COST_CAP=999999       # Budget cap effectively disabled
```

Or revert changes:
```bash
git revert <commit-hash>           # Revert Phase 6 commits
```

---

## Future improvements (not in scope)

1. **Dynamic cost model** — adjust `$2.5`/`$0.5` based on actual LLM provider rates
2. **Weekly/monthly budgets** — support longer budget windows
3. **Cost forecasting** — estimate week-ahead spend based on velocity
4. **Scheduled tasks approval** — auto-approve on time/condition
5. **Delegation** — different approval queues for different staff roles

---

## Files Changed

| File | Change |
|---|---|
| `app/agents/self_improve.py` | Add CostTracker, ApprovalQueue classes; update run_once() |
| `app/api/growth.py` | Add 4 API endpoints |
| `frontend/automation.html` | Add UI sections + JS functions |
| `.env` | Add SELF_IMPROVE_APPROVAL, SELFIMPROVE_COST_CAP |
| `scripts/test_phase6_safety_gates.py` | Add verification script |

---

## Deployment checklist

- [ ] ✅ Code review (CostTracker, ApprovalQueue logic)
- [ ] ✅ Run `scripts/test_phase6_safety_gates.py` — all tests PASS
- [ ] ✅ Deploy to VPS: `git push` → CI builds image
- [ ] ✅ Set env vars: `.env` SELF_IMPROVE_APPROVAL, SELFIMPROVE_COST_CAP
- [ ] ✅ Manual test: Approvals tab loads cost + pending tasks
- [ ] ✅ Verify audit trail: `/data/self_improve_approvals.jsonl` populated
- [ ] ✅ Monitor: check `/api/growth/selfimprove/cost-status` daily

---

## Lessons learned

1. **Global instances** — persist across loop iterations, not ideal but pragmatic for sync state
2. **Failure modes** — approval gate must be opt-in (backward compat), cost tracking always-on
3. **Audit is king** — every decision (approve/reject/budget-hit) logged, enables replay/debugging

---

## References

- [Self-Improve Loop Architecture](./SKILL.md)
- [Automation Decision Trees](../../docs/AUTOMATION.md)
- [Self-Improve Safety Research](./references/self-improve-safety.md)
