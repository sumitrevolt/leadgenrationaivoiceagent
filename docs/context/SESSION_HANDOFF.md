# SESSION_HANDOFF

## 2026-08-09 — all-worktrees integration PR #295

- Branch `integration/all-worktrees-20260809` was created fresh from `origin/main` and pushed.
- PR: https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/295
- Integrated clean active branches: capacity containment, dial/DLQ truth, CodeQL/image security, daily video, admin hardening, and PR-factory pilot.
- Preserved dirty tracked/staged work through backup refs:
  - `refs/backup/pre-merge-all-1786262374-current`
  - `refs/backup/pre-merge-all-1786262374-admin-nav`
  - `refs/backup/pre-merge-all-1786262374-buzz`
- Generated DB/WAL files and nested repository copies were excluded and remain untouched in their source worktrees.
- Evidence: targeted 18-file regression command exit 0 (one Windows symlink privilege skip); `prod_check.py` ALL PASSED; redacted scan 97 changed files / 0 findings; lints clean.
- No deploy or production flag change. Original worktrees and backup refs remain available.

---

## Last session — 2026-08-09: daily video producer (ADR-166)

**Prod probed live:** `/health` = `3cd95ba2`, equal to `origin/main`. Any `33651cfc` / `084cd990`
still quoted in other context docs is stale — re-probe before asserting a SHA.

**What the owner reported:** "daily posting videos not a proper setup; advanced videos not running;
old setup not running either." All three had *different* causes — verified on the host, not assumed:

1. Classic path was running, but on a **5-day** interval (`VIDEO_AD_INTERVAL_DAYS` unset) **and**
   silently budget-skipped inside the `content` mega-job → real 15-day generation gap (2026-07-22
   → 2026-08-06). `_run_content_engine` swallows budget exhaustion with no log naming the engine.
2. Advanced path never ran: `CREATIVE_PROVIDER_HYPERFRAMES_ENABLED` unset, Node/Chrome toolchain
   only in the un-applied `Dockerfile.video` image, and **no scheduler producer existed at all**.
3. 32/39 records stuck at `pending` review with no backpressure on generation.

**Bonus decisions made under owner authority (both evidence-driven, both shipped):**
1. *Budget-skipped engines are now observable.* `_run_content_engine` swallowed budget exhaustion
   with no exception and no log naming the engine. Prod: `content` blew its 420s budget on 15
   CONSECUTIVE daily runs (2026-07-18 -> 2026-08-01). Now logged-before-persisted, folded into
   `health().ok`, and shown in the Aaj tab.
2. *The CUSTOMER approval backlog is now owner-visible.* `approvals_bridge` (source of
   `needs_decision`) has zero reference to `content_approval`, so the queue that decides whether a
   video ever reaches a customer was counted by nothing - hence 32 pending, 4 published, page green.

