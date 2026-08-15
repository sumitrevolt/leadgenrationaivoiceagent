# Owner deploy — undeployed `origin/main` vs live `91958c23`

**Do not run this from an agent sandbox.** Owner SSH + kill fence only. No `reset --hard`. No `.env` dump.

## Truth (re-probe before you start)

| Ref | SHA | Label |
|---|---|---|
| Live `/health.version` | `91958c23` (2026-08-15 dual probe) | DIRECT_HOST_VERIFIED |
| VPS `/opt/leadgen` HEAD | `91958c23` | VERIFIED |
| 5 app images | `:91958c23` zero skew | VERIFIED |
| `origin/main` | `920a3e62` (PR #366) | GIT_VERIFIED |
| Undeployed on live | #364 docs `c35edb4d` · #365 funnel `56ff46a9` · #366 next42 `920a3e62` | VERIFIED |
| This P0 branch | `cursor/revenue-blocker-p0` (renewal guard + Hot Queue `callflag:` + HARD_OFF default) | CODE-PRESENT until merged+deployed |

Deploying `920a3e62` alone does **not** include this session's P0 patches. Merge/PR the P0 branch first **or** cherry-pick, then deploy that SHA.

Today's UPI Bind/Re-Approve **does not need this deploy** — that path is already live on `91958c23`.

## Canonical command (VPS)

```bash
# 1. Probe
curl -sS -H 'Cache-Control: no-cache' "https://leadsgenai.in/health?cb=$(date +%s)"

# 2. Kill fence (VOICE_LAUNCH_KILL=1 backup) then:
cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &
# poll /tmp/dep.log until === DEPLOYED <sha> OK ===

# 3. Recreate MUST carry APP_VERSION=<sha>  (ADR-097 — never :latest)

# 4. Prove
curl -sS -H 'Cache-Control: no-cache' "https://leadsgenai.in/health?cb=$(date +%s)"
# version == deployed sha, environment=production, timestamp advancing
```

Rollback: `ROLLBACK_TAG=c4fc0087` via the same script. Fence backup names only, never paste `.env`.

## Never

- `docker compose` without `-f docker-compose.vps.yml`
- recreate without `APP_VERSION`
- `DSH_AGENT_ALLOWLIST=*`
- arm `HARNESS_SESSION_EVENTS`
- flush `dlq:dead`
- raise `WEB_CONCURRENCY`
- cold WA auto
