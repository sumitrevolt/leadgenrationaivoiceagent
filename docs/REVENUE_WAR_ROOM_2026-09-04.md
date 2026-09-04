# Daily Revenue War Room — 2026-09-04 (08:30 IST)
**Sprint Day 2 of 8** · window 2026-09-03 → 2026-09-10 · **7 days remaining (including today)**

**Authority respected:** plan + local fixes only. No deploy, no SSH, no remote state change, no compliance gate touched.

**Ladder in force** (`docs/REVENUE_TARGET_REBASELINE_2026-09-03.md` §3): Floor ₹9,995 · Base ₹16,000 · Stretch ₹25,000 — all *net-new collected*. ₹5,00,000 = 90-day milestone, not measured here.

---

## 1. Production truth — partially UNREACHABLE (stated explicitly, not guessed)

| Check | Result | Source |
|---|---|---|
| `GET https://leadsgenai.in/health` ×3 | HTTP 200, `status: healthy`, `version: 37a1daf8`, `environment: production`, uptime `12h 44m 19s → 12h 44m 21s` (**monotonic, no divergence**) | live probe 2026-09-04 08:41–08:44 IST |
| `GET /api/ops/revenue-summary` | **HTTP 401** | live probe — admin gate working, no token in this session |
| `GET /api/billing/invoices` | **HTTP 401** | live probe |
| `GET /api/ops/hotqueue` | **HTTP 401** | live probe |
| `data/invoices.jsonl`, `data/upi_payments.json` locally | **do not exist** | `ls` → No such file |
| WAHA (WhatsApp) `127.0.0.1:3111` locally | **HTTP 000 — unreachable** (VPS-only) | `curl` probe |

**Consequence:** invoice ledger, hot queue, and active accounts **cannot be verified from this session**. Per the no-guessing rule, the revenue line below is *"no confirmed collection"*, not *"confirmed zero"*.

### What the local bot fleet reports (independent of the admin API)

Source: `command_center/data/esc_0904_0826.jsonl` (mtime **2026-09-04 08:27 IST**), corroborated by `esc_0904_0815.jsonl` (08:17 IST):

| Field | Reported value |
|---|---|
| `verified_revenue` | **₹1,999 — Jiya, INV/2026-27/0001, SOLE payer** |
| `wa_msg_id` | **0** (no WhatsApp send has ever returned a message id) |
| `sip_host/user/pass/did/provider_len` | **0,0,0,0,0** (no DID landed) |
| `dialer_proc` | **0** (dialer dead, day 5) |
| `leads` | **0** |
| `hot_queue_0904` | **ABSENT** |

### Baseline dispute — still unresolved, not silently resolved

- `DAY_0_REVENUE_BASELINE.md:16` — lifetime ₹7,997 / MRR ₹3,998 / 2 customers.
- Its own line items (INV/0001 + 0014 + 0015) sum to ₹5,997 — an unreconciled ₹2,000 arithmetic gap.
- Today's bot fleet and `memory/decisions.md:1150` both say **₹1,999 verified cash (Jiya only)**.
- **Planning rule in force:** treat ₹1,999 as verified; ₹3,998 / ₹5,997 / ₹7,997 as unverified. The ladder measures *net-new* collections, so this does not move the target — but it must be reported honestly.

---

## 2. Gap against the ladder

| Metric | Value | Basis |
|---|---|---|
| Net-new collected **today (2026-09-04)** | **₹0 confirmed** — ledger unreachable | §1 |
| Net-new collected **sprint to date (Day 1 + Day 2)** | **₹0 confirmed** | Day-1 close (`progress.md:474`) + §1 |
| Gap to **Floor ₹9,995** | **₹9,995** (100%) | arithmetic |
| Gap to **Base ₹16,000** | **₹16,000** (100%) | arithmetic |
| Gap to **Stretch ₹25,000** | **₹25,000** (100%) | arithmetic |
| Required pace to Base | **₹2,286/day** over 7 days | ₹16,000 ÷ 7 |

---

## 3. Highest-ranked UNRESOLVED blocker