**Shipped (PR #294, flags OFF):** `app/marketing/daily_video.py` + own beat job
`staff-daily-video-daily` (09:45 IST) + `daily_video_client_task` on the video queue + admin
`daily-status`/`daily-run` + `run_cycle` cadence-ownership deferral + 4 missing flags registered.
122 targeted tests green, `prod_check.py` PASS, `check_secrets.py` clean, ruff clean on changed files.

**MERGED + DEPLOYED 2026-08-09:** PR #294 -> prod `/health` = `d1b106b2`, 5/5 services zero skew,
kill-fence opened and closed cleanly (`.env` byte-identical to its backup), queues at baseline.
All `DAILY_VIDEO_*` flags stayed unset, so the producer is INERT and the deploy changed nothing.

**Operator error worth remembering:** the fence-closing recreate was run without `APP_VERSION`,
so compose used `${APP_VERSION:-latest}` and prod sat on the `:latest` image (`266d772a`) for
~55s until `/health.version` exposed it. Corrected with `APP_VERSION=d1b106b2 docker compose ... up -d`.
ANY manual recreate needs an explicit `APP_VERSION` - the runbook now spells this out.

**Next agent, start here:**
- Owner action = Stage 1 of `docs/runbooks/RUNBOOK_DAILY_VIDEO.md` (code IS deployed, flags OFF).
- The advanced engine needs an **image build + compose overlay + `CELERY_VIDEO_QUEUE=1`**, not a
  flag flip. Do not promise "advanced is on" from a flag alone.
- Clearing the 32 pending reviews is a prerequisite — `DAILY_VIDEO_MAX_PENDING=2` will correctly
  refuse to generate for a backlogged client.
- Do **not** change `packages.py` to say "daily" until a week of delivery is evidenced; if you do,
  `tests/test_billing_truth_2026.py` moves in the same commit.
- Housekeeping: `POSTIZ_API_KEY` was visible in a plain `printenv` grep during this session's
  read-only prod probe. Value not recorded anywhere in the repo, but consider rotating it and
  filtering secrets out of future env probes.
﻿# SESSION_HANDOFF — 2026-08-08 AWAITING OWNER LOGIN → #282

## 2026-08-08 00:15 IST — Standing by for #3 one-shot

**Owner steps (order matters):**
1. Login → session open rakho
2. Cursor: **#282 merge + deploy** (sirf jab owner bole login-ready)
3. Deploy ke baad seedha `/app/admin` — login MAT

Reflex login = VOID `#3`. Deploy result ke baad Claude confirm karega.
Phir P0 owner: Vobiz rotate + GTM (infra ≠ 2nd customer).

`#2` ✅ DONE · `#4` wait · flags triage no

---
# SESSION_HANDOFF — 2026-08-07 ADMIN DECISION + WAVE1

## 2026-08-07 23:55 IST — Admin priority (Cursor) + fresh verify

### Admin decision (LOCKED — max 3 streams)

| P | Item | Owner | Action |
|---|---|---|---|
| P0 | **Vobiz token rotate** | **OWNER** | Portal rotate — TRAI/paisa risk; agents cannot finish |
| P0 | **GTM Hot Queue → 2nd paid** | Owner + Cursor | Sprint goal; infra ≠ revenue |
| P1 | Harden wave1 code | **Cursor** | branch `fix/admin-harden-wave1` — Maps alias + foot-gun + quarantine gate |
| P1 | `#3` session-survive | Owner browser | **Before next deploy: login once; after deploy: NO login, open `/app/admin`** |
| P2 | `#2` graphify collision | Claude | `extract app --force --code-only` + mtime |
| P2 | `#4` reply_agent row | wait | event-gated |
| PARK | 263 unknown flags | later | triage pack, not tonight dump |
| PARK | Loki ingest | later | Loki ready but **0 samples / 5m**; **no promtail** container — root cause |
| PARK | DLQ=3 | later | still `TimeLimitExceeded(600)` ×3 — true |
| PARK | PII git history | OWNER | live file gone; history still has `prospect_leads_export.csv` |
| PARK | Postgres rotate | OWNER | planned not executed |

### Fresh verify (2026-08-07 DIRECT_HOST)

| Claim | Result |
|---|---|
| `/health` | `42493e3f` healthy |
| `dlq:dead=3` | **TRUE** TimeLimitExceeded(600)×3 |
| Loki ingest dead | **TRUE-ish** — ready + labels OK, **0 samples**; no promtail |
| Qdrant fail_rate 1.0 | **NOT re-proved tonight** — `qdrant:6333` HTTP 200 from app net |
| GoogleMapsClient missing | **TRUE** ImportError; `UDYAM_PIPELINE=1` → Maps enrich dead → OSM only |
| TENANT_QUARANTINE decorative | **TRUE for mutate** — `quarantine_enabled()` unused by mutate path (fixed in wave1) |
| SELF_IMPROVE foot-gun | **TRUE** — prod `SELF_IMPROVE_LOOP=1`; script still forced `0` (fixed in wave1) |
| PII csv live | **FALSE** — no live file; history commit remains |
| HARD_OFF | `0` (ADR-171) |

### Wave1 files (tests 34 green)
`google_maps.py` alias · `vps_enable_automation_max_flags.py` · `tenant_quarantine.py` + tests

**Deploy gate for #3:** owner must be logged in *before* this (or any) next deploy; first `/app/admin` load = decisive.

---
# SESSION_HANDOFF — 2026-08-07 SESSION CLOSE

## 2026-08-07 23:30 IST — Final ledger

| # | Status | Evidence |
|---|---|---|
| Master Blueprint | ✅ LIVE | PR #276, admin hrefs 0→2 |
| Automation Max | ✅ PROVEN | 43 jobs, 5 families today |
| #1 doc↔prod drift | ✅ CLOSED | ADR-169 + ADR-172 |
| #2 graphify | ⏸ PARTIAL | 4/4 tools OK; blind spot §G; collision OPEN (Claude: `extract app --force --code-only`, then mtime) |
| #3 admin logout | ⏸ PARTIAL | revoke 200→401 PROVEN; session-survive **next deploy only** |
| #4 reply_agent | ⏳ event-gated | absence ≠ fail |

Prod `42493e3f` · 5/5 · HARD_OFF=0 (ADR-171) · `.env` Claude-untouched.
Falsified-list rule: ek observation ≠ cause — check who produced the observation.

### #3 decisive test — ONE SHOT (do not void)

**After next deploy: LOGIN MAT KARNA.** Seedha `/app/admin` kholo.

| Result | Meaning |
|---|---|
| Panel data ke saath khula | **PASS** → `#3` full tick |
| `/app/admin-login` redirect | **FAIL** → `adminAuthBoot` retry kaafi nahi |

Agar deploy ke baad pehle login ho gaya (kisi bhi agent/reflex se) → **test VOID** (naya token; survival unknown; false-pass risk). Pehla admin page-load hi asli evidence — ek mauka.


---
# SESSION_HANDOFF — 2026-08-07 PR #281 ACCEPTANCE

## 2026-08-07 23:15 IST — #281 LIVE + acceptance PARTIAL

| Item | Evidence |
|---|---|
| Prod SHA | `42493e3f` · 5/5 skew · HARD_OFF=0 (ADR-171) |
| Test 1 | PASS — access token has `jti`+`iat` (UUID-len; values never printed) |
| Test 2 | PASS — same token: flags 200 → logout 200 → flags **401** |
| #3 status | **PARTIAL** — revoke PROVEN; session-survival next-deploy only |
| #1 | ADR-172 closed |
| #2 | Graphify `affected` — Claude (Desktop Commander) |
| #4 | first real inbound → `source=reply_agent` (event-gated) |

**Next deploy checklist:** open `/app/admin` WITHOUT re-login — that alone greens the boot-race claim. Test-2 logout tonight = expected.

---
# SESSION_HANDOFF — 2026-08-07 FINAL LIVE

## 2026-08-07 21:35 IST — ADR-171 ARMED + WI-CP2 + #276 all LIVE

| Item | Evidence |
|---|---|
| Prod SHA | `85b856f8` (uptime advancing) |
| Auto-send | HARD_OFF=0 · MASTER=1 · enabled=**True** (ADR-171) |
| WI-CP2 | PR #278 MERGED+DEPLOYED (interaction_log outs) |
| #276 MB door | admin Master Blueprint count **4** (kept) |
| Calling | VLK=0 · 5/5 skew 0 |
| Kill lever | `REPLY_AUTO_SEND_HARD_OFF=1` still documented |

Open: prove next real auto-send writes `interactions` source=reply_agent; SELF_IMPROVE_LOOP / CONTENT_APPROVAL_AUTO drifts.

---
# SESSION_HANDOFF — 2026-08-07 ADR-171 re-arm + WI-CP2

## 2026-08-07 21:00 IST — Owner reaffirm: auto-send ARMED (ADR-171)

**Conflict resolved:** Cursor briefly executed Option A (ADR-170 HARD_OFF=1). Owner then clarified auto-send stays on. **Re-armed:** HARD_OFF=0 · enabled=True @ `7ab5fe55`. Backup `.env.bak-reply-rearm-20260807_152441`.

**Already LIVE (skip):** PR #276 Master Blueprint — admin MB count 4 at `7ab5fe55`.

**In flight:** PR #278 WI-CP2 interaction-log (+ ADR-171 docs) — P0 while armed.

**Manifest:** SAFETY_INVARIANT defaults unchanged (fresh deploy fail-closed).

---
# SESSION_HANDOFF — 2026-08-07 LIVE

## 2026-08-07 20:50 IST — HARD_OFF + #276 BOTH LIVE

**Owner decision (admin, no ask):** Option A containment + ship Master Blueprint door.

| Item | Evidence |
|---|---|
| Prod SHA | `7ab5fe55` (uptime advancing, cache-bust curl ×2) |
| HARD_OFF | `1` · `_reply_auto_send_enabled()=False` · ADR-170 supersedes ADR-169 |
| VLK | `0` restored (calling LIVE) |
| Skew | 5/5 `APP_VERSION=7ab5fe55` |
| Acceptance | `/app/admin` Master Blueprint count **4** (was 0) |
| Backups | `.env.bak-reply-hardoff-20260807_150617` · `.env.bak-postdeploy276-killrestore-20260807_151859` |

Open drifts (not tonight): SELF_IMPROVE_LOOP ON vs pin 0; CONTENT_APPROVAL_AUTO ON (auto-submit). 263 unknown_requires_review flags.

---
# SESSION_HANDOFF — 2026-08-07 owner-exec: HARD_OFF + #276

## 2026-08-07 20:40 IST — OWNER DECISION EXECUTED (Cursor + Cloud)

**Verdict (admin):** Option A — restore `REPLY_AUTO_SEND_HARD_OFF=1` to manifest default. ADR-170 SUPERSEDES ADR-169 (premature OWNER-ARMED docs withdrawn).

**Containment PRODUCTION-PROVEN:**
- Backup `.env.bak-reply-hardoff-20260807_150617`
- Recreate app+worker `APP_VERSION=a08dd5e9`
- Prove: HARD_OFF=1, MASTER=1, `_reply_auto_send_enabled()=False`
- `/health` healthy after recreate

**PR #276:** MERGED `7ab5fe55`. Deploy `deploy_vps.sh 7ab5fe55` IN FLIGHT (kill dance VOICE_LAUNCH_KILL=1; HARD_OFF kept=1). Acceptance pending: admin grep Master Blueprint ≥1.

**Cloud:** Task [coord](bc-e98e2f74-cab3-4d82-a5b8-ea8caa253790) + branch `cursor/reply-hard-off-containment-3790` observed on fetch.

**Left:** finish deploy + kill restore 0 + acceptance curl; SELF_IMPROVE_LOOP / CONTENT_APPROVAL_AUTO drifts still open.

---
# SESSION_HANDOFF — 2026-08-07 Master Blueprint + Automation Max auth

## 2026-08-07 20:20 IST — Auth pass PROVEN + 3 flag drifts (owner decision pending)

**PR #276** OPEN MERGEABLE · commit `8b36b795` · 2 files only · CI: lint/test/CodeQL/Trivy/GitGuardian/harness green; Gate A non-required FAIL; prod_check was still pending at last poll. Deploy NOT done. Prod `a08dd5e9`, `/app/admin` still 0× Master Blueprint.

**Automation Max (authenticated, read-only — OTHER SESSION evidence, Cursor accepted):**
- Scheduler: 43 jobs · 0 disabled · 0 unhealthy · runs failures_first 60 → 0 failures
- All 5 families ran today (ok). platform_dial 0.16s ≠ dial placed (falsified-list #2)
- No run-now fired (correct — schedule already covered)

**Doc-vs-prod drifts (do not leave contradictory):**
1. `REPLY_AUTO_SEND=ON` vs matrix row 22 HARD-OFF — HIGHEST exposure → owner flip-or-relabel
2. `SELF_IMPROVE_LOOP=ON` vs automation-max script pins `"0"` (containment)
3. `CONTENT_APPROVAL_AUTO=ON` vs matrix row 9 `=0` — note: code = auto-SUBMIT to queue, NOT auto-approve/publish

**Real Automation Max gap:** 263 flags `unknown_requires_review` (governance), not engine wiring.

**Next:** Sumit decides REPLY_AUTO_SEND; then #276 merge/deploy when asked; flag classification separate.

---
# SESSION_HANDOFF â€” 2026-08-07 Master Blueprint nav (Cursor pickup)

## 2026-08-07 20:10 IST â€” PR #276 OPEN (merge â‰  deploy)

- Branch `fix/admin-master-blueprint-nav` @ `8b36b795` (1 commit ahead of `origin/main` `34836739`)
- PR: https://github.com/sumitrevolt/leadgenrationaivoiceagent/pull/276
- Staged paths ONLY: `frontend/admin_dashboard.html`, `tests/test_admin_master_blueprint_nav.py`
- Deploy NOT done. Acceptance after deploy: `grep -c -i "master blueprint"` on `/app/admin` â‰¥1 (now 0)
- Deploy note: will also ride #275 safe_settings; use `deploy_vps.sh` + APP_VERSION pin + VOICE_LAUNCH_KILL dance
- Automation Max still blocked on Sumit Chrome login (credentials off-limits to agents)

## 2026-08-07 19:45 IST â€” Master Blueprint admin-nav re-applied on CLEAN branch

**Picked up** prior Loop Run (progress.md Master Blueprint entry). Drifted-tree fix was
**not** shippable (`cursor/swara-paid-free-faq-fix` 1801/1830 off main).

**Done (Cursor):**
- Clean worktree `C:/Users/Ratanshila/Documents/leadgen-master-blueprint-nav`
- Branch `fix/admin-master-blueprint-nav` @ `origin/main` `34836739`
- Same 2-file additive slice: `frontend/admin_dashboard.html` + `tests/test_admin_master_blueprint_nav.py`
- pytest nav suites **25 passed** (`--noconftest`)
- Prod `/health` cache-bust Ã—2 = `a08dd5e9` (uptime advancing). Prod `/app/admin` still **0Ã—** "Master Blueprint" (undeployed â€” expected). `/api/blueprint/meta` 200, 59n/56e.

**UNPROVEN / blocked:**
- Automation Max + 43-job health â†’ needs owner `/app/admin-login` (no admin session in browser)
- `graphify affected` still empty post-refresh (undirected post-build) â€” not this PR
- Commit/PR/deploy not done (owner ask)

**Next:** Owner â†’ (1) commit+PR this branch? (2) admin login for automation auth pass.

---

# SESSION_HANDOFF â€” 2026-08-06/07 launch unblock: SHIPPED

Full evidence ledger: **`docs/context/LAUNCH_AUTOMATION_AUDIT.md`**.
Automation verify ladder: **`docs/context/AUTOMATION_VERIFY_CHECKPOINTS.md`**.
WS3 raw evidence: **`/root/WS3_EVIDENCE_20260807.md`**.

## 2026-08-07 19:20 IST â€” Peer CLEAR Â· merge-ready Â· sequence hold

WI-CP2 branch peer-verified (gates + skip-warn + lead_id + INTERACTION_LOG=1 prod).
**Merge-ready**, no open objections. Label stays **CLAIMED** (not CODE-PRESENT live) until
deploy + real `interactions` out+`reply_agent` row. B+C UNPROVEN unchanged.

**Sequence (locked):** morning **D2 (03:48Z)** + **CRM (~11:30 dial)** first â€” revenue path.
This observability PR waits. Owner blockers: **Vobiz portal** Â· morning D2 log Â· CRM prove.

## 2026-08-07 19:15 IST â€” Peer review PASS + INTERACTION_LOG follow-up

Peer: gates 1â€“4 verified. Extra findings addressed on branch:
- Prod `INTERACTION_LOG=1` (PRODUCTION-PROVEN probe)
- Helper warns on `record()["skipped"]` (master gate silent-return)
- lead_id no prospect-id fallback; `meta.prospect_id` only
- Replay = Redis claim-lock, not log-layer idempotency (ledger wording)

WI-CP2 remains **CLAIMED** until prod out+reply_agent row. Commit follow-up next.

## 2026-08-07 18:55 IST â€” WI-CP2 commit `7d3b1448` (CLAIMED, peer review pending)

Branch `fix/reply-auto-send-interaction-log` @ `7d3b1448` â€” 1 commit ahead of
`origin/main`. Visible from any worktree sharing `.git`:
`git show 7d3b1448` / `git grep _record_auto_reply_interaction fix/reply-auto-send-interaction-log`.
Label = **CLAIMED** until peer reads the four gates (meta= / await / call-time env /
sent-before-record). Push not done. Not deployed.

## 2026-08-07 18:50 IST â€” WI-CP2 fix CODE-PRESENT (not deployed)

Branch `fix/reply-auto-send-interaction-log` on clean worktree `leadgen-verify-main`:
auto-send `if ok:` â†’ `interaction_log.record(direction=out)` with `meta.delivery_key` +
`source=reply_agent`. `REPLY_AGENT_INTERACTION_LOG` default ON / opt-out `0`. No silent
except. `pytest tests/test_reply_auto_send.py` â†’ 26 passed. Backfill out of scope.
Not CP8 FAIL (observability). Ship/PR when owner asks; WI closes only after prod
`interactions` out+reply_agent proof. B+C still UNPROVEN.

## 2026-08-07 18:35 IST â€” CP2 auto-reply: inbound bifurcate + watch-item

`REPLY_AUTO_SEND` armed **via env=1** (not Redis-override).

`interactions` reply-ish out count=0 is **ambiguous**:
- **(a)** no inbound â€” dismissed for 2026-08-07 (email in=2)
- **(b)** blind logging â€” still live: zero `reply_agent` tags in interactions ever this probe, yet `reply_drafts` has historical `auto_sent_at` (2026-07-14)

Today PayU inbound â†’ draft `interested` + `scan_status=suspicious` â†’ **not** auto-sent (`auto_sent_at` absent). Guard held.

**WI-CP2-AUTO-REPLY** watch-item (not CP8 FAIL, not PASS). Truth source for outs = `reply_drafts.auto_sent_at`, not interactions meta.

## 2026-08-07 18:28 IST â€” CP2 hedge PARTIAL (send â‰  deliverability/triage/auto-reply)

Accept prior CP2 send-path evidence. Relabeled **PARTIAL**.

UNPROVEN (must not get green ticks): (1) deliverability/inbox (2) reply triage *effect*
(3) reply auto-send *output*.

Depth probe: `REPLY_AUTO_SEND` prod **env=1** (hot-fact env=0 is STALE); effective
`_reply_auto_send_enabled()=True`; `interactions` email-out reply-ish meta **count=0**
(last cold-outreach outs only). Path ARMED, attributed auto-reply sends not found.
Not CP8 unless owner asks. Cold WA still OFF.

## 2026-08-07 18:20 IST â€” Independent ladder verify + CP2 live

**Framing (confirmed):** `CP8 FAIL queue empty` â‰  sab PASS. Ledger hedged: CODE-PRESENT/PARTIAL + O1/O2/O3 UNPROVEN.

**CP1 three-way:** dispatcher 43 = JOB_META 43 = staff beat 43. Orphans none.
False finding withheld: 3 beat args = `train_brain` under `ENABLE_LEGACY_BEAT`, not staff orphans.

**`ENABLE_LEGACY_BEAT`:** prod = **`0`** (env + dotenv) â€” PRODUCTION-PROVEN as value; **not** filed as CP8 unless owner says.

**CP2 live (worker logs, no send canary):**
- `email_outreach` 16:05/17:05/18:05 â€” sent 4/3/3, failed 0, task ok
- `email_followup` 16:25/17:24 â€” sent 4/4, failed 0
- `reply_triage` + `sales_autopilot` ticks ok
Cold WA still OFF (`SALES_AUTOPILOT_WHATSAPP_ENABLED=0`).

Streams still waiting: WS-SEC1 portal Â· WS-MORNING wall-clock Â· WS-VERIFY CP4/6/7 deeper live if needed.

## 2026-08-07 17:40 IST â€” CP0 + CP3a (Automation Verify Ladder)

**Prod** `/health.version` = **`a08dd5e9`** (loopback + public). **main** = **`34836739`**.
Flags: `DELIVERABLE_CYCLE_SEED=1` Â· `CALL_LEAD_CRM_SYNC=1` Â· `NICHE_PROSPECT_MAX_QUERIES=12` Â·
`VOICE_LAUNCH_KILL=0` Â· `PLATFORM_DIAL_DAILY=1` Â· `PROSPECT_MAX_LOOKUPS=150` HOLD.
Queues: celery 0 Â· failed_tasks 0 Â· dead 0 (reprobe). D2 cron armed. `vobiz_new.env` missing.

**CP3a git:** workspace `cursor/swara-paid-free-faq-fix` @ `e8d34921` is ~1801 ahead / ~1830 behind
`origin/main` (merge-base `76cbb2f6`). This is **local branch drift**, not prod broken.
Clean verify worktree: `C:/Users/Ratanshila/Documents/leadgen-verify-main` â† `origin/main`.

**ACTIVE_WORK (3):** WS-SEC1 Vobiz Â· WS-MORNING B1/B2 Â· WS-VERIFY ladder.
**Swara = verify-only.** Hangup C3 WITHDRAWN. See AUTOMATION_VERIFY_CHECKPOINTS falsified list.

## 2026-08-07 17:55 IST â€” Automation Verify Ladder CP0â€“CP8 closed (this session)

Ledger: `docs/context/AUTOMATION_VERIFY_CHECKPOINTS.md` (full tables).
Clean worktree: `C:/Users/Ratanshila/Documents/leadgen-verify-main` @ `34836739`.

**Overnight numbered verdicts (GATE INSTALLED):**
- O1 Vobiz = UNPROVEN/BLOCKED (`vobiz_new.env` missing)
- O2/B1 D2 = UNPROVEN/ARMED (cron OK; no morning log yet)
- O3/B2 CRM = UNPROVEN (`CALL_LEAD_CRM_SYNC=1`; history 1459 â‰  new-path proof)

**CP1** JOB_META 43 inventory CODE-PRESENT. **CP2â€“CP7** verify slices PARTIAL/PASS as labeled; Swara verify-only.
**CP8** empty FAIL queue â€” no PR, no deploy. LOOKUPS=150 HOLD. Hangup C3 WITHDRAWN.

## 2026-08-07 17:05 IST â€” CP-A2 done Â· PR #275 on main

**`origin/main` = `34836739`** (squash merge of #275 safe_settings). **Prod still `a08dd5e9`** â€”
helper not required for morning D2/CRM; deploy of #275 can ride next VOICE_LAUNCH_KILL dance
or wait. Default-deny test added before merge (unknown field must not appear in `probe["fields"]`).

**CP-C3 hangup â€œ404â€ is a false lead** â€” do not implement a second route. POST already 200.

**Ticketed (not started):** CP-A3 Postgres rotate (owner haan + late-evening IST) Â· CP-A4
DATABASE_URL split Â· CP-C1 D3 cursor Â· CP-C2 LOOKUPS owner decision Â· CP-C4 trainer DLQ Â·
CP-C5 `@example.com` substring â†’ domain-suffix.

## 2026-08-07 16:45 IST â€” evening checkpoint (no flag / LOOKUPS / dial changes)

**Prod still `a08dd5e9`**, uptime ~3h+, flags unchanged:
`DELIVERABLE_CYCLE_SEED=1` Â· `CALL_LEAD_CRM_SYNC=1` Â· `NICHE_PROSPECT_MAX_QUERIES=12` Â·
`VOICE_LAUNCH_KILL=0` Â· `PROSPECT_MAX_LOOKUPS=150` (owner: do not bump).

**Cron D2 capture still armed** (UTC): `48 3 * * *` pre Â· `50 3 * * *` capture â†’
`/root/d2_morning_<date>.log` (re-attach on container recreate).

**Hangup URL â€œ404â€ RETRACTED:** `/api/webhooks/vobiz/status` is **POST 200** (empty + form).
GET returns 404 by FastAPI design â€” Vobiz posts Hangup/Status. Not a missing route.
Do not â€œfixâ€ it; Claudeâ€™s earlier GET probe was the wrong method.

**Vobiz rotate still OWNER-PORTAL blocked.** `/root/rotate_vobiz.sh` ready; `/root/vobiz_new.env`
missing. Agents apply only; cannot generate portal tokens. API: auth token = Console only;
SIP pass can Update-Endpoint via API but that still needs the leaked auth token â†’ portal both.

**Unproven overnight:** D2 path (`prospect` job morning) Â· CRM sync (needs answered call).
**Proven today:** D1 midday yield 4â†’163 leads (not D2).

**Next human:** Vobiz portal â†’ `/root/vobiz_new.env` â†’ Cursor `bash /root/rotate_vobiz.sh` â†’
portal revoke old. Say â€œrotate chalaoâ€ when file is 0600.

## 2026-08-07 17:31 IST â€” end of day Â· what is armed, what is unproven

`origin/main` = **`34836739`** (PR #275 `safe_settings`, squash-merged).
Prod = **`a08dd5e9`**, 5/5 zero skew, uptime 3h54m, `celery=0` `dlq:failed_tasks=0` `dlq:dead=3`.
main is one commit ahead of prod on purpose â€” `safe_settings` is a helper module with no runtime
caller yet, so it rides the next deploy. Nothing tomorrow morning depends on it.

Cron re-verified at 17:31 IST: `48 3` + `50 3` present, `cron` service active.
`/root/vobiz_new.env` still **MISSING** â€” the Vobiz rotation has not happened.

### Falsified this session â€” do NOT re-test these

1. *"`platform_dial` returns 0 candidates because `next_call_at` / `phone_verified`."* â€” those
   columns are not in the selection query at all.
2. *"0.28s job duration proves a no-op."* â€” the job only `send_task`s; sub-second is the happy path.
3. *"The whole lead pool is landlines."* â€” probe passed an object where a `str` was expected.
   89% of the pool passes `dial_gate`.
4. *"Places API is down / returning empty."* â€” live: HTTP 200, 6 businesses per query,
   `queries_empty: 0`, `queries_failed: 0`.
5. *"The rotation cursor has walked into exhausted niches."* â€” cursor=28's four targets all
   returned results on a live probe.
6. *"Dedupe saturation is the cause."* â€” 12 queryÃ—city combos still yielded **45 NEW** leads.
7. *"In-run queries come back empty while out-of-run ones don't."* â€” my own theory; the run dict
   says `queries_empty: 0`. Dead.
8. *"`grep crm_lead_id app/` finds nothing, so PR #267 is not on main."* â€” the worktree was on a
   different branch. Use `git grep <pat> origin/main --`.
9. *"No `/api/telephony` hits in 60m, so streams never connect."* â€” the container had been
   recreated 20 minutes earlier; `docker logs` starts from the recreate. Absence proved nothing.
10. *"`hangup_url` returns 404, so hangup callbacks are lost."* â€” probed with GET; the route is
    POST-only and returns 200.

Items 7, 9 and 10 were all mine, and all three share one shape: **treating absence or a status
code as a finding without checking what produced it.** That is the failure mode to watch for.

## 2026-08-07 15:35 IST â€” D2 deployed Â· the collapse is over Â· but read the attribution

**Prod `a08dd5e9`, 5/5 zero skew, uptime verified independently.** D2's function is present and
behaves to spec inside the running image: `remain=345 -> 240.0`, `remain=90 -> 60.0`,
`remain=44 -> None`.

**The lead collapse is over.**

```
                08-05    08-06    08-07
prospects        283      119      168
leads            260        4      163
```

`midday_prospect` at 10:00:45Z -> 10:02:50Z (124.5s, ok):

```
{'new': 112, 'duplicates': 22, 'no_phone': 29, 'queries_run': 3, 'queries_capped': True,
 'by_niche': {'hospital_appointments': 112}, 'lookups_used': 150, 'lookups_capped': True,
 'quality_rejected': 16, 'emails_found': 7, 'cadence_enrolled': 112}
scraped niches: ['hospital_appointments', 'skin_dermatology']
new source_query values: 'multispecialty hospital' 112 Â· 'harvest:opendata' 20
```

âš ï¸ **Do NOT credit D2 for this.** `post_prospect_harvest_timeout` is called from exactly one
place â€” `team_scheduler.py:1004`, inside `elif job == "prospect"`. Today's run was
**`midday_prospect`** (line 1241), a different branch that calls `run_harvest_safe()` and never
touches D2's code. The win is **D1** (`NICHE_PROSPECT_MAX_QUERIES=12`) reaching the prospector
through the midday harvest's own prospector source, plus that harvest's opendata source.

**D2 remains UNPROVEN.** Its branch next runs at 04:00 / 06:00 UTC (09:30 / 11:30 IST) tomorrow.
What to look for then: a `[team-scheduler] post-prospect harvest timeout=... truncated=False` line,
and the absence of the old `harvest truncated after prospect (SoftTimeLimit margin)`.
Rollback if it misbehaves is one env var: `PROSPECT_INLINE_HARVEST=0`.

**New binding constraint: `lookups_capped: True` at `lookups_used: 150`.** The query cap is no
longer what limits us â€” `PROSPECT_MAX_LOOKUPS=150` is. That is the next lever, and it costs Places
API quota, so it needs an explicit decision rather than a quiet bump.

Health after the run: `celery=0`, `dlq:failed_tasks=0`, `dlq:dead=3` (unchanged â€” the three
pre-existing `TimeLimitExceeded(600,)` trainer entries), duration 124s well under the 540s soft
limit, no SoftTimeLimit anywhere.

### Armed for tomorrow morning (D2 proof)

Owner decision: **`PROSPECT_MAX_LOOKUPS` stays 150.** Yield is back; a silent Places-spend bump is
not on. Revisit only after D2's morning proof and a look at quota headroom.

Cron installed on the VPS (UTC), verified, `cron` service active:

```
48 3 * * * /root/d2_morning_pre.sh        # counters + queue snapshot into the log
50 3 * * * /root/d2_morning_capture.sh    # 2h30m follow -> /root/d2_morning_<YYYYMMDD>.log
```

Window opens 03:48Z (09:18 IST) and covers **both** the 04:00Z and 06:00Z `prospect` runs. The
capture writes to a file as events happen and **re-attaches if a container is recreated**
mid-window (it logs `--- log stream ended, re-attaching ---`). That is deliberate: the 08-06
evidence was lost precisely because a recreate wiped `docker logs`.

Pass/fail for D2 tomorrow:

| check | pass | fail |
|---|---|---|
| `[team-scheduler] post-prospect harvest timeout=...` | line present | absent = branch never ran |
| `truncated=` | `False` | `True` = budget still short |
| old `harvest truncated ... SoftTimeLimit margin` | absent | present = D2 ineffective |
| run duration | < 540s | >= 540s = rollback immediately |
| `dlq:dead` | stays 3 | rising = D2 broke something |
| `by_niche` | >= 2 niches | 1 = D1 regressed too |

Rollback is one env var, no code touch: `PROSPECT_INLINE_HARVEST=0`.

**Still blocked on the owner: Vobiz rotation.** `/root/rotate_vobiz.sh` is staged (mode 700, 5732
bytes); `/root/vobiz_new.env` is still absent, so nothing has rotated. The leaked token can place
calls on the account â€” spend plus TRAI exposure under the owner's own DLT registration.

## 2026-08-07 12:40 IST â€” deploy + flags live

ðŸ”´ **SECRET EXPOSURE â€” ROTATE.** While probing `settings` for the Vobiz callback URL I dumped the
whole settings object to the session transcript. My error: the env-var half of that probe filtered
`KEY|TOKEN|SECRET`, the settings half had no filter at all.

**Standing rule from now on: never dump `settings`, `__dict__`, or env *values*. Allowlist field
NAMES and print names only.**

Exposed **credentials** (names only, 3):

| field | why it matters |
|---|---|
| `VOBIZ_AUTH_TOKEN` | places calls on the account â€” spend + TRAI exposure under the owner's DLT |
| `VOBIZ_SIP_PASS` | direct SIP trunk registration |
| `DATABASE_URL` | Postgres password is embedded inline |

Exposed **identifiers** (not credentials, but useful in combination):
`vobiz_auth_id`, `vobiz_sip_user`, `vobiz_trunk_id`, `vobiz_trunk_domain`, `vobiz_caller_id`.

Non-secret and harmless: `public_base_url`, `redis_url`, `qdrant_url`, `smtp_host`,
`waha_base_url`, `dnd_api_url`, `platform_website_url`, `LANGFUSE_BASE_URL`, `OMNIROUTE_BASE_URL`,
`TWILIO_WEBHOOK_URL` (stale placeholder), webhook tuning flags. `proxy_url` held the literal
placeholder `user:pass@proxy:port`, not a real credential.

**Runbook staged and syntax-checked: `/root/rotate_vobiz.sh` (mode 700).** Owner writes the new
values to `/root/vobiz_new.env` (mode 600, out-of-band â€” not chat); the script substitutes via
python, verifies by SHA-256 prefix + length only, recreates `app`+`worker` at the pinned
`APP_VERSION`, smokes, then shreds the handoff file. It refuses if the file is missing, is not
0600, or if a value is unchanged. No value is ever echoed.

Postgres rotation is **planned, not executed** â€” see the plan doc. It is more disruptive than it
looks because PgBouncer holds its own copy of the password, so role / PgBouncer / `.env` must
change in that order or the pool strands. Owner's call to do Vobiz first is right: Postgres is not
published to the host and sits behind PgBouncer on the Docker network.

| | |
|---|---|
| `/health.version` | **`67b74076`** (verified independently, not taken on report) |
| `DELIVERABLE_CYCLE_SEED` | **1** â€” Jiya `d79d690f61b3` has `2026-07: 10` + `2026-08: 10` |
| `CALL_LEAD_CRM_SYNC` | **1** in `leadgen_app` + `leadgen_worker`, both on `67b74076` |
| `NICHE_PROSPECT_MAX_QUERIES` | **12** in `leadgen_worker_heavy` (D1 canary) |
| `.env` backups | `.env.bak-crmsync-20260807_064038`, `.env.bak-d1queries-20260807_070310` |
| voice session | rotated `S20260807-3aa44c87` (30/30 paused) -> **`S20260807-7c55ae80`** (8/30) |

**CRM sync is LIVE but UNPROVEN â€” and that distinction matters.** 8 calls placed since the flag
went on; **zero were answered**, so `persist_call_log` -> `sync_lead_after_call` never executed.
`lead_status_history` still shows only `outreach` / `backfill:outreach`. This is *not* a failure of
the fix â€” the code path was never reached. Do not read the empty result as a negative.
Not a regression either: `https://leadsgenai.in/api/telephony/vobiz/answer-stream/<t>` returns 200
through Caddy *and* loopback, Caddy is active with no restart. Vobiz never fetches `answer_url` for
a call that rings out, so no stream, no log. Proof still needs ONE connected call.

**D1 canary CONFIRMED the hypothesis.** Run `07:03:37Z -> 07:05:49Z` (131.8s, ok):

```
before D1 (4 queries):   by_niche {'travel_agency': 3}                 -> ONE niche
after  D1 (12 queries):  'travel agency' 3 + 'gift shop' 2             -> TWO niches
prospects_today 19 -> 36 (+17) Â· leads_today 6 -> 10 (+4) Â· cursor 29 -> 30
```

Widening the query cap does widen niche coverage. But it reached 2 niches, not 4 â€” run duration is
unchanged (131.8s vs 135.4s), so **D2 (harvest SoftTimeLimit truncation) is still binding** and is
now the next constraint. Do not raise the cap further before D2; that would just truncate earlier.

**Pre-existing, not mine, worth a ticket:**
- `dlq:dead = 3`, all `TimeLimitExceeded(600,)` on `['trainer']` (00:17Z, 00:27Z, 06:18Z today).
  `celery` and `dlq:failed_tasks` are both 0.

ðŸ”» **RETRACTED â€” the "hangup_url 404" finding was my probe error, not a bug.** I curled
`/api/webhooks/vobiz/status` with the default method (GET) and reported the route as missing.
Re-probed properly:

```
GET   /api/webhooks/vobiz/status -> 404
POST  /api/webhooks/vobiz/status -> 200
```

The route exists and is POST-only, which is correct for a webhook. Vobiz hangup callbacks land
fine. **Do not "fix" this.** Second time this session that a status code got read as a diagnosis
without checking what produced it â€” probe with the method the caller actually uses.

**Method correction:** I claimed "the 11:30 run produced no `/api/telephony` hits" from
`docker logs --since 60m`. Invalid â€” the app container had been recreated at 12:10, so its log
stream starts there. After any recreate, `docker logs` absence proves nothing.

## 2026-08-07 morning â€” state at handoff

| | |
|---|---|
| `origin/main` | **`67b74076`** (PR #272 `92a6f870`, then PR #273) |
| Deployed `/health.version` | **`89acfaa3`** â€” main is 2 merges AHEAD of prod; **NOT deployed** |
| Deploy | deliberately withheld pending owner go-ahead |
| `CALL_LEAD_CRM_SYNC` | code merged, flag **OFF** (never set) |
| `DELIVERABLE_CYCLE_SEED` | code merged, flag **OFF** (never set) |

**Calling is live.** 11:30 IST scheduled dial: `ok=26 skip=12 fail=0`, plus 4 from the manual
canary = **30 = session cap**, and `[voice_launch] training pause at call 30` fired correctly.
`phone_type_blocked` fired on several leads â€” the gate is active and must stay that way.
All connected calls so far are voicemail/IVR (`bot_suspected`); no human conversation yet.

**WS3 root cause â€” found, with live numbers (see the evidence file).**
Not Places, not the cursor, not dedupe saturation, not empty queries. Three compounding defects:

- **D1 `queries_capped: True`** â€” `niche_prospector.py:173` forces `PROSPECT_MAX_QUERIES` to
  `NICHE_PROSPECT_MAX_QUERIES` default **"4"**; `prospector.py:829` then truncates `pairs[:4]`.
  All 4 queries were spent on ONE niche across 4 cities (`by_niche: {'travel_agency': 3}`).
  `build_targets` had selected four niches â€” `gift_stationery`, `hospital_appointments`,
  `skin_dermatology`, `travel_agency` â€” and three of them were **never scraped at all**.
- **D2 harvest truncated** â€” `team_scheduler.py:990`, SoftTimeLimit (~540s) margin. The
  websearch/opendata harvest stages never ran; on 08-05 those supplied the `harvest:websearch` /
  `harvest:opendata` prospects that made up the bulk.
- **D3 cursor +1 per run while `batch=4`** â€” 75% niche overlap run-over-run, hence
  `duplicates: 20` of 24 lookups (83%).

Headroom is not the constraint: `lookups_used: 24` of `PROSPECT_MAX_LOOKUPS=150`,
`lookups_capped: False`, `time_budget_exhausted: False`, `queries_failed: 0`, `queries_empty: 0`.
The system throttles itself to 4 queries while sitting on 126 lookups of unused budget.

**Gotcha (cost me a wrong reading):** `job_runs.jsonl` contains a NUL byte, so `grep` flips to
binary mode and reports **stale/wrong** "last" matches â€” it showed July entries as the newest.
Read that file with python line-by-line and `errors="replace"`, never grep.

## Prod state
| | |
|---|---|
| `origin/main` | **`89acfaa3`** |
| Deployed `/health.version` | **`89acfaa3`** â€” main and prod in exact parity |
| Container skew | 5/5 app-image services on `89acfaa3`, zero skew |
| Smoke after deploy | `/health` `/api/voice/niches` `/api/billing/plans` `/api/public/pay-info` â€” all 200 |
| `VOICE_LAUNCH_KILL` | `0` (deploy gate engaged then restored; proven in-container) |
| Voice session | **`S20260807-3aa44c87`**, attempts 0/30, state `running` |
| Queues | `celery` 0 Â· `dlq:dead` 0 Â· `dlq:failed_tasks` **2** (pre-existing `trainer` `TimeLimitExceeded(600)` at 00:17/00:27 UTC, BEFORE the 00:50 deploy â€” not caused by this work) |

## Shipped â€” all five PRs merged
| PR | What | Merge |
|---|---|---|
| #266 | paid/free FAQ beats product pitch | `c8447202` |
| #267 | `call_logs.lead_id` threading â€” also unblocks lead categorization | `7c726b6d` |
| #268 | agent_tasks orphan ledger: `begin()` + reaper + `ROUTINE_TASK_LEDGER` | `0c99540e` |
| #269 | deliverable ledger alias-expand | `3470f541` |
| #270 | fixture-tenant quarantine (INERT) | `89acfaa3` |

## Verified LIVE after deploy
**`begin()` â€” the agent_tasks leak is closed.** Rows created since deploy: `done` 2 (`flow_cron`, `watchdog`), `pending` **0**, `completed_at` set. Previously every succeeding routine leaked a `pending` row forever.

**Orphan reap â€” 12,072 rows closed.** 7 bounded batches (6Ã—2000 + 72), each with its own JSONL backup written BEFORE mutation, closed as `cancelled` (never `failed` â€” most of those routines SUCCEEDED and `automation_logs` holds the truth), never requeued.
```
before  pending 12,792 Â· done 52 Â· failed 7
after   pending    720 Â· done 52 Â· failed 7 Â· cancelled 12,072
remaining orphans >24h : 0
backups: /var/lib/leadgen/runtime/automation/agent_task_orphans_20260807_0107*.jsonl  (x7)
```
The 720 remaining are <24h old (created pre-deploy) and are out of the reaper's window. They will age in; new rows now close as `done`.

**Jiya deliverable fix â€” proven.** Same SELECT the writer runs, old vs new predicate:
```
OLD exact match  -> found: FALSE   (the bug)
NEW expanded     -> found: TRUE
matched row: client_id=d79d690f61b3  type=social_post_draft  status=not_started  cycle=2026-07
client candidates: [jiya-makeover, d79d690f61b3]
type   candidates: [social_posts, monthly_content_calendar, social_post_draft]
```
Both the id AND the type differed â€” both expansions were required. Ledger still reads `not_started 8` because no false status was written; it advances on the next content run.

**Jiya billing alias â€” linked earlier, survived the deploy.** `resolve_client("d79d690f61b3")` â†’ `jiya-makeover`, `canonical_client_id` â†’ `jiya-makeover`, `billing_client_ids` â†’ `["d79d690f61b3"]`. Backup `marketing_clients.jsonl.bak-jiyaalias-20260806_211128`. **Do NOT re-link.**

## Owner levers â€” current state
| Flag | State | Note |
|---|---|---|
| `AGENT_TASK_ORPHAN_REAP` | **OFF** | Backlog already cleared manually. Arm only if the 720 recent rows need sweeping once they pass 24h. |
| `ROUTINE_TASK_LEDGER` | **ON** (default) | `begin()` is now proven closing, so setting `0` is safe whenever you want to stop writing the duplicate ledger (~700 rows/day). Owner call. |
| `TENANT_QUARANTINE` | **OFF** | Dry-run against live prod: `scanned 10, selected 10`, `status_applied: cancelled`. All 10 fixtures selected; Jiya and `platform` correctly absent. Arm to apply. |

## â¸ Phase C â€” dial canary, DEFERRED to TRAI window
Everything upstream is done. The campaign is unblocked: session rotated, `PLATFORM_DIAL_DAILY=1`, `VOICE_LAUNCH_CAMPAIGN=1`, `VOICE_LAUNCH_KILL=0`, `DIAL_TEST_MODE=0`, 13,915 candidate leads, 12,436 gate-eligible.

TRAI promotional window is **10:00â€“19:00 IST**; this ran at ~06:45 IST. The window is enforced per-lead at dispatch, so nothing can leak out early.

**First action after 10:00 IST** â€” small canary, owner listens:
```
docker exec leadgen_app python -c "
from app.worker import celery_app
celery_app.send_task('app.tasks.calling.run_campaign_task',
  kwargs={'limit':3,'dry_run':False,'niche':'all','client_id':'','platform':True,'transactional':False})"
```
Then prove from `admin:campaign:last_run` that `placed/queued >= 1` â€” **not** from the scheduler job's `last_ok`, which is enqueue-only and sub-second by design. Confirm the paid/free FAQ fires on the call.

## â›” BLOCKED â€” prod shell access lost (2026-08-07 ~07:30 IST)
Desktop Commander MCP disconnected and did not return. The sandbox **can reach VPS port 22** but has **no SSH key** (it lives at `C:\Users\Ratanshila\.ssh\id_rsa`, outside every mounted folder). Reconnect Desktop Commander to resume.

**Ready to run the moment access returns** (scripts already written and validated):
| Workstream | Script | State |
|---|---|---|
| WS1 fixture quarantine APPLY | `outputs/ws1_quarantine.py` | written; dry-run already proved 10 selected, Jiya/platform absent |
| WS2 Jiya deliverable advance | needs a content tick for `jiya-makeover` | writer proven to find the row; status not yet written |
| WS3 falsification | one-liner below | â€” |

âš ï¸ Design gap found while preparing WS1: `tenant_quarantine.quarantine_enabled()` exists but **`quarantine_fixture_tenants()` never checks it**, and no scheduler calls it. The `TENANT_QUARANTINE` flag is currently decorative â€” apply is a manual one-shot call.

## WS3 â€” prospect intake collapse (260â†’4 on 2026-08-06): RANKED, NOT YET FALSIFIED

**Mechanism that makes this possible at all:** `leads` inserts are **phone-gated at BOTH writers** â€” `prospector.py:488` (`len(phone) < 10 â†’ return False`) and `niche_database.py:333`. Google Places is the only source that reliably carries a phone; OSM Overpass rows usually do not. So if Places goes dark, `prospects.jsonl` keeps growing and `leads` gets ~0.

**#1 â€” Google Places quota â†’ 24h Redis cooldown. Most consistent.**
`google_maps.py:82` returns `[]` before any HTTP while the cooldown key lives; `:147` a single 429 calls `start_places_quota_cooldown()`; `integration_health.py:32` `DEFAULT_PLACES_QUOTA_COOLDOWN_S = 24*3600`. This is a **step function**, matching 260â†’4 overnight. The 196.91s runtime is *explained*: Places short-circuits instantly, then per-query OSM fallback (`prospector.py:927`) runs with a 25s Overpass timeout â‰ˆ 200s. The job **cannot** report failure â€” `PlacesQuotaExhausted` is caught and turned into `return []`.

**#2 â€” `data/` rotation-state reset** (NOT rotation end). `_read_cursor()` returns 0 on any read failure; `gtm_targeting._load_state()` returns `{}`. Both silently restart at the beginning and re-scrape already-covered pairs â†’ ~100% dedupe. Same 196s / ~0 inserts signature.

**#3 â€” `HARVEST_INGEST_VALIDATION`** â€” ruled out as trigger: default-ON since 2026-07-05, no commit since 2026-07-25 touches the regex or flag.

**#4 â€” rotation cursor reaching its end** â€” **dead by code**: `% len(keys)` wraps, GTM selector is least-recently-used with no terminal state.

**Untested candidate that outranks all four â€” check it FIRST:** the DB mirror failing while harvest succeeds. `_persist_prospect_to_db` swallows every exception at `logger.debug` (`prospector.py:522`), and `bulk_import` is a fire-and-forget `create_task` nobody awaits (`:582`). A Postgres/PgBouncer hiccup gives exactly this signature.

### The one query that separates all of them
```
# 1. did the jsonl keep growing on 08-06?  (separates "source dried up" from "DB mirror broke")
docker exec leadgen_app sh -c "grep -c '2026-08-06' \$(python -c \
  'from app.platform import prospector; print(prospector._PATH)')"
# 2. is Places dark?   non-zero TTL = smoking gun
docker exec leadgen_redis redis-cli ttl integ:cooldown:places
# 3. which scraper actually ran, 08-05 vs 08-06?
#    agent_events member='rohan' action='prospects_found' -> meta_json.scraper
#    "google_maps_api" -> "osm_overpass" is the confirmation
```
`automation_logs.output_summary` will NOT help â€” it is literally `"success in {ms}ms"` (`team_scheduler.py:384`). The yield counters live in `agent_events.meta_json` (`new/duplicates/no_phone/queries_run/scraper/lookups_used`) and `data/harvest_runs.jsonl`.

### Separate pre-existing bug found while mapping
`app/platform/udyam_pipeline.py:55` imports `GoogleMapsClient` from `app.lead_scraper.google_maps`, which only defines `GoogleMapsScraper`. The Maps-enrich step has **always** been dead â€” caught at `:69` and silently falling through to OSM-only. Same function-level-import class as the `/api/voice/niches` incident. Unrelated to the cliff; worth its own fix.

## 2026-08-07 morning â€” WS1 DONE, WS2 root cause, WS3 evidence destroyed

### âœ… WS1 fixture quarantine â€” APPLIED
`pg_updated: 10` Â· backup `/var/lib/leadgen/runtime/customers/tenant_quarantine_20260807_022157.csv`
before `active 9 / paused 3 / cancelled 1` â†’ after `cancelled 11 / active 2`. `fixtures_not_cancelled: 0`.
**Active tenants are now exactly `platform` + `d79d690f61b3` (Jiya).** Money rows untouched (subs 2, billing 120, call_logs 100, deliverables 20). `PROOF_OK: true`.
Note: `TENANT_QUARANTINE` flag is **decorative** â€” `quarantine_fixture_tenants()` never checks it and no scheduler calls it. This was a one-shot manual apply.

### ðŸ”´ WS2 â€” the real Jiya blocker is NOT the alias
```
rows_by_cycle:               [["2026-07", 20]]   <- ONLY July, for anyone
max_created:                 2026-07-18
jobs_mentioning_deliverable: []                  <- no job seeds or renews deliverables
jiya_queue_len 24 Â· jiya_upcoming 0
```
`initialize_deliverables_for_client` is called **only from `usage.py` on plan activation**. Jiya activated 2026-07-05. **Nothing re-seeds a new billing cycle.** So:
1. **July rows** are stuck â€” `sync_customer_deliverable_status` only fires on NEW content generation, and July's content is already generated (`upcoming: 0`), so nothing re-triggers it. A `generate_gbp_pack` tick returned `added: 0` for exactly this reason.
2. **August rows do not exist at all** â€” the paying customer is >30 days into a paid month with no current-cycle ledger.

PR #269 makes the writer able to *find* a row (expansions verified live: `[jiya-makeover, d79d690f61b3]` Ã— `[gbp_suggestions, google_business_profile_suggestion]`). It cannot help when the current cycle has no rows. **Monthly cycle seeding is the missing piece â€” not yet built.**

### â›” WS3 â€” 08-06 evidence is GONE (my fault)
`docker logs` cannot predate `2026-08-07T01:00:38Z` â€” **the deploy recreated every container and destroyed the 08-06 logs.** Loki is running but **completely empty** (every label returns no values, every query `totalLinesProcessed: 0`) â€” nothing ships logs to it. So the shared-downstream hypothesis can be neither confirmed nor falsified from logs.

What multi-day counters DO show (`agent_events.meta_json`):
| day | queries_run | queries_empty | lookups_used | new | leads |
|---|---|---|---|---|---|
| 08-01 | 10 | 0 | 324 | 130 | 226 |
| 08-04 | 11 | 0 | 275 | 185 | 295 |
| 08-05 | 16 | 3 | 248 | 141 | 260 |
| 08-06 | 12 | **11** | **0** | 28 | **4** |

**But both lead sources collapsed together** â€” `google_maps` 131â†’2 AND `import` 129â†’2 â€” which a Places-only cause does not explain. jsonl only halved (283â†’119) while leads fell 98%.

Live now: Places is **healthy** (HTTP 200, 5 results raw; prod path returned 60), `places_bucket: fail 0`, no cooldown key. Falsified: Places-dead, dedupe exhaustion, rotation end/reset, junk validation.

**Next evidence â€” free:** watch today's scheduled `prospect` run (~11:34 IST) with logs intact. Do not ship a WS3 fix before that.

### Parked additions
- Loki ingests nothing â€” observability gap in its own right.
- `qdrant` fail_rate **1.0**, 450 failures/24h, `"fastembed model not ready within 90s"`.

## ðŸ”´ Standing lessons
1. **Never `cat data/<file>` as prod truth.** Resolve via the owning module â€” `clients_store._CLIENTS_FILE()`, `platform_dial._cfg_path()`. Live marketing store is `/var/lib/leadgen/runtime/customers/marketing_clients.jsonl` (3 rows); the `data/` copy is stale (8 rows) and caused a wrong finding this session.
2. **CI required checks bind to the head at dispatch time.** Push after dispatching â†’ PR stays BLOCKED though CI passed. Merging one PR makes the rest `BEHIND` â†’ `gh pr update-branch` **then** re-dispatch.
3. **`gh pr merge --admin` cannot bypass this ruleset** (no `bypass_actors`). Every merge here was a normal merge with the three required checks genuinely green.
4. **The runtime-data debt ratchet is a MUST-PASS gate** and it caught a real bug: a hardcoded `data/backups` backup path. It classifies a write by the path expression at the `open()` site â€” resolve and write must be in the **same function** or it still fails.

## 2026-08-07 eve â€” Coordination Hub enablement (independent workstream) DONE

What is it: the in-product multi-tool dashboard (`/app/coordination`, `COORDINATION_HUB_ENABLED`) where Cursor / Claude Code / OpenCode / Bolt / MonkeyCode post HMAC-signed heartbeats and see each other on one pane. Element: `app/platform/coordination_hub_auth.py`, `frontend/coordination_hub.html`; event store `data/coordination_hub/` (presence.json + events.jsonl).

### Delivered & verified
- **PR #279** (`feat/coordination-hub-opencode`) â€” registered `opencode`/`bolt`/`monkeycode` in `_KNOWN_TOOLS` + 2 contract tests. **Deployed** at `/health` = `7fac5259`, 5/5 zero skew, kill-dance done, CI clean.
- Per-tool HMAC secrets generated on prod `.env` (`COORD_HUB_TOOL_CURSOR/CLAUDE/OPENCODE/_SECRET` + `COORD_HUB_BUZZ_SECRET`, openssl rand -hex 32). Backups: `.env.bak-coordhub-20260807_161718`, `.env.bak-coordhub-killrestore-*`. `VOICE_LAUNCH_KILL` restored to `0`.
- End-to-end proof: inside container `python /tmp/coord_hb_probe.py` â€“ `hub_enabled_in_container True`, all 3 tool secrets present, then real HMAC heartbeats for cursor/claude/opencode all returned `http=200 ok=True`, persisted to `presence.json` + `events.jsonl` (host=verify-probe).
- **`http://127.0.0.1:8080` inside the container, `8000` on the host** â€” used 8080 for the probe (the known port landmine).

| current | |
|---|---|
| prod `/health` | **`7fac5259`** (= PR #279) — hub live, presence verified via probe, nothing auto-wired yet |
| `origin/main` HEAD | **`5ae5a4b9`** (PR #280 heartbeat script) — **NOT deployed** (scripts-only, no runtime impact) |
| `scripts/coord_hub_heartbeat.py` | PR #280 merged to main; HMAC heartbeat primitive, stdlib-only, graceful when secret absent; verified `http=200` against public https://leadsgenai.in with the real opencode secret |

### Notes / open
- **No tool auto-sends heartbeats yet.** The script exists; wiring is per-tool. Local tools need their own `COORD_HUB_TOOL_<ID>_SECRET` in the local env (secrets are on the VPS .env, NOT copied to the dev machine). Owner decides distribution. The `/app/coordination` Tool Script tab documents the endpoint.
- **CodeQL fight worth remembering:** `py/clear-text-logging-sensitive-data` flagged even a print that referenced only `tool_id`, plus a `# lgtm[...]` comment did NOT suppress it. The fix that worked: make the error message **fully static** (no f-string) so no taint can reach `print`. Use that pattern for any future dev script touching env-secret lookups.
- CI gotchas re-confirmed this session: `gh pr update-branch` (branch BEHIND) -> full CI re-run; `gh pr merge --admin` cannot bypass the ruleset; only merge with the three required checks genuinely green. Changing `origin/main` recomputes mergeability — wait for `enable`/`checks` to go green again.
