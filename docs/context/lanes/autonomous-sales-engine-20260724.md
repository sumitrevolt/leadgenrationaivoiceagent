# Lane: Autonomous Sales Engine (2026-07-24)

**Branch:** `feat/autonomous-sales-engine` (from `origin/main` `97521572441493208a6c77a91faf0990ddf7f225`)
**Worktree:** `C:\Users\Ratanshila\Documents\_leadgen_worktrees\lg-autonomous-sales`
**Owner:** sales-autopilot lane (this session)

## Goal
Production-ready, **policy-driven, fail-closed** autonomous Sales Operating System as an **additive, flag-gated, INERT-by-default** package under `app/platform/sales_autopilot/`. Dry-run is the default. No production sending. No calling. No deploy. Draft PR only.

## NO_TOUCH (hard refuse edits — owned by other sessions/PRs)
- `.github/**` — CI/CD owned by another session.
- **PR #121** (entitlement-assurance): `app/api/admin_dashboard.py`, `docs/context/lanes/sales-revenue-20260724.md`, `tests/test_admin_entitlement_assurance_route.py`
- **PR #122** (openclaw enter-to-run): `frontend/admin_dashboard.html`, `tests/test_openclaw_owner_copilot.py`
- **PR #123** (today overview): `app/platform/today_overview.py`, `frontend/admin_dashboard.html`, `frontend/delivery_command_center.html`, `tests/test_today_overview.py`
- `data/delivery_ledger/jiya-makeover.jsonl` — runtime customer ledger.
- Voice / Swara frozen paths (`app/voice_agent/**`, `app/telephony/**` behaviour).
- Any dirty primary-worktree files this lane does not own.

### Hard flag rules
- **Do NOT** flip `WHATSAPP_AUTO_SEND` to 1. It is NOT the master gate for this engine.
- **Do NOT** enable `PLATFORM_DIAL_*` or any calling. Calling HARD OFF forever in this wave.
- New engine gates default **OFF**: `SALES_AUTOPILOT_ENABLED`, `SALES_AUTOPILOT_WHATSAPP_ENABLED`, `SALES_AUTOPILOT_EMAIL_ENABLED`, plus per-stage kill switches.
- Admin surface = **new backend router only** (`app/api/sales_autopilot_admin.py`) mounted in `app/main.py`. Protected admin HTML files are NOT edited.

## Estique truth (verified)
- Estique Salon & Spa: id `1009985f-bd15-422a-93e4-69b6b8efd6bd`, phone `+919702475550`, email `info@estiquesalonsnspa.com`, Thane, `beauty_makeover`.
- Owner **already manually contacted** Estique → recorded as `manual_owner_confirmed`, initial step complete.
- Eligibility MUST reject a duplicate initial WhatsApp send to Estique (regression test required).

## Reuse (do not rebuild)
- `app/marketing/whatsapp_campaign.py::send_one` — WA send (ban-safe; auto only when its own flag + creds).
- `app/marketing/wa_campaign_runner.py::is_suppressed / suppress` — suppression list (opt-out).
- `app/platform/owner_os.py::kill_engaged(...)` — owner kill switches (`owner_whatsapp_outbound`, `owner_bulk_email`, `owner_payment_mutation`, `owner_all_agents`, `owner_schedulers`).
- `app/tasks/idempotency.py`, `app/tasks/staff_jobs.py`, `app/platform/team_scheduler.py` — scheduler pattern (INERT registration).

## Files owned by this lane (safe to create/edit)
- `app/platform/sales_autopilot/**` (new package)
- `app/api/sales_autopilot_admin.py` (new router)
- `app/api/automation_flags.py` (additive flag registration only)
- `app/main.py` (additive guarded router include only)
- `tests/test_sales_autopilot_*.py`
- `data/sales_autopilot/**` (runtime state; policy seed)
- this lane doc + `docs/context/SESSION_HANDOFF.md` (this lane)

## Rollout (owner action only, after deploy)
1. Deploy branch (separate authorization).
2. Keep dry-run: engine emits SIMULATED attempts only.
3. Owner reviews simulated attempts via `/api/sales-autopilot/*` admin API.
4. Enable `SALES_AUTOPILOT_ENABLED=1` (still dry-run) → verify eligibility/decisions.
5. Only then `SALES_AUTOPILOT_WHATSAPP_ENABLED=1` + policy `dry_run=false` with canary batch = 1.
Calling stays HARD OFF throughout.

## ADR — Autonomous Sales Engine (2026-07-24)
- **Decision:** Ship a self-contained, additive `app/platform/sales_autopilot/` package as the autonomous Sales Operating System. Policy-driven single source of truth (`data/sales_autopilot/policy.json` + env), one canonical eligibility function (fail-closed 4-state), deterministic-first safety validator (LLM tone-only, never authoritative), idempotent persist-before-provider send service (dry-run default), distributed-locked canary scheduler (batch=1, no catch-up flood), max-2 follow-ups, deterministic inbound classifier with fail-closed opt-out suppression, and handoff adapters to EXISTING activation/onboarding (no second CRM, no fake payment).
- **Why not reuse `SALES_ENGINE`/`CADENCE_ENGINE` flags:** those gate the existing draft-cadence engines; the autopilot needs its own narrow, independently-killable gates. `WHATSAPP_AUTO_SEND` is deliberately NOT the master gate (would couple ban-safety to sales autonomy).
- **Safety posture:** every gate fails to the safer outcome; provider timeout → `UNKNOWN_REQUIRES_REVIEW` (no auto-retry); Estique/`manual_owner_confirmed` → initial send returns `OWNER_EXCEPTION_REQUIRED` (regression test locks this).
- **Reuse:** `whatsapp_campaign.send_one` (ban-safe), `wa_campaign_runner.is_suppressed/suppress`, `owner_os.kill_engaged`, `tasks/idempotency` pattern.
- **Rollback:** unset `SALES_AUTOPILOT_ENABLED` (engine goes fully inert/dry-run) + recreate app; per-stage env kill switches for finer stops; nothing to migrate/revert in data (append-only ledger under `data/sales_autopilot/`).
- **Status:** flags default OFF, dry-run default; NOT deployed; draft PR only; calling HARD OFF.

## Verification (this lane, local)
- `pytest tests/test_sales_autopilot_*.py` → 51 passed.
- `scripts/prod_check.py` → ALL CHECKS PASSED (1182 routes; new router mounted; 0 wiring gaps).
- `scripts/check_secrets.py` → no secrets detected (22 changed files).