**`BLK-11` — WhatsApp delivery path (rank #1, score 900, `REVENUE_BLOCKERS.md:55`).**

The record is contradictory and must be carried as unresolved:

- `REVENUE_BLOCKERS.md:11-16` claims BLK-11 **RESOLVED** on 2026-08-23 with `weekly_digest {"due":2,"sent":2}`.
- `progress.md:108` records the session left at **`SCAN_QR_CODE`** since 2026-08-22 with no confirmation it was scanned.
- **Today's hard evidence:** `data/outreach_drafts/JIYA_UPSELL_READY_TO_SEND_2026-09-03.txt` lines 69–72 — the PROOF-OF-SEND block is **still blank, 24 hours after the draft was written** (file mtime 2026-09-03 09:38, unchanged). Bot fleet reports `wa_msg_id: 0`.

Under the evidence rule (no claim without proof), **BLK-11 is unresolved** and it gates `BLK-05` and every customer-facing message path.

**Why it outranks everything else:** it blocks an *already-drafted, already-verified, highest-probability cash ask*. Every other blocker blocks measurement or targeting; this one blocks cash.

---

## 4. Today's owner action list (5 actions, ranked)

### A1 — Send the Jiya ₹19,990 annual-prepay ask (≈10 min)

**Correction to the standing plan:** the Combo ₹5,999 upsell is **NOT available to Jiya**. `beauty_makeover` appears in none of the Combo bands — Band A (insurance, coaching, solar, hospital, upskilling, travel), Band B (home loans, study abroad, dental, finance advisory, CA & legal), Band C (IVF, immigration, commercial solar/HVAC, hair transplant). Verified at `app/marketing/combo_packages.py:57,91,125`. The correct ask is **Starter annual prepay ₹19,990** (10 × ₹1,999 = 2 months free), verified at `app/marketing/packages.py:196`.

- **Owner action:** on the VPS confirm WAHA is `WORKING`, then send the main message verbatim from `data/outreach_drafts/JIYA_UPSELL_READY_TO_SEND_2026-09-03.txt`. If she declines, send the §6.1 fallback line (locks the monthly, prevents churn).
- **Expected impact:** **₹19,990 collected** = 200% of Floor, 125% of Base. Fallback path = **₹1,999** renewal.
- **Proof of completion:**
  ```bash
  curl -s http://127.0.0.1:3111/api/sessions/default   # → "status":"WORKING"
  ```
  The WAHA send response **must contain a non-null message `id`**. Then fill lines 69–72 of the draft file (time / reply / WAHA id / operator) and paste it into `progress.md`.

> Compliance: Jiya is an existing paying subscriber. This is a service/renewal conversation, not cold outbound. Cold WhatsApp stays OFF.

### A2 — Work the 09:00 IST hot-queue pack (≈15 min, runs automatically)

The pack job fires at **09:00 IST** — `app/worker.py:574-578` (`crontab(hour=9, minute=0)`) with `timezone="Asia/Kolkata"`, `enable_utc=False` (`app/worker.py:195-196`). It had legitimately not run yet at 08:26 IST, so the bot fleet's "ABSENT" alarm was premature, not a fault.

- **Owner action:** take the ntfy push on topic `leadgen-d6b984bd` (≈09:05 IST) and close the top cards via the embedded 1-click UPI path (deployed, PR #430).
- **⚠️ Caveat:** the customer-suppression guard shipped today is **local-only, NOT deployed**. Today's prod pack will still lack it. Manually verify no row's phone is Jiya's (`+919876543210`) or Kamal's before sending.
- **Expected impact:** not stated — zero rows are verifiable until the pack exists.
- **Proof of completion:** ntfy push received with a row count, and the pack file present:
  ```bash
  docker exec leadgen_app ls -la /opt/leadgen/data/hot_queue_for_owner_2026-09-04.*
  ```

### A3 — Pull Kamal's record and send the ₹1,999 renewal (≈15 min)

- **Owner action:** read Kamal's `plan` + `niche` from the VPS client store. Invoice INV/0015 is dated **2026-08-03** → **~32 days overdue** on a ~29-day cycle. Send the renewal. **If** his niche falls in Band A/B/C, quote Combo **₹5,999** instead of ₹1,999.
- **Expected impact:** **₹1,999** renewal; **+₹4,000** if he qualifies for Combo (undecidable until the niche is read — not estimated here).
- **Proof of completion:** a new `INV/…` dated **2026-09-04** in the ledger (`GET /api/billing/invoices` with token → HTTP 200).

### A4 — Decide the `upi_12` ambiguous row (≈2 min)

- **Owner action:** approve or reject. It has blocked the payment-authorization gate since **2026-08-22 (13 days)** — `DAY_0_REVENUE_BASELINE.md:18`.
- **Expected impact:** no figure is recorded for this row anywhere reachable, so **none is claimed**. Value is clearing the gate.
- **Proof of completion:** the queue no longer surfaces `upi_12`; decision recorded in `progress.md`.

### A5 — Make collections verifiable (≈20 min, ₹0 direct)

Without this, every future day-close reports "unverifiable" and the ladder cannot be measured.

- **Owner action:** (i) provision a read-only ops token (or a scheduled ledger export); (ii) resolve the pre-existing red ratchet (§6) **after review, not by reflex**.
- **Expected impact:** ₹0 directly; unblocks measurement for the remaining 7 days.
- **Proof of completion:**
  ```bash
  curl -s -H "Authorization: Bearer <token>" https://leadsgenai.in/api/ops/revenue-summary   # → HTTP 200
  .venv\Scripts\python.exe -m pytest tests/test_runtime_data_a7_ratchet.py -q               # → green
  ```

---

## 5. Local fix shipped today (NOT deployed)

**Gap:** an existing paying customer's phone number could appear in an outbound prospecting pack. Proven instance — `data/hot_queue_for_owner_2026-08-31.csv` contains exactly one row, phone `+919876543210`, which is **Jiya Makeover's number** (`data/marketing_clients.jsonl:7`).

**Change — `app/platform/hot_queue_owner_pack.py`:**
- New `_last10()` / `_row_phones()` / `_existing_customer_phones()`. Active-customer phones are stripped from the pack **before** any `wa.me` link or UPI kit is generated, so a suppressed row never has a sendable URL attached.
- Matching on the **last 10 digits**, so `+91…`, `91…` and bare-10 forms all collide correctly.
- Rows with no `phone` but a customer `wa_link` are also excluded.
- **Fail-visible, not fail-silent:** if the client store cannot be read, the run returns `customer_suppression: "unverified"` and writes a WARNING into the MD, rather than pretending there were no customers.
- The pack still never raises: the lookup is wrapped, and a crash degrades to `unverified`.

**Tests — `tests/test_hot_queue_owner_pack.py`:** 5 new tests (exclusion in both `+91` and bare forms, `wa_link`-only row, unverified state surfaced, lookup explosion survives, `_last10` normalisation).

**Verification evidence:**

| Gate | Result |
|---|---|
| `pytest test_hot_queue_owner_pack.py test_hot_queue_payment_path.py test_hot_queue.py test_billing_truth_2026.py` | **35 passed**, exit 0 |
| `ruff check app` | **All checks passed** |
| `scripts/prod_check.py` | **`[OK] ALL CHECKS PASSED - ready to deploy`** — 1353 routes, 54 pages 0 gaps, automation 0 gaps, API.md synced (1380 ops) |
| `scripts/check_secrets.py` | **`[OK] no secrets detected`** (2 files changed vs HEAD) |
| `GET /health` ×3 post-change | 200 / 200 / 200, uptime monotonic |

**Deploy is owner-gated and was not performed.**

---

## 6. Pre-existing red gate — reported, deliberately NOT auto-fixed

`tests/test_runtime_data_a7_ratchet.py::test_no_allowlist_or_baseline_relaxation` fails: **`assert 98 == 85`**.

- **Proven pre-existing:** `git stash push` of today's two changed files → the test **still fails at HEAD** (`2e348479`). Restored immediately after. Not caused by this session.
- **Why it was not bumped unattended:** this is a pinned anti-relaxation control. Raising 85 → 98 without reviewing the 13 new entries would be exactly the silent loosening the ratchet exists to prevent.
- **Related observations worth owner review:** commit `c32378f7` widened one entry's `access_modes` from `["CREATE"]` to `["CREATE","REWRITE"]` and broadened two `path_pattern`s from `/opt/leadgen/media/content_os/last_run_*.lock` to `/opt/leadgen/media/content_os/last_run_`. Broadening a path pattern is the shape a relaxation takes — verify intent before the count is updated.
- **Also noted (not fixed):** `ruff check tests` reports **96 pre-existing errors** across the test tree. `ruff check app` is clean and is the configured gate.

---

## 7. Local owner-tooling state (read-only)

| Check | Result |
|---|---|
| Hermes backend `127.0.0.1:9119` | **LISTENING** — holding since ~14:43 IST 2026-09-03 (**~18h**). The `--port 0` throwaway path is not in use; the launcher fix from 2026-09-03 is holding. |
| OmniRoute `127.0.0.1:20128` | **LISTENING** |
| Claude proxy `127.0.0.1:22000` | **LISTENING** |
| `LeadGen-OmniRoute-DSH-AutoStart` scheduled task | Still **Disabled** — the durable fix (enabling it) remains an owner action. |

---

## 8. Compliance statement

No DND / TRAI / consent / opt-out gate was weakened, disabled, or bypassed. Cold WhatsApp remains OFF; the 25/day email cap is unchanged. No synthetic payment, no projected or estimated revenue reported as collected. All actions were read-only HTTP probes, local file reads, local port queries, and local code changes. `payment_verification_method` remains `owner_confirmed_upi`; `PROVIDER_VERIFIED` was not set and remains unreachable by design.
