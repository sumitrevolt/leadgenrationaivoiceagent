---
name: slo-error-budget
description: SLO definitions + error-budget policy + burn-rate alerts for leadsgenai.in — uptime, voice-call success, email deliverability, LLM chain ok-rate, scheduler job freshness. Use jab "kitna reliable hai", SLA customer ko dena ho, alert fatigue tune karni ho, ya feature-velocity vs stability trade-off decide karna ho.
---

# SLO & Error Budget (reliability ko number do, feeling nahi)

> Enterprise audit skill. `observability-ops` = monitoring STACK chalana; **yeh = kya measure karna + kab rukna** (error budget khatam = feature freeze, reliability work). Pehle `context-first`.

## SLO set (single-VPS realistic — 99.99% ka natak mat karo)
| SLI | Target | Source |
|---|---|---|
| `/health` uptime (public) | 99.5%/30d (~3.6h budget) | Uptime Kuma + Gatus |
| p95 API latency (public pages) | <800ms | Prometheus `/metrics` |
| Voice call completion (no infra-error drop) | 97% | `call.completed` vs errors |
| STT/LLM/TTS chain ok-rate | 98% (breaker cooldowns count against) | free_ai provider stats |
| Email delivery (non-bounce) | 97% | outreach bounce tracking |
| Scheduler job freshness (24 staff jobs) | har job apne window+2h me heartbeat | `data/job_heartbeats.json` |
| Webhook delivery (customer H.1) | 99% within 5 retries | dispatch log |

## Error budget policy (dhanda rule)
- Budget = (1 − SLO) × window. Track monthly.
- **Budget >50% left** → normal velocity (ship features).
- **<50%** → risky deploys sirf verify-ship FULL gate ke saath, canary-style (off-peak).
- **Budget EXHAUSTED** → feature freeze us surface pe; sirf reliability/rollback work jab tak burn ruk na jaye. Yeh decide-and-ship ka counterweight hai — dono enterprise behavior hain.

## Burn-rate alerts (Alertmanager)
- Fast burn: 2% budget/1h → page (ntfy `ops_alerts` fan-out, G.1).
- Slow burn: 10%/24h → email digest me.
- Prometheus rules `monitoring/` me add karo; alert me SLI + budget-left % include.

## Wiring workflow
1. Existing metrics inventory: `curl -s localhost:8000/metrics | grep -c '^leadgen'` + celery-exporter (:9808) + Gatus/Kuma checks list.
2. Missing SLI = instrument karo (counter success/total per surface — additive, flag-safe).
3. Recording rules (ratio) + burn-rate alert rules → prometheus.yml reload.
4. Grafana SLO dashboard (provisioning dir me JSON = git-safe, restart-persistent).
5. Monthly: budget review → `docs/SESSION_LOG.md` me 3-line entry (SLI, budget used, decision).

## Enterprise bar
- Har customer-visible promise (pricing page "reliable") ke piche measured SLI ho.
- Alert = actionable only (runbook link in annotation → `prod-incident-triage`).
- SLO breach postmortem = blameless, root-cause + guard shipped (incident skill).

## Output
SLO table (SLI × target × current × budget-left) · burn-rate rules shipped · dashboard JSON · freeze/velocity verdict.

## Related repo skills
`observability-ops` (stack) · `prod-incident-triage` (breach response) · `leadgen-automation-reliability` (job loops) · `llm-quota-ops` (provider budgets) · `verify-ship` (deploy gate).
