# Workflow Contracts — LeadGen AI

Per-pipeline production contracts satisfying the Enterprise Playbook's
`08_WORKFLOW_ENGINE.md` + `WORKFLOW_READINESS_CHECKLIST.md`, grounded in the project's
**real** modules (not generic templates).

## Shared execution substrate (every pipeline inherits)
- **Engine:** Flow Runner — `automation/flow_store.py` (persist) + `flow_compiler.py`
  (validate) + `agents/flow_dispatch.py` (route) → linear `agents/process_engine.py` /
  DAG `agents/dag_engine.py`. Gated OFF by default (`FLOW_RUNNER`).
- **State persistence + replay:** event-sourced journal `data/process_runs/<run_id>.jsonl`
  (byte-identical replay). Voice conversation DSL = `voice_agent/flow_engine.py`.
- **Reliability:** per-step 240s timeout, bounded retry → FAILED terminal, fail-closed conditions.
- **Idempotency:** external side effects keyed (see each pipeline).
- **DLQ:** `platform/dlq_retry.run_sweep()` (`dlq:failed_tasks` → retry ×2 → `dlq:dead` + alert).
- **Events:** `agent_events` table + `customer_webhooks.SUPPORTED_EVENTS` (see
  [EVENT_BUS](../architecture/EVENT_BUS.md)).
- **Observability:** Prometheus/Grafana/Loki/Tempo/Sentry + `automation_health` dead-man.
- **Runbooks:** [../runbooks/](../runbooks/README.md).

## Pipelines
| Pipeline | Owner (agent) | Doc |
|---|---|---|
| Lead | Rohan / Neha | [LEAD_PIPELINE.md](LEAD_PIPELINE.md) |
| Voice Outreach | Swara / Tara | [VOICE_OUTREACH_PIPELINE.md](VOICE_OUTREACH_PIPELINE.md) |
| Content | Isha / Dev | [CONTENT_PIPELINE.md](CONTENT_PIPELINE.md) |
| Billing | Nikhil | [BILLING_PIPELINE.md](BILLING_PIPELINE.md) |
| CRM | Neha | [CRM_PIPELINE.md](CRM_PIPELINE.md) |
| Follow-up | Rohan | [FOLLOWUP_PIPELINE.md](FOLLOWUP_PIPELINE.md) |

## Readiness-checklist coverage (all pipelines)
owner ✅ · trigger ✅ · state machine ✅ · success/failure terminals ✅ · retry ✅ ·
timeout ✅ · idempotency ✅ · audit logs (`agent_events`) ✅ · metrics ✅ · alerts (ntfy) ✅ ·
pause/resume (Flow Runner breakpoint) ✅ · replay (event-journal) ✅ · E2E test ✅ ·
runbook ✅.
