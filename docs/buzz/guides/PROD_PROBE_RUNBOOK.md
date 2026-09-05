---
title: "Read-Only Production Probe Runbook"
tags: [leadgen, prod, runbook, read-only, observability]
status: active
created: 2026-08-03
---

# Read-Only Production Probe

Proven working 2026-08-03. Use this whenever a report needs *current* prod facts instead of
whatever the context docs last recorded. Everything here is read-only — nothing in this runbook
changes state.

**Host:** `root@72.61.245.204` · **Repo on box:** `/opt/leadgen` · **Public:** https://leadsgenai.in

## 1. Health and version (no SSH needed)

```
GET https://leadsgenai.in/health
```

Report `version` and `environment`. This is the authoritative prod SHA — never quote a SHA from a
doc, a git log, or a browser tab. If `version` is `latest`, prod provenance is UNKNOWN and that is
itself the finding.

## 2. SHA agreement

`git fetch`, then compare `/health.version` against `origin/main`. A stale local ref has already
caused one agent to report a merged PR as unmerged — fetch first, always.

## 3. Container skew

Per-container image tag for all five app-image services: `app`, `worker`, `scheduler`,
`worker-heavy`, `worker-video`. All five must be on the same SHA. Any disagreement means a partial
deploy and the odd one out is running unknown code.

## 4. Queues

Redis needs no auth and only `db0` holds keys. Check `llen` for `celery`, `dlq:failed_tasks`,
`dlq:dead`. Non-zero DLQ is a real finding; a large `celery` backlog after a worker recreate is the
known restart-storm symptom.

## 5. Flags

Report values for named non-secret flags only — e.g. `SALES_AUTOPILOT_ENABLED`,
`SALES_AUTOPILOT_REFILL`, `SALES_AUTOPILOT_DRY_RUN`, `SALES_AUTOPILOT_WHATSAPP_ENABLED`,
`VOICE_LAUNCH_KILL`, `DIAL_TEST_MODE`, `WHATSAPP_AUTO_SEND`.

**Never dump `.env`.** Never print a secret value. Grep for the named keys only.

Note the flags are not all at the top of the file — `WHATSAPP_AUTO_SEND` and
`SALES_AUTOPILOT_WHATSAPP_ENABLED` sit near lines 498 and 629. Check for duplicate definitions of
the same key; last-wins, so an appended duplicate silently overrides.

## 6. Ask the code, not the filesystem

For kill switches, **call the real function inside the live container** rather than inferring from a
missing file. On 2026-08-03 a file-absence check pointed the right way for the wrong reason; the
authoritative answer came from evaluating `kill_engaged('owner_whatsapp_outbound')` and
`auto_send_enabled()` directly. The store is DB-backed, not the JSONL sidecar.

`auto_send_enabled` is defined in `app/marketing/whatsapp_campaign.py:33-42`.

## 7. Timestamps

Give every finding a UTC timestamp. Facts age fast here and an undated fact becomes a lie within a
day — that is exactly how the 2026-08-02 labels ended up misleading a report on 08-03.

## Reporting

Lead with what changed since the docs, not with what matches. Flag any gate that is open which
`CURRENT_STATE.md` records as closed — that gap is the highest-value thing a probe can find.
