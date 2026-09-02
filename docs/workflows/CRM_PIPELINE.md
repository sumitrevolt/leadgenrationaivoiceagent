# CRM Pipeline — Production Contract

**Workflow ID:** `crm.sync` · **Version:** 1 · **Owner:** Neha (Pipeline Ops)
**Trigger:** lead state change / qualify → `platform/crm_sync.py` (`CRM_SYNC`, default OFF)

## State machine
```
LEAD_CHANGED → MAPPED → SYNC_QUEUED → PUSHED → CONFIRMED  [terminal: SYNCED]
     │            │           │           │
     └────────────┴───────────┴───────────┴──► SYNC_FAILED (terminal, retry-eligible)
```

## Step → module map (real code)
| Step | Module | Idempotency |
|---|---|---|
| Map fields | `platform/crm_sync.py` (Zoho India DC / HubSpot) | lead id + provider |
| Push | per-client or global creds | external record id (upsert, not insert) |
| Confirm | response normalize | external id |
| Stage change | emits `crm.stage_changed` (internal) | lead id + stage |

## Validation & reliability
Upsert (not blind insert) = no duplicate CRM records. Per-client OR global creds; INERT without creds.
Retry on transient → SYNC_FAILED → DLQ-eligible. Data quality pre-check by Diya (dedupe, missing-contact).

## Events
`crm.stage_changed` (internal `agent_events`).

## Metrics & alerts
`agent_events` · sync success rate · `data_integrity_score` (Diya) · ntfy on repeated sync failure.

## Test matrix (E2E)
happy sync · missing creds (inert) · upsert dedupe · provider failure retry · stage change ·
field-map validation. Coverage: `test_crm_sync.py`, `test_parity_clientcrm.py`.

## Runbook
[Provider Outage](../runbooks/RUNBOOK_PROVIDER_OUTAGE.md) · [Queue Backlog](../runbooks/RUNBOOK_QUEUE_BACKLOG.md).
