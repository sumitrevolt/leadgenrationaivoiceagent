# Event Bus — LeadGen AI

> Formalizes the Playbook's `12_EVENT_BUS.md` against the project's **existing**
> event mechanism. Per Council 2026-06-25 + operating-manual ("additive > destructive,
> don't refactor a working system without evidence"): this documents the live
> implementation — **no event-bus refactor was performed.**

## Implementation (what exists)
The event bus is delivered by three cooperating layers:

| Layer | Module | Role |
|---|---|---|
| Internal event log | `agent_events` table + SSE | every agent/loop action, dashboards, audit trail |
| Customer-facing bus | `app/platform/customer_webhooks.py` | Svix-style **HMAC-signed** delivery to customer endpoints (`CUSTOMER_WEBHOOKS`) |
| Outbound integrations | `app/platform/outbound_webhooks.py` | internal → external integration fan-out |

## Event registry (typed, stable contract)
Source of truth = `customer_webhooks.SUPPORTED_EVENTS` (append-only, never rename —
keeps customers' verifiers stable):

| Event (past-tense) | Producer | Emit site |
|---|---|---|
| `lead.created` | mini-site inquiry | `platform/inquiry_hooks.run_after_inquiry()` |
| `lead.qualified` | billing meter | `billing/lead_usage.py:153` + `automation/orchestrator_pipeline.py:678` |
| `call.completed` | call meter | `billing/usage.py:157` (via `telephony/post_call_hooks.meter_call_completion`) |
| `call.report.ready` | post-call report | report generator |
| `payment.received` | billing | payment confirm hook |
| `subscription.activated` | subscription | activation hook |
| `subscription.cancelled` | subscription | cancel hook |

> `lead.created` / `lead.qualified` / `call.completed` are **live-wired**; the
> `payment.*` / `subscription.*` emit points are registry-ready (documented hook
> pattern in `customer_webhooks` docstring) — wire after billing webhook handlers stabilize.

## Event contract (per delivery)
Each webhook payload carries: `event_id`, `event_type`, `occurred_at`, `producer`,
`customer_id`, `entity_id`, `payload`, plus an **HMAC signature header** for verification.
Correlation/trace IDs flow via the request context + `agent_events` row id.

## Delivery guarantees & rules
- **Immutable** events; **no secrets** in payloads.
- **Idempotent consumers** — retries safe (consumer-side keying).
- **Retry:** 3 attempts, backoff `(5s, 30s, 300s)` (`_RETRY_BACKOFF_S`), 10s HTTP timeout.
- **Failure → DLQ:** repeated delivery failure recorded; deliveries tail kept (`_DELIVERIES_TAIL=500`).
- **SSRF defense:** customer URLs validated (`_is_url_safe`, private-IP deny default ON) — same defense as the `/site-audit` C4 fix.
- **Signature fail-closed in prod** when the secret is unset.

## Replay
Replay only after: scope defined · idempotency verified · affected consumers listed ·
dry-run performed · rollback plan exists. Internal workflow replay = the event-sourced
journal (`data/process_runs/<run_id>.jsonl`, byte-identical).

## Versioning
New event types **append** to `SUPPORTED_EVENTS`; never rename (breaks verifiers).
Payload schema changes are additive. Removal = deprecation cycle, not a hard delete.

## Open delta vs Playbook letter
The Playbook lists ~16 event names; this project ships a **deliberately small, stable 7**
(customer-contract discipline). Additional internal signals live in `agent_events`
(not exposed as customer webhooks by design). This is a scope choice, not a gap.
