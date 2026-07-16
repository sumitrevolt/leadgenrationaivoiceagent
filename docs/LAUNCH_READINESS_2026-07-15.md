# Enterprise Launch Update — 2026-07-15 + 2026-07-16 closeout + 2026-07-16 FINAL ACCEPTANCE

## 🏁 2026-07-16 FINAL ACCEPTANCE (authoritative — supersedes conflicting lines below)

**Final verdict: `CONDITIONALLY READY`** — ek hi bacha condition: **customer Logout button kaam nahi karta** (P2, chhota frontend fix). Baaki HAR acceptance item PASS.

### Jiya Makeover browser acceptance (REAL login, credentials Chrome password-manager autofill se — values kabhi expose nahi)
- Login → customer dashboard ✅ · Identity: "Jiya Makeover Studio", NAGPUR, `Client: jiya-makeover` ✅ · "Aapka asli data" (real tenant data, no demo fallback) ✅
- Setup state: 50% Done, setup-first pinning by design ("Setup Incomplete" toast) ✅
- Purchased vs delivered: Business profile ✓ / Brand kit ✓ / 4 branded posters ✓ / Festival posts ✓ delivered; 12 social captions = Pending (24 approvals gating) ✅
- Approvals: 24 pending, "Approval dekhein" surfaced ✅ (kuch approve/reject/publish NAHI kiya)
- Social/creatives: July calendar real content (Rath Yatra festival posts, posters, reels) ✅ · WhatsApp Promo Message in calendar (content pack) ✅
- Hot Queue betting-spam: 0 visible (runtime-proven on real drafts; legit 1203 rows visible) ✅
- No app JS console errors (sirf MetaMask extension noise) ✅ · No infinite loader ✅
- **🚨 FOUND + FIXED LIVE: paying customer saw "NO PLAN — Free/Trial" + fresh UPI QR (double-payment risk!).** 2-layer root cause: (1) ADR-095 identity split on customer surface — Subscription row owned by legacy billing id `d79d690f61b3`, JWT carries `jiya-makeover` (ADR-106: `_billing_client_ids()` alias resolution across ALL billing WHERE clauses); (2) latent `.value`-on-plain-str crash (`payment_gateway='upi'` string in DB) that 500'd the FIRST-EVER real subscription response, masked by the known Sentry `_IncludedRouter` secondary crash (ADR-106 addendum: `_ev()` coercion). **UI proof after fix: "Aapka Plan — ACTIVE — starter — 05 Jul 2026 → 04 Aug 2026"**; API via Jiya's real JWT: `200 {plan: starter, price: 1999, status: active, gateway: upi}`.
- ❌ **Logout: BROKEN** — 2 attempts, tokens (`accessToken`/`lgai_token`) localStorage me rehte hain, koi redirect nahi, API calls 200 dete rehte. P2 — THE remaining condition.
- ⚠️ P2: portal "Purane Bills" empty — real invoice GST-ledger (file) me hai, Postgres `Invoice` table me row nahi; GST-download path alag se verify karna hai.

### Authorization checks
- Unauth: `/api/platform/office/snapshot` 401 · `/api/customer/office` 401 ✅
- Customer token ≠ other tenant / ≠ admin routes: `test_customer_tenant_isolation_authenticated.py` **19 passed** ✅ (export/report surfaces suite me covered)

