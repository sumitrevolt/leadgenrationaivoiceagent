# Lead Pipeline — Production Contract

**Workflow ID:** `lead.pipeline` · **Version:** 1 · **Owner:** Rohan (Leads Manager) + Neha (Pipeline Ops)
**Trigger:** mini-site inquiry / `/audit` / widget / CSV import → `platform/inquiry_hooks.run_after_inquiry()`

## State machine
```
CAPTURED → DEDUPED → ENRICHED → SCORED → SEGMENTED → QUEUED_OUTREACH → [terminal: ENROLLED]
   │           │          │         │          │              │
   └───────────┴──────────┴─────────┴──────────┴──────────────┴──► FAILED (terminal, logged)
```
- **Start:** CAPTURED. **Success terminal:** ENROLLED (in cadence/CRM). **Failure terminal:** FAILED.
- No implicit transitions; every transition logged to `agent_events` with actor + timestamp.

## Step → module map (real code)
| Step | Module | Idempotency key |
|---|---|---|
| Capture | `marketing/mini_site.py` + `inquiry_hooks` | inquiry id |
| Dedupe | Diya data-integrity (phone/email) + prospect-store | normalized phone/email |
| Enrich | `lead_scraper/*` + `platform/lead_harvester.py` (`LEAD_HARVESTER`) | lead id |
| Score | `platform/lead_scoring.py` (`LEAD_HOT_THRESHOLD`) | lead id + score-version |
| Segment | `marketing/cadence.py` + niche/band tags | lead id |
| Queue Outreach | `platform/auto_outreach.py` (`AUTO_EMAIL_OUTREACH`) | lead id + day |

## Validation rules (pre-transition)
- Inputs validated before start. **Consent/opt-out checked before any outreach** (consent-ledger + DND fail-closed).
- Subscription status checked before paid automations. Provider responses normalized; AI outputs schema-validated.

## Events emitted
`lead.created` (on capture) · `lead.qualified` (on qualify, `billing/lead_usage.py`) · `workflow.failed` (on FAILED).

## Reliability
Retry: bounded (Flow Runner) → FAILED. Timeout: 240s/step. DLQ: `dlq:failed_tasks`.
Manual recovery: re-enqueue via admin / journal replay. Daily caps: outreach 25/day, MX-verified.

## Metrics & alerts
`agent_events` (transition log) · lead count/score distribution · ntfy `ops_alerts` on stall.

## Test matrix (E2E) — `tests/`
happy path · invalid input · provider failure · retry success · max-retry failure ·
duplicate trigger (dedupe) · manual replay · permission failure · stale transition ·
end-to-end journey. Coverage: `test_lead_harvester.py`, `test_customer_onboard.py`, `test_workflow_gaps.py`.

## Runbook
[Duplicate / Non-Compliant Outreach](../runbooks/RUNBOOK_DUPLICATE_OUTREACH.md) ·
[Queue Backlog](../runbooks/RUNBOOK_QUEUE_BACKLOG.md).
