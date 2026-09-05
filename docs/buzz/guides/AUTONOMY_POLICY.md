---
title: "LeadGen Autonomy Policy — GREEN / AMBER / RED"
tags: [buzz, autonomy, governance, boss, compliance]
status: active
created: 2026-08-05
---

# Autonomy Policy

Owner decision 2026-08-05. Governs how the 31 runtime STAFF agents, Boss, and the
Buzz collaboration plane are allowed to act without a human in the loop.

## Chain of control (single control plane)

```
Buzz (#admin)  ->  Boss  ->  Owner OS / OpenClaw  ->  31 runtime STAFF  ->  Celery
```

Buzz is an **interface**, not a controller. Buzz never mutates STAFF directly and
never becomes a second control plane. Commands enter through Boss or not at all.

## Tiers

### GREEN — agent executes itself

The agent acts, then reports. No prior approval.

Qualifies when ALL of these hold:
- Reversible, or naturally idempotent.
- Inside the agent's own documented duty in `app/platform/team.py`.
- No money moves, no customer-visible irreversible send at scale.
- No compliance surface touched.
- Existing feature flag already ON.

Examples: health probes, KPI rollups, lead rescoring, RAG reseeding, report
generation, draft creation, queue drains within existing caps.

### AMBER — Boss decides

The agent proposes; Boss decides; relevant agents or the Council review where the
call is non-obvious. Owner is **not** prompted for routine AMBER.

Qualifies when:
- Cross-agent or cross-division impact.
- Changes a cap, threshold, schedule, or campaign shape.
- Spends a rate-limited external quota in a new way.
- Reassignment, retry-after-failure, defer, or rollback of another agent's work.

Boss's failure playbook: **retry -> reassign -> defer -> rollback**, in that order,
with the reason recorded in the owning channel.

### RED — system refuses, Boss included

Not a judgement call. The code refuses, and Boss has no override.

- DND scrub bypass (lookup failure must BLOCK promotional)
- TRAI calling window violation (10:00–19:00 IST enforced in code)
- Missing AI disclosure at call start
- Consent / opt-out suppression bypass
- DPDP breach: purpose creep, retention overrun, cross-client lead leak
- Secret exposure in any message, commit, log, or canvas
- Destructive ops: `DROP`, destructive migration, `reset --hard`, `git add -A`
- Inventing a 32nd STAFF persona
- Editing the FROZEN Swara / voice path
- Deploy by any route other than `scripts/deploy_vps.sh` with `APP_VERSION=<sha>`

A change that weakens a RED gate is an **ABORT**, never a fix.

## The one human gate

**Real UPI bank-credit confirmation and paid-ledger marking.**

Only the owner confirms that money actually landed. Nothing else in the system may
mark an invoice PAID, and `payment_verification_method` stays `owner_confirmed_upi`
— never `PROVIDER_VERIFIED`.

`UPI_AUTO_ACTIVATE` remains fail-closed: the allowlist
(`UPI_AUTO_ACTIVATE_CLIENTS`) is the containment, and an empty or unknown client is
refused. Routine coordination and approvals do **not** go to the owner. UPI does.

## Boss operating limits

- Max **3** active missions at once.
- Assigns and reassigns across the 31; posts final evidence in the owning channel.
- Refuses full-repo audits when `docs/context/ACTIVE_WORK.md` already has streams.
- Recommends flag flips; never silently changes prod `.env`.
- Stopping rule: wait for each delegate once, synthesize **one** answer, no ping-pong.

## Evidence contract

Every completed action carries proof, not prose:
exit code · targeted pytest result · `scripts/prod_check.py` · `/health.version`
read over direct HTTPS. Absence of errors is not evidence that a fix worked —
check the END timestamp of the error series before claiming causation.

## Audit + rollback

- Every AMBER decision and every RED refusal is logged with agent, tier, reason, time.
- Idempotency key on anything that can re-fire.
- Rollback path named **before** the action, not after.
- Kill switches stay owner-owned: `VOICE_LAUNCH_KILL`, `DIAL_TEST_MODE`,
  `SALES_AUTOPILOT_WHATSAPP_ENABLED`, `WHATSAPP_AUTO_SEND`.

## Rollout stages

1. Read-only canary — pulse mirror only, zero commands.
2. Bounded command canary — Boss routes a small, reversible GREEN set.
3. Full automation — AMBER delegated to Boss, owner sees UPI only.

Acceptance: 31/31 assigned · routine work needs zero owner prompts · UPI always
owner-confirmed · compliance fail-closed · no second control plane.
