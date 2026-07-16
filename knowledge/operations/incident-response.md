---
type: Runbook
title: Incident response
description: Prod triage loop — evidence first, no false causation.
tags: [sre, incident, sentry]
timestamp: 2026-07-17T00:00:00Z
resource: memory/incidents.md
---

# Incident response

1. Health 000/502 → `docker ps` + logs → targeted recover (not blind rebuild).
2. Sentry `search_issues` / `search_events` — check error series **end** timestamp before claiming a fix worked (ADR-097 lesson).
3. Postmortem → `memory/incidents.md` + prevention rule.
4. Self-heal cron `scripts/vps_selfheal.sh` */10 already runs — do not fight it with thrash restarts.

Related: [Deployment](deployment-runbook.md).
