# Deploy Card — 2026-09-23 (b8b154fb → VPS srv1736379)

## Status

- **Candidate SHA:** `b8b154fb` (origin/main, CI green)
- **Previous prod:** `883ef713` (DIRECT_HOST_VERIFIED 2026-09-21)
- **Target version:** `/health.version = b8b154fb`

## Prerequisites (owner-only)

- [ ] VPS SSH reachable (`ssh root@72.61.245.204`)
- [ ] `/health` responds (`curl http://127.0.0.1:8000/health`)
- [ ] `/health.version` currently `883ef713` (or known)

## Deploy Command (run ON VPS)

```bash
cd /opt/leadgen && APP_VERSION=b8b154fb bash scripts/deploy_vps.sh b8b154fb
```

## What It Does

1. Gate container checks (APP_ENV=production, APP_VERSION=SHA, pgbouncer URL)
2. Build `ghcr.io/sumitrevolt/leadgenrationaivoiceagent:b8b154fb`
3. Rollout services: `worker scheduler worker-heavy worker-video dsh-worker`
4. Systemd `leadgen` restart (port 8000 owner)
5. Alembic migrate head
6. Health + smoke verification
7. Tag rollback: `git tag rollback-b8b154fb <previous-sha>`

## Rollback (emergency)

```bash
cd /opt/leadgen && git checkout 883ef713 && bash scripts/deploy_vps.sh 883ef713
```

## Post-Deploy Verification

- [ ] `/health.version = b8b154fb`
- [ ] `/health` → `healthy, environment:production`
- [ ] All 5 app-image services running (`docker ps`)
- [ ] Telegram poller active (no 409)
- [ ] TypeSafe probe success (`python scripts/typesafe_status.py --probe`)
- [ ] Revenue MTD still accessible (`/api/admin/revenue/mtd`)

## Pre-Deploy Warnings (from local prod_check)

- ⚠️ `.pyc` orphans in `scripts/` (telethon_enable_forums_v2, telethon_recreate_forum_groups, telethon_toggle_forum_topics) — SOURCE NOT IN TREE. These are from an unmerged branch checkout that left gitignored __pycache__ behind. **Do NOT delete — they may be needed by the branch work.**
- ⚠️ `.pyc` orphans in `tests/` (test_canonical_governance_ingestion, test_governance_integrity, test_owner_directive_checksum, test_telegram_egress) — same situation.

## Local Gates Already Passed (this session)

- `python scripts/prod_check.py` → exit 0, 1474 routes, 0 gaps
- 105 targeted tests (typesafe_intake_gate, typesafe_consumer_inventory, billing_truth_2026, smartflo_acceptance) → pass
- Ruff: 0 errors (1425 pre-existing, all fixable)
- `check_secrets.py`: no secrets detected

## Risk Assessment

**LOW** — additive docs/tests + 26-file SmartFlo framework merge. No schema changes, no billing path changes, no voice/telephony changes. Systemd leadgen restart is the only production-affecting action.

---

*Written 2026-09-23 08:35 IST by Hermes — owner deploy approval required.*
