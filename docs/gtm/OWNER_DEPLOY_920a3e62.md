# Owner deploy — undeployed `origin/main` vs live `91958c23`

**Do not run this from an agent sandbox without a VPS SSH key.** Owner SSH + kill fence only. No `reset --hard`. No `.env` dump. Cloud agent 2026-08-15: `Permission denied (publickey)` + `deploy-vps.yml` Build/Deploy skipped because `DEPLOY_ENABLED` is not true.

## Truth (re-probe before you start)

| Ref | SHA | Label |
|---|---|---|
| Live `/health.version` | `91958c23` (2026-08-15 dual probe 13:58:36Z / 13:58:39Z, uptime advanced) | DIRECT_HOST_VERIFIED |
| `origin/main` | `07870e89` (PR #371 squash) plus later docs-only handoff if merged — **re-fetch `origin/main` before deploy** | GIT_VERIFIED |
| GitHub heads | `main` only | GIT_VERIFIED |
| Open PRs | 0 (`#367` closed as superseded ghost) | GIT_VERIFIED |
| Actions deploy | run 31888501593 gate-only; Build + Deploy **skipped** | GIT_VERIFIED |
| Undeployed on live | #364 docs · #365 funnel `56ff46a9` · #366 next42 `920a3e62` · #368 callflags `c4e9058f` · #369 CI `6dd4ace0` (runtime no-op) · #371 HQ auto-chase `07870e89` INERT | VERIFIED |

P0 Hot Queue `callflag:` + renewal guard are **already in** `07870e89` (PR #368). Do not look for `cursor/revenue-blocker-p0`.

Today's UPI Bind/Re-Approve **does not need this deploy** — that path is already live on `91958c23`.

After deploy, do **not** arm `HQ_AUTO_CHASE`, `CONTENT_APPROVAL_SWEEP_LIVE`, cold WA, GSC, or `HARNESS_SESSION_EVENTS`.

## Canonical command (VPS)

```bash
# 1. Probe
curl -sS -H 'Cache-Control: no-cache' "https://leadsgenai.in/health?cb=$(date +%s)"

# 2. Drift check (mandatory)
git -C /opt/leadgen status --porcelain
docker diff leadgen_app

# 3. Kill fence (VOICE_LAUNCH_KILL=1 backup) then:
cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &
# poll /tmp/dep.log until === DEPLOYED <origin/main sha> OK ===
# If a docs-only handoff PR landed after #371, deploy that new SHA (re-fetch first).
# Minimum product SHA is 07870e89 (#371).

# 4. Recreate MUST carry APP_VERSION=<deployed sha>  (ADR-097 — never :latest)

# 5. Prove (twice, advancing timestamp)
curl -sS -H 'Cache-Control: no-cache' "https://leadsgenai.in/health?cb=$(date +%s)"
# version == origin/main sha, environment=production
# 5/5 app images :<sha> zero skew; VLK=0
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
