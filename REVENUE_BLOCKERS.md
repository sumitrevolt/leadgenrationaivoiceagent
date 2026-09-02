# TOP 10 REVENUE BLOCKERS (RANKED MATRIX)
**Date:** 2026-08-22 (updated same day after live verification)
**Framework:** `Score = (Revenue Impact [1-10] × Probability [1-10] × Fix Speed [1-10]) / Risk [1-5]`

> **STATUS UPDATE 2026-08-22 (live-verified):**
> - ~~BLK-01 UPI stale queue~~ → **RESOLVED**: 3 synthetic pilot rows rejected with audit trail
>   (backup `upi_payments.json.bak-pilotcleanup-20260822`). Residual: 1 ambiguous row
>   `upi_12_bd74bae8` ("REAL-CHECK") pending OWNER approve/reject — payment authorization gate.
> - Baseline corrected: 2 paying customers / ₹3,998 MRR (see `DAY_0_REVENUE_BASELINE.md` correction log).
>
> **STATUS UPDATE 2026-08-23 (Hermes Desktop session, live-verified):**
> - ~~BLK-11 WAHA dead~~ → **RESOLVED END-TO-END**: session flapping root-caused (WORKING→FAILED,
>   `me:null`), restart+fresh QR scan done (owner, business number ***2607 matched), phir
>   manual sweep trigger se `weekly_digest {"due":2,"sent":2}` — Jiya + Kamal dono ko REAL
>   WhatsApp delivered. Test Hotel Spa (fake number 9999999998) correctly blocked by
>   recipient-exists fail-closed gate = expected. BLK-05 auto-unlocked.
> - ~~BLK-01 Hot Queue UPI path~~ → **DEPLOYED LIVE**: PR #430 merged (`31de993e`) via canonical
>   `deploy_vps.sh`, `/health`=`31de993e` verified, rollback lineage `2e292d07` captured.
>   42 warm leads ke cards pe ab UPI payment path hai.
> - BLK-02 (trial nudges) → **NO ACTIVE TARGETS**: DB probe me koi active trial user nahi mila
>   (Sharma Solar variants bhi nahi). Feature tab banega jab real trials aayengi — backlog.
> - BLK-03 (Kamal onboarding RED) → **PARTIAL**: digest delivery fixed; 46-pending-posts +
>   missing-inputs rescue ABHI BAAKI (data model: accounts/users/files, `clients` table nahi).
>
> **STATUS UPDATE 2026-08-23 #2 (BLK-03 RESOLVED + ops tools live):**
> - ~~BLK-03 Kamal rescue~~ → **RESOLVED**: store record healthy nikla (pehla probe galat
>   legacy file padh raha tha; runtime truth = `/var/lib/leadgen/runtime/customers/`).
>   Asli issue = 25-din-purane 46 stale-pending approvals. Canonical `content_approval.approve()`
>   se backup ke saath clear kiya: **43/46 approved**, 3 video_ad REFUSED by containment design
>   (coordinated path chahiye = expected). Backup: `content_approvals.jsonl.bak-blk03-*`.
>   Socials unconnected hain isliye koi external publish nahi hua (internal queue state hi).
> - **OPS MCP TOOLS LIVE** (PR #432, prod `ff1153e9`): `/api/ops/hotqueue|hotqueue/action|
>   revenue-summary` /mcp pe exposed, admin+Bearer double-gated.
> - **HARNESS_SESSION_EVENTS=1 ARMED** (owner-approved; ADR-187; backup `.env.bak-harness-*`).
> - Remaining (new rank order): (a) Kamal brand-kit colors/tagline + socials connect = OWNER/
>   customer inputs; (b) 3 video_ad approvals via coordinated path; (c) Sharma Solar trials
>   ab mile (file-store me 3 active) = BLK-02 wapas relevant; (d) B2B lgmcp_ keys dormant.

> **STATUS UPDATE 2026-08-23 #3 (BLK-02 SHIPPED + DATA TRUTH):**
> - ~~BLK-02 missing~~ → **BUILT + DEPLOYED + ARMED**: PR #434 merged (`20ce9552`), CI 22/22
>   green, canonical deploy OK, `TRIAL_NUDGE_ENABLED=1` live in worker+scheduler
>   (backup `.env.bak-trialnudge-20260823025516`). Daily beat 09:50 IST.
> - **DATA CORRECTION:** "Sharma Solar ×3 active trials" claim galat nikla — current
>   `marketing_clients.jsonl` me sirf 1 trial-flagged record hai ("Fresh Test Biz 42",
>   status=active, email=null → ineligible). Eligible trials ABHI ZERO hain → 09:50 runs
>   will send 0 until a real expiring/expired trial signup occurs. Job self-fires on first
>   real target. Admin UI tab for nudge stats = backlog (API-only-adhoora rule).

---

## Ranked Blocker Table

| Rank | Blocker ID | Revenue Blocker Description | Impact | Prob | Speed | Risk | Score | Immediate Action & Fix Path |
| :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| **#1** | `BLK-11` | **WhatsApp delivery path DEAD (WAHA session `default` FAILED → SCAN_QR_CODE)**<br>All paid-customer weekly digests + delivery messages are fail-closed blocked (`data/delivery_stuck.jsonl`: Jiya 20×, Kamal 14×, TestHotelSpa 124×). Churn risk on BOTH paying customers. | 10 | 10 | 9 | 1 | **900** | Owner scans the QR (delivered in chat 2026-08-22). Verify: session `/api/sessions/default` → `WORKING`, then next digest sweep sends. |
| **#2** | `BLK-03` | **Kamal dar (PAYING) stuck RED in onboarding**<br>Setup 20%, 46 posts approval-pending (44 urgent-48h), missing inputs offer/brand/social/approval, 2 failed automations, health_score=0. ₹1,999 collected, near-zero published value. *(Ranked above BLK-02 despite lower score: paying-customer churn protection.)* | 9 | 9 | 7 | 1 | **567** | Admin `/app/admin` Delivery Cockpit: fill Kamal's missing business inputs, bulk-approve/clean his content queue, clear 2 failed automations. |
| **#3** | `BLK-02` | **Trial-to-Paid Conversion Nudge Gap**<br>Active trials (Sharma Solar etc.) lack automated expiration + upgrade-to-Starter UPI cards. | 9 | 8 | 9 | 1 | **648** | Automated trial-expiry notice with direct UPI link to ₹1,999/mo Starter. |
| **#4** | `BLK-05` | **Voice Post-Call Instant Offer Dispatch**<br>`POST_CALL_WHATSAPP=1` + `VOICE_CLOSE_WHATSAPP=1` are SET, but they ride the SAME dead WAHA session until BLK-11 is fixed. | 9 | 7 | 8 | 1 | **504** | After WAHA relink, send one test offer package end-to-end. |
| **#5** | `BLK-06` | **High-Intent ICP Lead Filtering & Scoring**<br>Broad prospecting dilutes the 25/day email warmup cap. | 8 | 8 | 7 | 1 | **448** | Enforce 0–100 scoring before daily outreach queue dispatch. |
| **#6** | `BLK-07` | **Automated Multi-Touch Stalled-Lead Follow-ups**<br>`/audit`/`/demo` viewers stall without 48h/96h value-first sequences. | 8 | 7 | 7 | 1 | **392** | Wire follow-ups via existing `email_followup` scheduler. |
| **#7** | `BLK-08` | **Frictionless Manual UPI Onboarding Flow**<br>Payers need instant receipt confirm + 1-click provisioning. | 8 | 7 | 7 | 1 | **392** | Owner-scoped `UPI_AUTO_ACTIVATE` review + approval queue hygiene in `/app/admin`. |
| **#8** | `BLK-09` | **Own-Brand Video/Social Proof Automation**<br>Daily HyperFrames video cycle + Postiz posting consistency for trust building. | 7 | 7 | 7 | 1 | **343** | Keep `VIDEO_AD_CYCLE=1`, `DAILY_VIDEO_CLIENTS=*` running daily. |
| **#9** | `BLK-10` | **Unified Admin Command Center Visibility**<br>No single real-time view integrating bot tasks, revenue counters, pending approvals. | 7 | 8 | 6 | 1 | **336** | Hermes Control Plane panel in Admin (watchdog + scoreboard + telemetry). |
| **#10** | `BLK-04` | **GSC pSEO rank tracking LIVE but empty series**<br>`GSC_ENABLED=1` active, daily snapshots running, domain verified — series all zeros (new/low-indexed domain). | 6 | 7 | 6 | 2 | **126** | URL-inspection submit key pSEO pages; sitemap/internal-link push in daily job. |

---

## Execution Rule
Fix blockers strictly in rank order while #1–#2 remain active. Never work on cosmetic or theoretical items while BLK-11 (WhatsApp dead) is unresolved — it gates BLK-05 and every customer-facing message path.
