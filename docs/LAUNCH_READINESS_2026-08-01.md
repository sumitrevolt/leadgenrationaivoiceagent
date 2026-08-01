# Launch Readiness — 2026-08-01 (Launch-Readiness Commander session)

> Evidence labels: DIRECT_HOST_VERIFIED (probed live host, timestamped) | GIT_VERIFIED | CI_VERIFIED | BROWSER_VERIFIED | CODE-PRESENT | UNVERIFIED.
> Read-only session boundaries honoured: no merge, no deploy, no flag change, no customer-facing action, no DB/billing mutation.

## 0. Fresh truth (all re-derived this session — nothing carried forward)

| Fact | Value | Evidence |
|---|---|---|
| `origin/main` | `48f0577883e51bf0b2e573b81547dabe9afee18e` (PR #207 merge) | GIT_VERIFIED 2026-08-01T14:12Z after `git fetch` |
| Production `/health.version` | `48f05778` — **EQUAL to origin/main tip** | DIRECT_HOST_VERIFIED 14:19:18Z (in-host curl) + external HTTPS |
| Deploy event | 14:12:55Z, canonical `deploy_vps.sh` → `/tmp/dep207.log` ends `DEPLOYED 48f05778 OK`; operator-run (CI deploy-vps run 30702944652 had Build & Deploy jobs **skipped** — Gate only) | DIRECT_HOST_VERIFIED |
| 5-service image parity | app/worker/scheduler/worker-heavy/worker-video ALL `ghcr.io/...:48f05778`, `APP_VERSION=48f05778`, restarts=0, oom=false | DIRECT_HOST_VERIFIED 14:19Z |
| Queues | `celery=0`, `dlq:failed_tasks=0`, `dlq:dead=0` | DIRECT_HOST_VERIFIED 14:19Z |
| CI on `48f05778` | CI ✅, tests ✅, security-scan ✅, deploy-vps gate ✅ (all `push` runs 14:02:20Z success) | CI_VERIFIED |
| Rollback reference | `9bfc2d6f` — image PRESENT on VPS (`docker images`: 48f05778, 9bfc2d6f, 3c843517) | DIRECT_HOST_VERIFIED |
| Soak stream | `/tmp/continuous_monitor_ce14f9ff.log` logs q/dlq/health every 5 min; version flip 9bfc2d6f→48f05778 between 14:12:04Z and 14:17:04Z; **soak clock reset at 14:12Z deploy** | DIRECT_HOST_VERIFIED |
| Open PRs | ONLY #204 (draft, HyperFrames video provider) | GIT_VERIFIED |
| PR #204 head | `5278510`, base main, mergeStateStatus **DIRTY**; only real content conflict = `memory/decisions.md` (append-only); final head has **zero CI runs** (last green CI on `4931710`) | GIT_VERIFIED |
| PR #204 ownership | LIVE session `local_29030ac0` ("HyperFrames video rendering integration") owns worktree+branch; findings transferred to it via session message at ~14:25Z; this session did NOT touch that branch | coordination log |
| Worktrees | main checkout: `main`, clean · `hyperframes-video-rendering-d233cb`: clean, PR #204 (ACTIVE OWNER — preserve) · 2 temp cleanrooms (PR #204 verification scratch — preserve) · this launch worktree | GIT_VERIFIED |

## 1. Runtime flag posture (DIRECT_HOST_VERIFIED 14:19Z — supersedes CLAUDE.md ops-facts of earlier today)

Owner edited `/opt/leadgen/.env` at **13:23:24Z** today (stat mtime), then deployed 14:12Z. Changes vs last recorded posture:

| Flag | Was (2026-08-01 morning) | NOW | Meaning |
|---|---|---|---|
| `SALES_AUTOPILOT_DRY_RUN` | 1 | **0** | autopilot LIVE (not simulation) |
| `SALES_AUTOPILOT_EMAIL_ENABLED` | 0 | **1** | email channel armed |
| `AUTO_EMAIL_OUTREACH` | 0 (by design) | **1** | outreach engine armed |
| `VIDEO_CUSTOMER_REVIEW_ENABLED` | 0 (pending owner) | **1** + `CLIENTS=jiya-makeover` | Jiya video-review canary armed |
| `SELF_IMPROVE_LOOP` | 1 | 1 (cap 120/day) | unchanged |
| `WHATSAPP_AUTO_SEND` | 0 | **0** ✅ | ban-safety preserved |
| `REPLY_AUTO_SEND` | 0 | **0** ✅ | preserved |
| `PLATFORM_DIAL_DAILY` | 10 (owner test-mode 2026-07-31) | **10** | unchanged; calling window+DND gates active |
| `UPI_AUTO_ACTIVATE` | 1 (allowlist `81bd0bbe501d` only) | 1 + same allowlist | Estique-only, fail-closed (PR #203) |
| `DND_FAIL_OPEN` | 0 | **0** ✅ | TRAI fail-closed |
| `SALES_AUTOPILOT_CANARY_BATCH` | 1 | 1 | max 1 item/tick |
| `OPENCLAW_ENABLED` / `ALLOW_RED` | 1 / 0 | 1 / 0 | Stage A GREEN-only |

**Behavioural evidence:** `sales_autopilot/last_tick.json` at 13:55:00Z = `{enabled:true, dry_run:false, processed:0, items:[]}` — engine LIVE but **zero customer-facing actions so far**; worker/scheduler logs 6-12h: 0 sales/outreach/smtp lines. This session changed NO flag.

## 2. Reliability evidence (read-only)

- Celery beat (v5.6.3, `RUN_IN_PROCESS_SCHEDULER=0` → beat is authoritative) restarted with deploy at 14:12:59Z; due-task dispatch observed at 19:45:00 IST and 19:50:00 IST (`staff-flow-cron` twice = two consecutive self-requeued ticks; `staff-growth-15min`, `staff-engineer-sre-hourly`, `staff-onboard-hourly` also dispatched). Label: DIRECT_HOST_VERIFIED.
- DLQs both zero AND separately observable (`dlq:failed_tasks`, `dlq:dead`).
- Disk 74% used / 52G free. Old-image retention working (kept 3 newest tags).
- `leadgen_app_staging` runs an UNTAGGED image (id `42b8c1c0f708`) — known ADR-097 provenance gap, NON-production service, unchanged.
- **WAHA (self-host WhatsApp): session `default` status = `FAILED`, `me:null`** at 14:38Z probe — regression from `SCAN_QR_CODE` recorded in SESSION_HANDOFF earlier today. Owner QR scan will NOT work until the session is restarted/recreated. WS-1 blocked. (Webhook target uses public HTTPS URL — correct host pattern.)

## 3. Browser validation (public journeys, BROWSER_VERIFIED ~14:25–14:40Z)

| Page | Result |
|---|---|
| `/` landing | 200, title correct, 0 console errors |
| `/pricing` | 0 console errors, all resources 200; prices from LIVE API (`/api/marketing/packages`, `/api/billing/plans`): Main ₹1,999 + Combo ₹5,999; **no Growth ₹2,999 leak**; signup modal renders (biz/email/phone/site/pass) |
| `/start` | Intentional alias of `pricing.html` (app/main.py:1611) — signup is in-page modal; NOT a route collision |
| `/audit` | 200, form present, 0 errors, 0 failed resources |
| `/demo` | 200, 0 errors |
| `/voice-agent` | 200, Band A ₹4,999 + annual shown, 0 failed resources |
| `/app/login` | email+password with labels, forgot-password link present |
| `/privacy` | Grievance officer ✓, purge ✓, retention ✓, DPDP ✓ |
| Mobile 375px | `/pricing` + `/privacy`: NO horizontal overflow; body font ≥14px; 9 tap targets <32px height (minor a11y polish item) |
| Service worker | active (scope `/`); public-page content matched non-browser curl (no stale-cache divergence observed today) |

No form was submitted; no payment/OAuth/communication triggered.

## 4. Security findings (this session's own probes)

- **P1 — Gemini API key in `/root/.bash_history` (VPS):** a curl-pipe-to-bash deploy one-liner was run with `GEMINI_API_KEY=<value>` inline; the key value sits in plaintext shell history (also present in that process's env at the time). OWNER ACTION: rotate this key in the 9-key voice pool + remove the history line (`history -d` / edit file). Key value deliberately NOT recorded anywhere by this session.
- P3 — `deploy_vps.sh` was once piped from `raw.githubusercontent.com` to bash — supply-chain-fragile pattern; prefer the checked-out `/opt/leadgen` copy (canonical runbook already does).

## 4b. Local release gates on RC `48f0577` (this worktree ≡ origin/main, run 2026-08-01 ~15:01Z)

| Gate | Result |
|---|---|
| `scripts/prod_check.py` | **PASS** — `[OK] ALL CHECKS PASSED`; 1219 routes; 48 pages 0 wiring gaps; automation 0 gaps; explorer graph 355 nodes/0 orphans; API.md in sync (1243 ops) |
| `pytest tests/test_billing_truth_2026.py` | **15 passed** |
| `scripts/check_secrets.py` | clean (0 changed files vs HEAD) |
| PR #208 (ci-probe on PR #204 head `b6d059a`) | GitGuardian pass; blocking CI contexts pending at 15:02Z — owned by live session `local_29030ac0` |

Coordination note (re-verified 14:43Z): PR #204 owner session `local_29030ac0` RUNNING (last activity 14:43:26Z), head advanced `5278510` → `b6d059a`, opened PR #208 to run blocking CI on that head. This session stays off that branch; Phase-4 verdict will cite its evidence.

## 5. Lane results (parallel read-only audit + research)

_Pending — filled in as the 9 lanes return: security-pr204, security-surface, agent-os, harness, release-infra, frontend-funnel, research-hyperframes, research-celery-gha, research-providers. First dispatch 14:45Z failed wholesale (subagent session limit, reset 20:30 IST); resumed 15:01Z run wf_11388add-232._

## 6. Launch matrix

_Assembled after lane results._

## 7. Owner-action packet

_Consolidated at session end._
