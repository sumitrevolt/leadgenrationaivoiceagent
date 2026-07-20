# PRODUCTION_TRUTH — live-proven only

## Production SHA
`d32a4934` — verified 2026-07-20 via `GET https://leadsgenai.in/health`
`environment=production` · `status=healthy`

## Container versions
App-image services tagged `:d32a4934` (app, worker, scheduler, worker-heavy, worker-video) — PRODUCTION-PROVEN via compose ps after deploy.
Note: recreate used hashed container names; deploy script skew check false-failed while health+tags correct.

## Health endpoints
| Endpoint | Result | Label |
|---|---|---|
| `/health` | healthy, version `d32a4934` | PRODUCTION-PROVEN |
| `/api/admin/delivery-assurance` | 401 unauthenticated | PRODUCTION-PROVEN |
| `/api/admin/delivery-cockpit` | 401 unauthenticated | PRODUCTION-PROVEN |

## Enabled high-risk flags (ops memory — re-verify before acting)
| Flag | Claimed state | Label |
|---|---|---|
| `AGENT_RUNTIME` | `1` canary | PRODUCTION-PROVEN historically |
| `PLATFORM_DIAL_DAILY` | HARD OFF | PRODUCTION-PROVEN mandate |
| `WHATSAPP_AUTO_SEND` | `0` | PRODUCTION-PROVEN ops fact |

## Known live customer
Jiya Makeover · `jiya-makeover`

## Live workflow evidence
- In-container `delivery_assurance.missed_deliverables_summary()` → checked=1, missed=0, at_risk=1, error=None — PRODUCTION-PROVEN
- Routes include `/api/admin/delivery-assurance` once — PRODUCTION-PROVEN
- `product_one_health` in scheduler source (count 5) + prior heartbeat ok=True @ 2026-07-20T03:50Z — PRODUCTION-PROVEN registration; post-deploy hourly tick may not have fired yet

## Known production defects
- Deploy script APP_VERSION skew check false-negative on hashed container names (ops tooling debt)
- CI remote `prod_check + pytest` job fails many pre-existing tests (not WS-1 unique)

## Last deployment evidence
2026-07-20 deploy wave landed `d32a4934` (includes squash merge #59 `d625e48` + domain-assurance agents). Concurrent deploy noise; end state healthy.

## Rollback reference
`bash scripts/deploy_vps.sh 208fcf48` (pre-WS-1-merge tip) or `69c4c8d2` (earlier) — only if health/auth regresses. Current: no rollback needed.
