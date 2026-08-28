# PB-DEPLOYMENT — Deployment Playbook (P0)

- **Purpose**: Ship code to prod safely with provenance + rollback, every time.
- **Trigger**: any production deploy request.
- **Scope**: verify -> build -> deploy -> probe -> record.
- **Prereqs**: kill fence for voice (VOICE_LAUNCH_KILL TRUE_TOKEN), prod_check --deployment PASS, secrets scan clean.

## Strategy
1. REPO TRUTH: fetch origin, confirm target sha on main (branch protection; PR-only).
2. CI green: pytest (targeted + billing truth), prod_check.py, check_secrets.py.
3. Deploy via CANONICAL script only: `scripts/deploy_vps.sh` (sets APP_VERSION=<sha>, deploys all 5 app-image services, pipefail).
4. Probe: /health .version == deployed sha, per-container skew = 0, smoke verify.
5. Record: progress.md Loop Run + SESSION_HANDOFF.

## Decision tree
```
Deploy request
├─ CI red / secrets dirty   -> STOP, fix first (RB-INFRA-008)
├─ APP_VERSION unset        -> refuse (:-latest = UNKNOWN provenance — landmine)
├─ health mismatch post-deploy -> rollback (RB-INFRA-009, RED)
└─ all green                -> record + ntfy
```

## Allowed actions
- deploy_vps.sh (DRY_RUN=1 for plan), targeted pytest, probes, rollback via previous sha.

## Prohibited actions
- Manual docker commands outside deploy script; reset --hard / blind rebuild on VPS; committing secrets; deploy without APP_VERSION.

## Escalation
- Deploy gate failure -> owner (kill fence missing/UNSET -> BLOCK).

## KPIs
- Deploy success rate; mean time to green; rollback rate.

## Guardrails
- Kill fence BEFORE deploy; `-f docker-compose.vps.yml` explicit; never deploy during active incident.

## Linked runbooks
RB-INFRA-007 (regression), RB-INFRA-009 (rollback), RB-INFRA-008 (CI failed), RB-INFRA-010 (config mismatch).

## Evidence requirements
- /health .version, dep.log tail, container skew table, smoke result.

## Owner approval conditions
- Owner arms deploy (kill-fence + script). Any hotfix outside normal PR flow.
