# Current State — LeadGen AI (2026-08-12)

> Short current-state handoff for AI sessions. Code remains source of truth; this file is the reasoning/status layer.

## Date
2026-08-12

## Production Truth

**Production SHA:** `9c47647c` (verified 2026-08-12 07:39 UTC via DIRECT_HOST probe)
- Last deploy: 2026-08-11 (per uptime 9h 33m)
- Includes: PR #332 (ADR-177 GSC), PR #330 (Boss governance), PR #329 (rollback retention)

**Main tip:** `1b8fe65d` (6 commits ahead of prod)
- Safe to deploy: YES (security patches + docs)
- Required: NO (revenue path already live)

**Rollback ref:** `9b09a808` (prior prod, verified 2026-08-11)

## Main Business Focus

**GTM 0→1:** 2nd paid customer this week (jiya makeover = only paying customer, ₹1,999 MRR)

**Sprint Goal:** Owner outreach execution + UPI confirm (technical path READY)

**Hot Queue:** CODE-LIVE at `/app/inbox` — owner 15 min daily blitz for conversion

## Revenue Path Status

**Money Funnel:** ✅ ALL LIVE
- Lead magnets: `/audit`, `/site-audit`, `/demo` (smoke OK 2026-08-12)
- Inquiry capture: `POST /api/public/inquiry` + Hot Queue bridge
- Pricing: `/pricing`, `/start` (both serve)
- UPI: Self-serve submit + guest bind (PR #320, CODE-LIVE)
- Payment rail: UPI manual (CANONICAL, owner bank verify)

**Paying Customers:** 1 (jiya makeover, INV/2026-27/0001)

**Billing Truth:** Locked by `tests/test_billing_truth_2026.py` (Main ₹1,999, Advanced ₹5,999)

**Technical Blockers:** NONE

**Owner Actions Required:**
1. Daily Hot Queue blitz (15 min at `/app/inbox`)
2. UPI approval when payment arrives (5 min per submission)

**Runbook:** `docs/ops/OWNER_REVENUE_BLITZ.md` (created 2026-08-12)

## Automation Posture

**Staff Bus (31 Agents):**
- Synthetic canary: ✅ PROVEN 2026-08-12 (31/31 agents OK)
- Control agents: ✅ PROVEN (Fizz/Honey/Bumble/Comb/Boss all replied)
- Production flag: `STAFF_BUS_ENABLED=0` (keep OFF until AUTH-MERGE)

**Voice Calling:**
- Status: ✅ FULL CAMPAIGN LIVE (owner go-ahead 2026-08-02)
- Flags: `VOICE_LAUNCH_KILL=0`, `DIAL_TEST_MODE=0`, `PLATFORM_DIAL_DAILY=1`, `PLATFORM_DIAL_LIMIT=100`
- Compliance: DND fail-closed, TRAI window 10-19 IST, AI-disclosure, consent, DLT

**Sales Autopilot:**
- Status: ✅ EMAIL LIVE (owner-armed 2026-08-01)
- Flags: `SALES_AUTOPILOT_ENABLED=1`, `DRY_RUN=0`, `EMAIL_ENABLED=1`, `WHATSAPP_ENABLED=0` (cold WA HARD-OFF)

**GSC Rank Tracking:**
- Status: CODE-LIVE but INERT (PR #332 deployed)
- Flag: `GSC_ENABLED=0` (creds pending, runbook exists)
- Priority: MEDIUM (pSEO observability, not revenue-blocking)

## Flag Posture (Last verified 2026-08-04 in-container)

**Revenue-Critical:**
- `UPI_AUTO_ACTIVATE=1` (ARMED but fail-closed allowlist, 1 client only)
- `VOICE_LAUNCH_KILL=0` (calling LIVE, 100/day cap)
- `PLATFORM_DIAL_DAILY=1` (boolean ON, full campaign)
- `SALES_AUTOPILOT_ENABLED=1` (email ON, WA OFF)

**Do-Not-Arm (Absolute):**
- `STAFF_BUS_ENABLED=0` (keep OFF until AUTH-MERGE)
- `BOSS_DECISION_GOVERNANCE=0` (WS-GOV constraint)
- `DUNNING_ENGINE=0` (issue #307, owner decision)
- `GSC_ENABLED=0` (creds pending)
- `SALES_AUTOPILOT_WHATSAPP_ENABLED=0` (ban-safety HARD-OFF)
- `ALLOW_TOS_SCRAPE=0` (ToS compliance HARD-OFF)

## Dependabot Status (2026-08-12)

**Evidence:** `docs/evidence/DEPENDABOT_TRIAGE_20260812.md` (PR #344)

**Safe to merge now (dev-only):**
- #323 `actions/setup-python` 7.0.0 (CI-only)
- #326 `mkdocstrings` 1.0.6 (docs tool)
- #327 `mypy` 2.3.0 (type checker)
- #328 `pylint` 4.0.6 (linter)

**Wait / Review first:**
- #322 `actions/checkout` 7.0.1 (BREAKING: fork PR checkout in `pull_request_target`)
- #324 `python-minor-patch` group (35 updates, contains MAJOR bumps: `sentry-sdk` 1.x→2.x, `pydantic-settings` 2.14→2.15)
- #325 `sentry-sdk` 2.66.1 (duplicate of #324)

## Safety State

**Compliance Gates:** INTACT (TRAI, DPDP, DND, consent, retention)

**Voice/Swara:** FROZEN (no edits without owner approval)

**Secrets:** All in `.env` (gitignored), no committed values

**Outbound Automation:**
- Voice calling: LIVE (100/day cap, compliance gates active)
- Email autopilot: LIVE (25/day cap, warmup)
- Cold WhatsApp: HARD-OFF (ban-safety)
- Post-call WhatsApp: ON (interested leads only, separate path)

**Payment Rail:** UPI manual ONLY (Stripe/Razorpay REMOVED)

## Known Issues / Blockers

**Owner-Action Required:**
- Hot Queue daily blitz (15 min/day for 2nd paid)
- UPI approval when payment arrives
- GSC creds setup (optional, runbook exists)
- Comb Desktop NIP-OA mint (1 click, for staff bus AUTH)

**External-Blocked (Low Priority):**
- Meta app-review for customer Pages (own-brand already works)
- GBP API approval (observability only)
- DKIM DNS setup (deliverability opt)

**No-Action (Working as Designed):**
- Prod 6 commits behind main (expected, no deploy since 2026-08-11)
- GSC inert (creds pending, not blocking)
- Staff bus OFF (synthetic canary OK, waiting AUTH-MERGE)

## Last Verified Gate

**Tests:** Full pytest suite ~80+ green (targeted suites preferred for speed)

**Verification:**
- `prod_check.py` PASS (API docs sync 1295 ops)
- `check_secrets.py` clean
- Ruff clean for touched files
- Duplicate route grep clean
- Alembic single head

**Evidence:**
- `/health` probe 2026-08-12 07:39 UTC = `9c47647c` (DIRECT_HOST_VERIFIED)
- Smoke routes: `/pricing`, `/start`, `/app/inbox` all 200 OK
- Hot Queue wired + tested (PR #341 evidence)
- Guest UPI bind wired + tested (PR #320, 221-line test)

## Worktree / Branch State

**Trunk Hygiene:** PARTIAL COMPLETE
- Consolidation evidence: `docs/evidence/WORKTREE_BRANCH_CONSOLIDATION_20260812.md` (PR #335/340)
- Orphan dirs remain: `leadgen-boss-second-brain-governance-20260811`, `.claude/worktrees/buzz-multi-agent-setup-b0ce78`
- Gate A `.freebuff` noise: IGNORE (per user instruction)

**Active Branch:** `cursor/automation-revenue-ready-docs-166e` (this PR)

## Do Not

- Deploy without `VOICE_LAUNCH_KILL=1` gate set first
- Arm `STAFF_BUS_ENABLED` / `GSC_ENABLED` / `DUNNING_ENGINE` / `BOSS_DECISION_GOVERNANCE` without AUTH
- Edit Voice/Swara paths (FROZEN without owner approval)
- Merge Dependabot #322-#325 blindly (see triage doc)
- Weaken compliance gates (TRAI, DPDP, DND)
- Enable cold/bulk WhatsApp automation (ban-safety)
- Use `git add -A` (parallel agent risk)

## Next Steps (Owner)

**Immediate (This Week):**
1. Hot Queue daily blitz (15 min/day, runbook: `docs/ops/OWNER_REVENUE_BLITZ.md`)
2. UPI approval when payment arrives (5 min per submission)
3. Close 1+ lead → 2nd paid customer → MRR increases to ₹4,000+

**Optional (Not Blocking):**
1. Merge safe Dependabot PRs (#323, #326, #327, #328)
2. Deploy main tip `1b8fe65d` (security patches, not required)
3. GSC creds setup (rank tracking observability)
4. Guest UPI live proof (staging sim or wait for first guest payment)

## Evidence Files

**Created 2026-08-12:**
- `docs/evidence/AUTOMATION_REVENUE_READY_20260812.md` (this PR)
- `docs/ops/OWNER_REVENUE_BLITZ.md` (this PR)
- `docs/CURRENT_STATE.md` (this file, updated)

**Pre-Existing:**
- `docs/evidence/REVENUE_READY_20260812.md` (PR #341)
- `docs/evidence/STAFF_BUS_20260812.md`
- `docs/evidence/DEPENDABOT_TRIAGE_20260812.md` (PR #344)
- `docs/context/AUTOMATION_MAX_READINESS_MATRIX.md` (32-row capability audit)

---

**Last Updated:** 2026-08-12
**Prod SHA:** `9c47647c` (DIRECT_HOST_VERIFIED)
**Main Tip:** `1b8fe65d` (6 commits ahead, safe to deploy)
**MRR:** ₹1,999 (1 active customer)
**Target:** 2nd paid this week (owner execution only blocker)

---

**Canary:** 🐦 pelican