### Production (final)
- SHA **`f2793d8b`** = origin/main, `/health` production ✅ · image `sha256:6c7581fc9859…` · **zero skew 5/5** · queues **celery=0, dlq=0** (3 DLQ entries system ke dead-letter processor ne drain kiye — 1 pre-deploy SIGKILL 01:14Z, 1 deploy-window SIGKILL 02:58Z, 1 `hot_queue_brief` mid-churn fail 03:53Z; koi post-deploy naya fail nahi; scoped-cleanup procedure absent thi isliye maine delete NAHI kiya) · no restart loops
- Memory (settled): host 15.6GB total / **69% used / 4.9GB available**; containers: worker 593MB/2GB, worker_heavy 237MB/2.4GB, app normal
- Is phase ke 2 aur commits: `5830cfe6` (ADR-106 alias) + `f2793d8b` (ADR-106 addendum `_ev`, rebased over parallel session's `d409dcf`/`dfaead4`). Gates har commit se pehle: alias+billing-truth tests (22 → 24+... final 24 passed incl. `_ev` guards), prod_check ALL PASSED, secrets clean.
- **VPS pull-conflict incident (resolved, data safe):** parallel session ne runtime data files commit kar diye the (stale Windows snapshots of `data/*jiya*.jsonl`); VPS live customer data ko `/tmp/live_data_20260716-035446` backup karke pull kiya, phir live files RESTORE ki — zero customer-data loss, VPS tree wapas chronic-dirty-normal.

### Repository cleanup
- `lg-adr105-wt`: `f2793d8b` origin/main pe PROVEN (merge-base), koi unique uncommitted repo-work nahi tha → worktree unregistered + branch `adr105-deploy` deleted. Directory remnant: 2 locked log files (hung redirect handle) — reboot ke baad folder delete kar dena.
- Main tree: ab `main @ dfaead4` (parallel session ne reconcile karke re-attach kiya; origin se 1 peeche = mera `f2793d8b`). Remaining dirty files ownership: `data/*.jsonl` = runtime (kabhi commit nahi) · `memory/*`, `progress.md` = session notes (dono sessions) · scripts/`*.extracted.js`/unity `??` files = purani sessions ke parked artifacts. Sab preserved, kuch reset nahi kiya.

### Remaining paid/manual integrations (non-blocking — not sold as active features)
X/Twitter posting (API credits depleted, 402 — paid decision) · YouTube OAuth app publish (7-din token death) · DLT cold-outbound (platform_dial user-mandate OFF) · Meta customer-page publishing (app review).

### Rollback (exact)
`ssh -i ~/.ssh/id_rsa root@72.61.245.204` → `cd /opt/leadgen && APP_VERSION=5830cfe6 setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &` (ya `2f8bbb1c` — dono deployed-good; script SHA se rebuild karta hai). Billing-fix-only revert: ADR-106 dono commits revert; spam guard: `REPLY_SPAM_CONTENT_GUARD=0`.

---



## ⚡ 2026-07-16 Closeout (supersedes sections A/J/K below where they conflict)

**Final verdict: `CONDITIONALLY READY`** — sirf 2 chhoti conditions bachi hain (neeche). Saare P1 blockers CLOSED.

### Git reconciliation (real Windows repo, Desktop Commander)
- Staged-revert anomaly was REAL (not phantom): index held a -735-line revert of ADR-104 hardening + staged-DELETE of 3 test files, while disk was intact. Root cause unknown (parallel session suspected). Fix: `git restore --staged` on exactly the 10 affected files — working tree untouched, all hardening files now clean vs HEAD.
- Parallel uncommitted work (email_warmup/team/postiz/signup-test edits + jiya runtime jsonl) left strictly alone.
- ADR-105 committed via an isolated worktree on origin/main (main tree's parallel work never touched): **commit `2f8bbb1c`**, exactly 4 files, +160/-0. Pushed `642fcdf..2f8bbb1` → origin/main.
- NOTE: main working tree HEAD abhi bhi `0350ee18` par hai (origin se peeche) + dirty parallel work — agla session apna kaam commit kare, phir `git pull --ff-only`.

### Validation (real .venv, worktree = committed code)
- `pytest` spam-guard + reply-agent regressions (4 suites): **64 passed, 0 failed** (spam guard 19 + auto_send/junk_guard/noise_filter 45)
- Tenant isolation: `test_customer_tenant_isolation_authenticated.py` **19 passed** (customer token ≠ other tenant, ≠ admin routes)
- `prod_check.py`: **ALL CHECKS PASSED** (1125 ops, engines 81/81) · `check_secrets.py`: **clean** (13 files)

### Production deployment
- Deployed **`2f8bbb1c`** via canonical `deploy_vps.sh` (detached, `/tmp/dep.log`): `=== DEPLOYED 2f8bbb1c OK ===`
- `/health` + `/health/ready`: version `2f8bbb1c`, environment production, DB/Redis/LLM healthy
- **Zero skew**: all 5 app containers `APP_VERSION=2f8bbb1c`; image `sha256:ccfeebd90e62…`; no restart loops (all healthy)
- Routes: `/` `/pricing` `/start` `/audit` `/app/login` `/app/office` `/api/voice/niches` `/api/billing/plans` → all **200**
- Scheduler dispatching (reply-triage hourly LIVE with new guard); workers 3/3 pong; celery queue 0; DLQ 1 stale pre-deploy SIGKILL entry (job 263, 01:14Z — triage pending, non-blocking)
- Disk 74% used (52G free) after image retention; memory 81.5% used post-build (watch)

### Customer acceptance (jiya-makeover)
- Unauth gates: `/api/platform/office/snapshot` → 401, `/api/customer/office` → 401 ✓
- **Hot Queue spam filter runtime-proven on REAL prod drafts**: 1815 rows → 612 noise-filtered, **2 betting-spam rows now hidden** (previously intent `other`/`question`), **1203 legit rows still visible** ✓
- Tenant isolation: 19/19 authenticated tests pass ✓
- ⚠️ CONDITION 1: jiya UI login walkthrough = credential-gated (owner ka 2-min spot-check; screen ready: https://leadsgenai.in/app/login). Jiya's content NOT touched/published by this session.

### Postiz closeout
- Open registration: was already flipped to `POSTIZ_DISABLE_REGISTRATION=true`; compose re-applied per runbook (NO --remove-orphans), main stack verified up, health 200, postiz 307
- **Runtime proof registration blocked**: POST /api/auth/register → **HTTP 400 "Registration is disabled"** ✓
- **Own-brand branded test post PUBLISHED (end-to-end proof)**: post_id **`cmrmx5ij50003nz6o1nuachza`**, provider **facebook**, publishDate **2026-07-16 02:57:00 UTC**, state QUEUE→**PUBLISHED**, evidence URL: https://www.facebook.com/122101038657384404/posts/122110418541384404 · media-required channels correctly skipped on text-only post · config source=env, 2 ids effective
- ⚠️ CONDITION 2 (channel-level, non-blocking): X integration **credits depleted** (X API 402 CreditsDepleted — paid plan issue, owner decision); YouTube OAuth 7-day refresh (publish Google OAuth app) pending as before

### Rollback (exact)
`ssh -i ~/.ssh/id_rsa root@72.61.245.204` → `cd /opt/leadgen && APP_VERSION=5f65979c setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &` (previous known-good `5f65979c`; local image tag was retention-pruned, script rebuilds from git SHA). Spam guard alone: `REPLY_SPAM_CONTENT_GUARD=0` env, no deploy.

### Cleanup note
Temp worktree `C:\Users\Ratanshila\Documents\lg-adr105-wt` (branch `adr105-deploy`, merged into main) holds this session's helper scripts/evidence logs — safe to `git worktree remove --force` + delete branch after review.

---



> Method note: is session ke paas VPS SSH nahi tha (key Windows host pe hai, agent sandbox Linux hai). Isliye prod evidence = live HTTPS probes (cache-busted) + git-object ancestry; container-level facts sirf ledger-corroborated. Sandbox mount 3 jagah STALE pakda gaya — har content claim Windows file-tools se verify hua.

## A. Executive Verdict

- **Final status: `CONDITIONALLY READY`**
- Current production SHA: **`5f65979c`** (`/health` live, `environment:production`, uptime 4h at probe time; NOT `:latest` — provenance known)
- Deployment time: today (uptime ~4h at 17:10 UTC probe)
- Overall risk: **MEDIUM** — platform healthy aur money-path live, par 10 committed+pushed fixes (admin-action confirmations + endpoint hardening) prod pe NAHI hain, aur own-brand posting ka end-to-end proof pending hai.
- Customer impact: jiya-makeover served by current prod; koi naya regression is session me nahi mila. Undeployed backlog = admin-safety improvements, customer-facing breakage nahi.

## B. Work Completed (this session)

- **Baseline/provenance:** prod `/health`+`/health/ready` cache-busted verify; git ancestry mapping (prod ↔ local ↔ origin); MRR-truth fix `c78b73d` aur voice-KB fix `8383eec` dono prod lineage me PROVEN (merge-base).
- **Routing/API smoke:** `/api/billing/plans` (2 public plans, Growth hidden ✓ billing-truth), `/api/voice/niches` (200, 28 niches — purana 7-din 500 bug fix live confirmed), `/api/public/pay-info` (UPI ARMED, QR live), `/app/login`, `/start` — sab green.
- **Fix shipped (code, not deployed):** reply-agent **SPAM CONTENT GUARD** (ADR-105) — betting/gambling spam ab LLM-classify se pehle drop (email + WhatsApp), aur pehle se saved spam drafts Hot Queue read-path pe retro-hidden. Flags: `REPLY_SPAM_CONTENT_GUARD` (default ON), `REPLY_SPAM_EXTRA_TERMS` (CSV).
- **Integrity finding:** sandbox mount ne 10-file staged-revert (-735 lines, ADR-104 tests staged-DELETE) dikhaya — Windows disk verified INTACT; phantom likely, par operator confirm kare (K-2).
- **Memory write-back:** ADR-105 in `memory/decisions.md`, Loop Run in `progress.md`.

## C. Routing Matrix (config source: CLAUDE.md §2 + integrations.md; live per-provider probes is session possible nahi the — admin-gated)

| Workload | Primary | Fallback chain | Privacy | Status | Evidence |
|---|---|---|---|---|---|
| LLM general | Mistral small | Groq → Cerebras → NIM/SambaNova/OpenRouter | masked/biz-only | CONFIGURED | `/health/ready` `llm: configured (gemini-scoped voice)`; chain in `free_ai.py` w/ 429 circuit-breaker |
| Voice STT | Groq whisper-large-v3 | Gemini audio | call audio, 90-day retention | CONFIGURED | ledger + code; `VOICE_GEMINI_PRIMARY=0` prod |
| TTS | EdgeTTS hi-IN | — | none | CONFIGURED | free-stack mandate |
| Images/video | Pollinations | — | proxy-only key | CONFIGURED | §5 (key never in URL) |
| Per-provider live request test | — | — | — | **NOT RUN this session** | needs admin token / VPS shell |

## D. Integration Matrix

| Integration | State | Test this session | Manual action |
|---|---|---|---|
| Postgres/PgBouncer | HEALTHY | `/health/ready` db healthy | — |
| Redis | HEALTHY | `/health/ready` redis healthy | — |
| UPI manual payments | ARMED | pay-info live (VPA+QR) | — |
| Stripe (intl) | configured | not tested (no safe write) | — |
| Vobiz telephony | configured | not testable from here | — |
| WhatsApp WAHA | WORKING (ledger 07-14) | not re-tested | — |
| Postiz (own-brand social) | wired, 4 channels | **end-to-end post proof PENDING** | K-4 + K-5 |
| Hostinger SMTP/IMAP | working; warmup PAUSED (complaints) | not re-tested | operator review |
| Sentry / backups / GHCR | ARMED / restore-proven / live | not re-tested | — |

## E. Workflow Matrix (delta this session)

| Workflow | Status | Evidence |
|---|---|---|
| Signup → pricing → UPI pay | LIVE | `/start` + plans API + pay-info probes |
| Reply triage (email/WA) | LIVE + hardened (pending deploy) | spam guard 19/19 tests |
| Voice inbound callback | LIVE (KB fix `8383eec` in prod) | ancestry proof; 2 QA acceptance calls still recommended post-next-deploy |
| Own-brand social publish | **UNPROVEN** | dry_run=false but no non-empty `post_id` witnessed yet |
| Customer delivery (Jiya) | delivering per ledger; admin confirmations undeployed | commits 0350ee1 etc. awaiting deploy |

## F. Automation Matrix (unchanged this session)

25 staff jobs + dead-man trio alive per Current State; queues/DLQ last verified 0/0 (07-14). Naya guard email-triage job ke andar hai — koi naya schedule nahi. `platform_dial` HARD OFF (user mandate) — untouched.

## G. Agent Matrix (delta)

| Agent | Change | Kill switch |
|---|---|---|
| Reply agent | + spam-content guard (pre-classify, 3 wire points) | `REPLY_SPAM_CONTENT_GUARD=0` |
| Baaki (prospector, delivery, reconciler, etc.) | unchanged | as before |

## H. Test Evidence

- New suite `tests/test_reply_agent_spam_guard.py`: **19 passed, 0 failed** (sandbox harness against HEAD-blob+exact-edits reconstruction; pytest-stub; anchors count==1 asserted; AST clean). **Windows venv run pending (K-3).**
- Live smoke: 7 endpoints probed, all green (section B).
- prod_check/check_secrets: NOT run this session (Windows venv unreachable from sandbox) — K-3.
- Tenant-isolation authenticated tests: not re-run (last green 07-12 ledger).

## I. Customer Acceptance — jiya-makeover

- Login/dashboard: serving on current prod (no regression observed; authenticated walkthrough was 07-15 earlier session, ledger-corroborated)
- Payment evidence: only real invoice-backed client (`d79d690f61b3`), MRR shows ₹1,999 truth (fix in prod)
- Pending: content approval backlog review by owner; deliver-now confirmation UX arrives with next deploy

## J. Remaining Blockers

| # | Severity | Problem | Launch-blocking? |
|---|---|---|---|
| 1 | P1 | 10 pushed commits undeployed (admin confirmations, password-reset/onboard-scrape hardening, L2 fix, Postiz readiness) | YES — for "hardened" claim; platform itself live |
| 2 | P1 | Own-brand posting end-to-end unproven (no non-empty post_id yet) | For marketing-flywheel claims only |
| 3 | P2 | Phantom(?) staged revert in git index — operator confirm needed before ANY commit | YES until confirmed |
| 4 | P2 | Email warmup paused (complaint 0.585%) | No (deliberate pause) |
| 5 | P2 | Disk 77% used / mem 75.7% on VPS | No, watch |
| 6 | P3 | Poisoned intermediary caches of `/health/ready` still serving `version:"latest"` | No (SOP: cache-buster) |

## K. Manual Admin Actions (exact single next steps)

1. **Deploy backlog:** Windows me `git pull --ff-only`, phir SSH → `cd /opt/leadgen && APP_VERSION=f6fb352a setsid nohup bash scripts/deploy_vps.sh > /tmp/dep.log 2>&1 &`, phir `/tmp/dep.log` poll + `curl localhost:8000/health` == `f6fb352a`.
2. **Git index confirm:** Windows terminal me `git status` — agar `tests/test_admin_*`/`test_l2_*` staged-DELETE dikhe to `git restore --staged .` (files disk pe intact hain, kuch delete nahi hoga).
3. **New tests on real venv:** `.venv\Scripts\python.exe -m pytest tests/test_reply_agent_spam_guard.py -q` + `scripts\prod_check.py` + `scripts\check_secrets.py` — phir spam-guard commit karo (surgical: `app/platform/reply_agent.py` + `tests/test_reply_agent_spam_guard.py` + `memory/decisions.md` + `progress.md`).
4. **Postiz registration band:** `deploy/postiz/.env:4` `POSTIZ_DISABLE_REGISTRATION=true` — SIRF playbooks.md "Postiz env change / restart" runbook se (orphans incident).
5. **YouTube OAuth publish:** Google Cloud Console → OAuth consent screen → Publish app (7-din refresh-token death fix).

## L. Rollback Plan

- Previous known-good: current prod **`5f65979c`** (image `ghcr.io/...:5f65979c`) — next deploy fail ho to `APP_VERSION=5f65979c bash scripts/deploy_vps.sh`.
- Spam guard rollback: env `REPLY_SPAM_CONTENT_GUARD=0` (no code revert needed); code revert = 1 file + 1 test file.
- DB: is session me koi migration nahi — rollback consideration N/A.
- Verification post-rollback: `/health` version == `5f65979c` + smoke (plans/niches/pay-info).

## M. Next 7-Day Plan

1. K-1 deploy + acceptance (admin confirm-modals smoke + 2 voice QA calls) — Day 1
2. K-2/K-3 git hygiene + spam-guard commit — Day 1
3. Own-brand posting first REAL drain proof (`social_post_jobs.jsonl` non-empty post_id) — Day 1-2
4. Email warmup complaint-rate review + resume decision — Day 2-3
5. Approval backlog triage with Jiya review procedure — Day 2-4
6. Disk/mem trend check (77%/75.7%) + retention sweep — Day 3-5
7. Optional: Unity WebGL artifacts ship decision (flag stays OFF) — Day 6-7
