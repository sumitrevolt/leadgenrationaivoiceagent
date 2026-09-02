# Owner deploy — live `07870e89` vs `origin/main` `94ab3167` (docs-only)

**Product SHA is already live.** Do not re-run a full deploy just to pick up docs #372. No `reset --hard`. No `.env` dump.

## Truth (re-probe before you start)

| Ref | SHA | Label |
|---|---|---|
| Live `/health.version` | `07870e89` (2026-08-15 dual probes 14:09:45Z–14:10:20Z, uptime advanced from a fresh recreate) | DIRECT_HOST_VERIFIED |
| `origin/main` | `94ab3167` (PR #372 docs squash on top of `07870e89`) | GIT_VERIFIED |
| GitHub heads | `main` only | GIT_VERIFIED |
| Open PRs | 0 | GIT_VERIFIED |
| Actions deploy | `07870e89` run 31888501593 gate-only; Build + Deploy **skipped** (`DEPLOY_ENABLED` not true). Live recreate was SSH from another host, not this cloud agent. | GIT_VERIFIED |
| 5/5 app-image pin | UNVERIFIED from cloud sandbox (no SSH) | UNKNOWN |

`HQ_AUTO_CHASE` is CODE-PRESENT on the live SHA. Keep it **INERT**. Do not arm `CONTENT_APPROVAL_SWEEP_LIVE`, cold WA, GSC, or `HARNESS_SESSION_EVENTS`.

UPI Bind/Re-Approve is already on this live SHA. Today's revenue gate is owner inbox + bank confirm, not another deploy.

## If you must deploy again (optional docs SHA)

```bash
# 1. Probe — expect 07870e89 unless you intend to move it
curl -sS -H 'Cache-Control: no-cache' "https://leadsgenai.in/health?cb=$(date +%s)"

# 2. Drift check (mandatory)
git -C /opt/leadgen status --porcelain
docker diff leadgen_app

# 3. Kill fence then:
cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &
# poll until === DEPLOYED <sha> OK ===
# Recreate MUST carry APP_VERSION=<sha> (ADR-097 — never :latest)
```

Rollback: `ROLLBACK_TAG=c4fc0087` via the same script (re-probe before using). Fence backup names only, never paste `.env`.

## Never

- `docker compose` without `-f docker-compose.vps.yml`
- recreate without `APP_VERSION`
- `DSH_AGENT_ALLOWLIST=*`
- arm `HARNESS_SESSION_EVENTS` or `HQ_AUTO_CHASE`
- flush `dlq:dead`
- raise `WEB_CONCURRENCY`
- cold WA auto
