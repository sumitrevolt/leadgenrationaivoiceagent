# Follow-up Pipeline — Production Contract

**Workflow ID:** `followup.cadence` · **Version:** 1 · **Owner:** Rohan (Leads Manager)
**Trigger:** lead enrolled / reply / day-offset → `marketing/cadence.py` (`CADENCE_ENGINE`), `platform/lifecycle_nurture.py`

## State machine
```
ENROLLED → STEP_DUE → DRAFTED → [APPROVED → SENT] → NEXT_STEP/COMPLETED  [terminal]
   │           │          │
   └───────────┴──────────┴──► SUPPRESSED (opt-out/bounce, terminal) · FAILED (terminal)
```
- **Default = DRAFTED then human 1-click send** (ban-safe). Auto-send is per-channel flag-gated.

## Step → module map (real code)
| Step | Module | Idempotency / control |
|---|---|---|
| Enroll | `marketing/cadence.py` | lead id |
| Step due | day-offset scheduler | lead id + step no. |
| Draft | `cadence.py` / `lifecycle_nurture.py` / AI reply (`reply_agent.py`) | lead id + step |
| Suppress check | consent-ledger + `email_unsub` + DND | contact key |
| Send | email (`AUTO_EMAIL_OUTREACH`) / WhatsApp 1-click / SMS | lead id + step (dedupe) |
| Re-engage | `platform/winback.py` (`WINBACK_ENGINE`, 30-day dedupe) | lead id |

## Validation & reliability
**Opt-out/bounce → instant SUPPRESSED** (cross-channel). Caps: 25/day, warmup ramp, bounce auto-pause.
`_is_bulk_sender()` guard. Per-step dedupe key prevents double-send on retry. AI reply triage = draft (auto-send OFF).

## Events
internal `agent_events` (step transitions); no customer-facing webhook by default.

## Metrics & alerts
`agent_events` · send/reply/suppress counts · complaint rate (warmup auto-pause) · ntfy on cap breach.

## Test matrix (E2E)
happy cadence · opt-out suppress · bounce auto-pause · duplicate-step dedupe · reply-triage draft ·
winback 30-day dedupe · cap enforcement. Coverage: `test_email_unsub.py`,
`test_email_warmup_complaints.py`, `test_consent_reconsent_cooloff.py`, `test_reply_junk_guard.py`, `test_revenue_automation.py`.

## Runbook
[Duplicate / Non-Compliant Outreach](../runbooks/RUNBOOK_DUPLICATE_OUTREACH.md).
