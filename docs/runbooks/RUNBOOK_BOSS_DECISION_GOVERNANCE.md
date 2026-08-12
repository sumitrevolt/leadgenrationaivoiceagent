# RUNBOOK — Boss + Second Brain Decision Governance

**Flag:** `BOSS_DECISION_GOVERNANCE` (default OFF / INERT)
**Module:** `app/platform/boss_decision_governance.py`
**Rollback:** unset / `BOSS_DECISION_GOVERNANCE=0` — execute path fail-closed; propose/list remain local-only diagnostics.

## What this is

Hash-bound per-decision approval for **decision-bearing** STAFF outputs only.
Heartbeats, telemetry, drafts, roster pulse, and hierarchical aggregate Boss
verdicts are **not** approval proof.

State machine:

`proposed → advice_requested → advice_recorded → boss_reviewed → boss_approved|boss_rejected|needs_owner|refused → executed|consumed`

## Authority

| Lane | Rule |
|------|------|
| GREEN | Boss may approve after valid Second Brain advice + review |
| AMBER | Requires Owner OS decision id |
| RED | Refused |
| UPI / payment types | Human-only — Boss cannot approve/execute |
| Self-approve | Boss cannot approve a decision they proposed |
| held / disabled | Routing-covered but unarmed |

Second Brain (`obsidian_sync.recall` + optional LLM Council) is **advisory only**.
Unavailable / stale / malformed / cross-tenant / hash mismatch → fail-closed.

## Owner OS / Buzz

- Owner OS `approvals_inbox` surfaces pending governed decisions (same surface).
- Buzz `#admin` = `buzz_ro_projection()` read-only mirror — no mutation.
- No second approval SPA / ledger / Boss / scheduler.

## 31/31 meaning

Static routing coverage for all canonical STAFF identities and decision types.
**Not** a claim that every live customer decision for held agents was approved.

## Verify

```bat
.venv\Scripts\python.exe -m pytest tests/test_boss_decision_governance.py -q
.venv\Scripts\python.exe scripts\prod_check.py
```
