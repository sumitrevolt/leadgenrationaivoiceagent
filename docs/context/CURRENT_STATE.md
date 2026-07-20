# CURRENT_STATE — LeadGen AI (operational truth)

> Evidence labels: PRODUCTION-PROVEN · CODE-PRESENT · TEST-PROVEN · LOCAL-ONLY · PARTIAL · STALE · UNKNOWN
> Do not treat chat history as truth when this file + code/runtime disagree.

## Last verified timestamp
2026-07-20T02:05Z (prod `/health` probe) · local git verified same session

## Local HEAD
bfdef446288c22c24282a8353dd81b74d063edec - feat(context): canonical docs + wire delivery assurance to admin cockpit
Label: CODE-PRESENT (matches origin/main)

## Origin/main
`79ef3dcd` — identical to local HEAD (no ahead/behind)
Label: CODE-PRESENT

## Production SHA
`8ad64db7` — `chore(infra): hardcode WEB_CONCURRENCY=2 literal`
Label: PRODUCTION-PROVEN (`curl https://leadsgenai.in/health` → version + environment=production)

**Drift:** origin/main is **1 commit ahead** of production (`79ef3dc` delivery_assurance not deployed yet).

## Repository cleanliness
DIRTY (LOCAL-ONLY uncommitted):
- `CLAUDE.md` / `AGENTS.md` (Current State canary notes — SHA claim stale vs live)
- `app/platform/automation_health.py` (ntfy dead-man push — not committed)
- `memory/decisions.md`, `progress.md`
- `data/*` jiya/marketing local ledger noise — do not commit
- Untracked: `docs/AGENT_24_7_SETUP_PLAN.md`, `docs/AGENT_ENABLEMENT_RUNBOOK.md`, `tests/test_coordinator_rate_cap.py`

Worktrees: many (Codex/Cursor) — several prunable/detached. Active hygiene branch: `chore/context-hygiene`. Delivery phases worktree: `feat/delivery-phases-2-4`.

## Production status
healthy · environment=production · uptime ~0.5h at probe · activation summary `ready_for_launch=true` blocker_count=0
Label: PRODUCTION-PROVEN

## Paying customers
1 — Jiya Makeover Studio · canonical id `jiya-makeover` · billing alias `d79d690f61b3` · INV/2026-27/0001
Label: PRODUCTION-PROVEN (prior ops + identity ADRs)

## Working customer workflows
- Identity canonicalize portal/delivery status (ADR-123) — PRODUCTION-PROVEN
- GBP + review_reply generators → delivery pct path (ADR-124) — PRODUCTION-PROVEN
- Branded posters 4/4 → **pct 90** (ADR-125) — PRODUCTION-PROVEN
- Agent Runtime canary `AGENT_RUNTIME=1`, Kavya read-only succeeded — PRODUCTION-PROVEN (flag); code SHA on that canary was `4fa716cb` then infra moved to `8ad64db7` — PARTIAL on “still same image for runtime”

## Broken / incomplete customer workflows
- **proof** deliverable (last 10%) — HONEST-blocked: Jiya own-page Meta Advanced Access / channel connect OR admin manual-publish + customer approval of `approval_pending` drafts — PARTIAL
- Delivery assurance module on origin/main — CODE-PRESENT + TEST-PROVEN, **not** PRODUCTION-PROVEN (prod still `8ad64db7`)

## Working admin controls
- Delivery cockpit `/api/admin/delivery-cockpit` (401 without admin) — PRODUCTION-PROVEN route live historically; current probe auth-gated
- Owner OS Runtime routes — PRODUCTION-PROVEN gated 401
- Mission Control `/app/automation` — CODE-PRESENT (frontend syntax fix shipped earlier)

## Broken admin controls
- Delivery Command Center KPI `At Risk` / `Benefit This Week` expected by JS but not fed from cockpit — CODE-PRESENT gap (LOCAL fix in flight this session)

## Non-voice agent status
- Canonical roster: **31** in `team.STAFF` / `agent_registry` — CODE-PRESENT + TEST-PROVEN
- Pilots under `AGENT_RUNTIME`: kavya / isha / zara — PRODUCTION-PROVEN canary (kavya); others not canary-proven
- Docs saying “32 agents” = STALE (control-plane/Boss counted as 32nd in some docs)

## Top blockers
1. Jiya `proof` = Meta customer-page access / approval — EXTERNAL
2. Prod lag behind origin (`79ef3dc` undeployed)
3. Context fragmentation (this folder created to stop it)

## Top 3 next actions
1. Finish wiring delivery_assurance → admin cockpit/API + tests; deploy when user authorizes (`8ad64db7` → HEAD)
2. Jiya proof path: customer approval of pending drafts OR Meta Advanced Access
3. GTM Hot Queue → 2nd paying customer
