# Signal catalogue — what to instrument, per flow

On-demand reference for `leadgen-observability`. The SKILL.md body says *how* to run the
audit; this file is the checklist you fill in while running it. Produce one row per flow
and leave the "current" column honest — an unknown is a finding, not a blank.

## Fill-in table

| Flow | Log event | Metric | Alert condition | Dashboard | Current |
|---|---|---|---|---|---|
| Signup → activation | | | | | |
| UPI payment submit → owner confirm | | | | | |
| Onboarding / first delivery | | | | | |
| Content generation cycle | | | | | |
| Lead pipeline (harvest → score → outreach) | | | | | |
| Email outreach + reply triage | | | | | |
| Celery queue + scheduler jobs | | | | | |
| Voice compliance gates (DND, window, consent) | | | | | |
| Infra (app, worker, Postgres, Redis, Qdrant) | | | | | |

## Structured-log field contract

Every event line should carry: event-name, status, a **safe** account id, request id,
duration, error-class. No PII, no recording contents, no credential values — masking is
part of the instrumentation patch, not a follow-up.

## Alert thresholds worth having

A revenue flow that stopped completing · a worker that stopped consuming · SMTP disabled ·
database unreachable · queue backlog growing monotonically · error-rate stepping up.
Anything that pages without one of these behind it is noise, and noise trains operators to
ignore the channel.

## Audit-log surface (separate from ops logs)

Admin approval, plan change, payment status transition, and any compliance-bypass
*attempt*. These are retained for accountability, so they answer "who did what", not
"is the box healthy".

## Product analytics

Activation, retention, feature usage. `POSTHOG_API_KEY` is the gate — the wiring exists,
so treat a gap here as configuration, not engineering.

## Scoring

Close the audit with a readiness score out of 100 and an explicit gap list. A flow with no
alert is a gap even when its dashboard looks green, because a dashboard nobody is watching
at 03:00 is not a signal.
