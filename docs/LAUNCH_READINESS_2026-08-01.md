# Launch Readiness — 2026-08-01 (Launch-Readiness Commander session)

> Evidence labels: DIRECT_HOST_VERIFIED (probed live host, timestamped) | GIT_VERIFIED | CI_VERIFIED | BROWSER_VERIFIED | CODE-PRESENT | UNVERIFIED.
> Read-only session boundaries honoured: no merge, no deploy, no flag change, no customer-facing action, no DB/billing mutation.

## 0. Fresh truth (all re-derived this session — nothing carried forward)

| Fact | Value | Evidence |
|---|---|---|
| `origin/main` | `b6ed6f8df2e3af6a6e8d1347313c976de1009d95` (PR #209 docs) — includes `48f05778` | GIT_VERIFIED 2026-08-01T18:55Z after `git fetch` |
| Production `/health.version` | `48f05778` — **behind main by docs-only #209**; app image still PR #207 | DIRECT_HOST_VERIFIED 14:19Z + re-probed 18:57Z external HTTPS |
| Deploy event | 14:12:55Z, canonical `deploy_vps.sh` → `/tmp/dep207.log` ends `DEPLOYED 48f05778 OK`; operator-run (CI deploy-vps run 30702944652 had Build & Deploy jobs **skipped** — Gate only) | DIRECT_HOST_VERIFIED |
| 5-service image parity | app/worker/scheduler/worker-heavy/worker-video ALL `ghcr.io/...:48f05778`, `APP_VERSION=48f05778`, restarts=0, oom=false | DIRECT_HOST_VERIFIED 14:19Z |
| Queues | `celery=0`, `dlq:failed_tasks=0`, `dlq:dead=0` | DIRECT_HOST_VERIFIED 14:19Z |
| CI on `48f05778` | CI ✅, tests ✅, security-scan ✅, deploy-vps gate ✅ (all `push` runs 14:02:20Z success) | CI_VERIFIED |
| Rollback reference | `9bfc2d6f` — image PRESENT on VPS (`docker images`: 48f05778, 9bfc2d6f, 3c843517) | DIRECT_HOST_VERIFIED |
| Soak stream | `/tmp/continuous_monitor_ce14f9ff.log` logs q/dlq/health every 5 min; version flip 9bfc2d6f→48f05778 between 14:12:04Z and 14:17:04Z; **soak clock reset at 14:12Z deploy** | DIRECT_HOST_VERIFIED |
| Open PRs | #204 HyperFrames (draft) · #210 this packet (draft) · #208 ci-probe **CLOSED** obsolete | GIT_VERIFIED 18:56Z |
| PR #204 head | `f040e9afda8b7817a3b4d728ce61b68c06b56121` — includes latest `origin/main`; **MERGEABLE**; blocking CI all SUCCESS | GIT_VERIFIED / CI_VERIFIED |
| PR #204 ownership | Cursor takeover owns worktree `hyperframes-video-rendering-d233cb`; exact-head image chain rebuilt; 3-template hermetic canary IN PROGRESS (beauty+local done, agency encoding) | coordination log 2026-08-01T18:55Z |
| Worktrees | main `b6ed6f8` clean · HF PR #204 @ `f040e9a` · this launch worktree (docs only; runtime `data/*` dirty preserved, not staged) | GIT_VERIFIED |

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

> **SUPERSEDED 2026-08-02 (historical snapshot):** `PLATFORM_DIAL_DAILY` is the boolean
> ON/OFF switch (=`1` prod), NOT a count; the per-run cap moved to `PLATFORM_DIAL_LIMIT=100`
> when platform_dial went FULL CAMPAIGN LIVE. See `docs/context/CURRENT_STATE.md`.

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
| PR #208 (ci-probe) | **CLOSED** 18:56Z — obsolete; #204 head now gets normal `pull_request` CI | GIT_VERIFIED |

## 4c. PR #204 exact-head carry-forward (Cursor takeover, frozen `f040e9a`)

| Gate | Result | Evidence |
|---|---|---|
| Local = remote = PR head | `f040e9a` | `git rev-parse` + `gh pr view 204` |
| Includes latest `origin/main` | yes (`b6ed6f8` merged) | GIT_VERIFIED |
| App image | `leadgen-app:pr204-f040e9a` = `sha256:615f00e3be90…` | docker inspect |
| Video image FROM exact app (not `latest`) | `leadgen-video:pr204-f040e9a` = `sha256:702c2dfac860…`; **20/20 layer prefix match** | RootFS.Layers diff |
| `hyperframes check` ×3 | **PASS** — 0 errors each (warnings only: composition size) | networked in-image run |
| Clean-room approval + HyperFrames suites | **PASS** (pristine `git archive` inside video image, `/opt/venv` pytest) | `_proof/cleanroom_all.log` exit 0 |
| Hermetic 3-template provider canary | **PARTIAL** — beauty `CUSTOMER_APPROVABLE` 1080×1920/30fps/25.4s/8.4Mbps; local mp4+frames written; agency still encoding under `--network none` | container `hfproof3-f040b` |
| Blocking CI on frozen SHA | Lint/secrets · prod_check+pytest · harness-redis · tests · Trivy · GitGuardian = SUCCESS | CI_VERIFIED |
| Jiya real-photo canary | **BLOCKED** (zero consented visual assets) — photo-free brand canary only | CODE + canary photos=0 |

## 5. Lane results

> **Research recovery (Cursor 2026-08-01 ~19:15 IST):** Claude's parallel workflow aggregator returned empty, but all 9 agent results were in `wf_11388add-232/journal.jsonl`. Durable packet: `docs/archive/2026-08/CLAUDE_WEB_RESEARCH_2026-08-01.md` (+ `.json`).

| Lane | Verdict | Notes |
|---|---|---|
| security-pr204 | GREEN | adversarial review PASS; flags OFF; residual P2 hermetic-env secret leak + network_disabled dead control |
| security-surface | AMBER | Gemini key in VPS bash_history (owner); AUTO_EMAIL_OUTREACH 25/day is per-RUN (~275/day if hourly) |
| agent-os | AMBER | 12G/17A/2R; dry-run burned live funnel sequencing; inbound email stop incomplete |
| harness | AMBER | self_improve kill needs worker restart; dead-man alert in-band |
| release-infra | AMBER | `Dockerfile.lock` can bake `data/` phone PII into GHCR (P1); Actions not SHA-pinned |
| frontend-funnel | AMBER → patched in this PR | ₹5,999 was mislabeled voice-only; Compare was dead `#plans`; yearly toggle missing — **fixed on this branch** |
| research-hyperframes | AMBER | pin 0.7.87 = latest; Apache-2.0; `--no-sandbox` hardcoded upstream; Linux canary still in progress on #204 |
| research-celery-gha | AMBER → partial patch | Celery posture strong; set `worker_cancel_long_running_tasks_on_connection_loss`; Actions SHA-pin still open |
| research-providers | AMBER → patched in this PR | Groq Llama 8B/70B shut **2026-08-16**; dead Qwen3-32B+Kimi removed; migrated to `openai/gpt-oss-20b` / `120b` + `qwen/qwen3.6-27b` |

## 6. Launch matrix

| Dimension | Ready? | Evidence |
|---|---|---|
| App health / provenance | YES | `/health` healthy `48f05778` |
| Billing truth | YES | 15/15 billing-truth; INV path unchanged |
| Protected send gates | YES (code) | WA=0, reply=0, UPI allowlisted, dial test-cap — **prod dial=10 is owner test-mode, not code default** |
| Agent Runtime fleet | PARTIAL | 12 pilots canary-ready; master flag OFF; 2 voice RED frozen |
| Video / Creative OS | PARTIAL | PR #204 additive flags OFF; exact-head proof almost done; Jiya photo gate owner-blocked |
| WAHA | NO | session FAILED — owner QR / recreate |
| Estique 2nd customer | WAIT | owner password reset + PAID |
| Merge #204 | WAIT | finish agency canary + update PR body; owner merge decision |
| Deploy newer SHA | NO | not requested; docs-only main tip not a deploy reason |

**Verdict now:** `PARTIAL` — safe engineering packet ready; customer-facing launch still owner-gated.

## 7. Owner-action packet

1. **Rotate** Gemini key that landed in VPS `/root/.bash_history`; scrub history line.
2. **WAHA:** recreate/relink session → reply `WAHA CONNECTED` (AUTO stays 0 until boundary proof).
3. **Estique:** private password reset → Billing ₹1,999 → reply `PAID` (never paste password/OTP in chat).
4. **Jiya video photo canary:** register consented visual assets before any real-photo HyperFrames canary; until then photo-free only.
5. **PR #204 merge:** only after Cursor posts final exact-head canary PASS on `f040e9a` (or successor SHA if HEAD moves); flags stay OFF.
6. **Do not** flip `WHATSAPP_AUTO_SEND`, raise dial beyond test allowlist, or enable `AGENT_RUNTIME` fleet-wide without one-pilot arming.
7. **Optional:** confirm intent of `CREATIVE_OS_ENABLED=1` in prod vs inert HyperFrames provider flags.

### Canonical deploy / rollback (when owner authorizes — NOT run this session)

```bash
# Deploy exact SHA (VPS)
cd /opt/leadgen && setsid nohup bash scripts/deploy_vps.sh <40-hex-sha> > /tmp/dep.log 2>&1 &
# Rollback image reference currently proven present
# APP_VERSION=9bfc2d6f  (or prior known-good tag on host)
```

### Explicit non-actions this session

Not merged · not deployed · flags not flipped · nothing sent/published · no customer mutations · no unconsented assets used.
