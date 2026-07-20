# PRODUCTION_TRUTH — live-proven only

> Never mix planned / local / hoped-for changes into this file.

## Production SHA
`8ad64db7` — verified 2026-07-20 via `GET https://leadsgenai.in/health`
`environment=production` · `status=healthy`

## Container versions
UNKNOWN this session (no SSH inspect). Prior Loop Run (progress.md): WEB_CONCURRENCY=2 deploy claimed 0 skew on `8ad64db7`. Re-verify on next deploy.

## Health endpoints
| Endpoint | Result | Label |
|---|---|---|
| `/health` | healthy, version `8ad64db7` | PRODUCTION-PROVEN |
| `/api/activation/summary` | ready_for_launch true, blocker_count 0 | PRODUCTION-PROVEN |
| `/api/admin/owner-os/runtime` | auth-gated (expect 401 unauth) | PRODUCTION-PROVEN historically |
| `/api/voice/niches` | smoke historically 200 — NOT re-probed this session | UNKNOWN (this session) |

## Enabled high-risk flags (ops memory — re-verify on VPS `.env` before acting)
| Flag | Claimed state | Label |
|---|---|---|
| `AGENT_RUNTIME` | `1` (canary) | PRODUCTION-PROVEN (2026-07-20 canary Loop Run) |
| `PLATFORM_DIAL_DAILY` | HARD OFF | PRODUCTION-PROVEN mandate |
| `WHATSAPP_AUTO_SEND` | `0` | PRODUCTION-PROVEN ops fact |
| `SOCIAL_PREFS_HONOR` | `1` | PRODUCTION-PROVEN ops fact |
| `HOT_QUEUE_BRIEF_DAILY` | `1` | PRODUCTION-PROVEN ops fact |
| `RUN_IN_PROCESS_SCHEDULER` | `0` (Celery durable) | PRODUCTION-PROVEN ops fact |
| `UPI_AUTO_ACTIVATE` | `0` | PRODUCTION-PROVEN ops fact |
| `DLT_APPROVED` | `1` | PRODUCTION-PROVEN ops fact |

## Known live customer
Jiya Makeover Studio · marketing id `jiya-makeover` · billing alias `d79d690f61b3` · starter · INV/0001

## Live workflow evidence
- Agent Runtime Kavya `ops_health_check` succeeded under `AGENT_RUNTIME=1` (progress Loop Run 2026-07-20) — PRODUCTION-PROVEN
- Swara runtime place_call blocked `red_lane_hard_off_mandate_required` — PRODUCTION-PROVEN
- Jiya delivery progress **90%** (9/10) after ADR-125 — PRODUCTION-PROVEN at time of ADR; not re-scored this session → treat as PARTIAL until next status call

## Known production defects
- Origin/main (`79ef3dc`) not yet deployed — delivery_assurance dead on prod until deploy
- CLAUDE.md previously claimed prod SHA `4fa716cb` after infra deploy to `8ad64db7` — STALE docs (fixed via this context system)

## Last deployment evidence
`8ad64db7` WEB_CONCURRENCY=2 literal (progress.md Loop Run 2026-07-20) — PRODUCTION-PROVEN

## Rollback reference
- App image: redeploy prior `APP_VERSION=<previous sha>` via `scripts/deploy_vps.sh` (canonical)
- Agent Runtime canary: unset `AGENT_RUNTIME` + recreate app (~20s)
- Never `docker compose` without `-f docker-compose.vps.yml`
