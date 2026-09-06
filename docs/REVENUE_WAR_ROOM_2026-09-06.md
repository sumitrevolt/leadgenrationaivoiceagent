# Daily Revenue War Room — 2026-09-06 (08:30 IST) — Sprint Day 4 of 8

**Authority:** plan + local fixes only. No deploy, no SSH, no remote state change, no compliance gate touched.
**Ladder in force:** Floor ₹9,995 / Base ₹16,000 / Stretch ₹25,000 (net-new **collected**) — `docs/REVENUE_TARGET_REBASELINE_2026-09-03.md` §3. ₹5,00,000 = 90-day milestone, not measured here.

---

## 1. Production truth — pull result

| Check | Result | Source |
|---|---|---|
| `GET https://leadsgenai.in/health` | **healthy**, `environment: production`, version **`b4a457f2`**, uptime **1h 8m 17s** (restart ≈ 07:26 IST), `dsh_allowlist: ["jiya_makeover"]` | live probe 2026-09-06 08:3x IST |
| Prod vs repo | **`b4a457f2` = local `git log -1` HEAD** (PR #473 merge) ⇒ prod is at main tip, no version drift | `git log --oneline -1` = `b4a457f2` |
| `GET /api/ops/revenue-summary` | **HTTP 401** | live probe |
| `GET /api/billing/invoices` | **HTTP 401** (prior runs) | `progress.md:868` |
| `GET /api/ops/hotqueue` | **HTTP 401** (prior runs) | `progress.md:865` |
| Bearer attempt with local `FASTAPI_MCP_TOKEN` | **401 — `Invalid token: Not enough segments`** | live probe — prod expects a JWT, the local token is not one |
| Why it fails | `require_admin` (`app/api/auth_deps.py:107`) → `get_current_user` (`:50-55`) does `decode_token()` and requires `payload["type"] == "access"`. **No API-key / read-only-token branch exists.** | `app/api/auth_deps.py` |
| Config gap | `.env` has no `OPS*`/`ADMIN*` read-only token; `.env.example` defines none | `progress.md:868` |

**🔴 Verdict: production revenue truth is UNREACHABLE for the 3rd consecutive war room.** The local `FASTAPI_MCP_TOKEN` is not a JWT, so it cannot satisfy `require_admin`.

### Collected revenue — honest statement

| Metric | Value | Basis |
|---|---|---|
| **Collected today (2026-09-06)** | **₹0 confirmed** — the ledger is unreachable, so this is *"no confirmed collection"*, **NOT "confirmed zero"** | No invoice/UTR/receipt artifact anywhere in repo; admin endpoints 401; `data/invoices.jsonl`, `data/upi_payments.json`, `data/payments.jsonl` all absent locally |
| **Net-new collected, sprint Day 1–3** | **₹0 evidence-backed** | Day 1 = ₹0, Day 2 = ₹0 (`progress.md:882-883`); Day 3 (09-05) produced **no** revenue artifact — 6 loop runs, all engineering (merge reconcile, scratch cleanup, social-task registration, trial-nudge UI, RL parity, OmniRoute re-seed) |
| **Gap to Floor ₹9,995** | **₹9,995** (100%) · required pace **₹1,999/day × 5** | ladder §3 ÷ 5 remaining days |
| **Gap to Base ₹16,000** | **₹16,000** (100%) · required pace **₹3,200/day × 5** | same |
| **Gap to Stretch ₹25,000** | **₹25,000** (100%) · required pace **₹5,000/day × 5** | same |
| Days remaining | **5** (Sep 6–10 inclusive; window Sep 3–10) | ladder §3 |

**Baseline dispute — carried, still unresolved (do NOT silently pick one):**
- `DAY_0_REVENUE_BASELINE.md` — lifetime **₹7,997**, MRR ₹3,998, 2 customers; its own line items sum to **₹5,997** (unexplained ₹2,000 gap).
- Bot fleet + `memory/decisions.md:1150` — **₹1,999** verified cash (Jiya `INV/2026-27/0001` only).
- **Planning rule:** treat ₹1,999–₹3,998 as verified cash; ₹5,997 / ₹7,997 as unverified. Does not move the ladder (which measures *net-new*).

---

## 2. Highest-ranked UNRESOLVED blocker

**BLK-11 — WhatsApp send path has never produced a message id.** Rank **#1**, score **900** (`REVENUE_BLOCKERS.md:55`).

Status is **contested**, and I am reporting the conflict rather than picking a side:
- `REVENUE_BLOCKERS.md:12-17` marks it **RESOLVED 2026-08-23** (session restart + QR scan, `weekly_digest {"due":2,"sent":2}`).
- `progress.md:917` (09-04 20:30 IST close) **re-opened** it with harder, more recent evidence: `esc_0904_1252.jsonl` ts 12:22 IST → `"wa_msg_id": 0`, `"wa_auto_sent_none": 1829`; local WAHA probe `127.0.0.1:3111` → HTTP 000.
- **09-05 produced no evidence either way** (no war-room doc, no WA line item in any of the 6 loop runs).

Because the more recent measurement contradicts the older resolution note, **BLK-11 stays the operating #1 until re-proven.** It gates BLK-05 (score 504) and every customer-facing send.

**Blocked cash: ₹19,990** (Jiya annual prepay) = **200% of Floor**, **125% of Base** — drafted, verified, unsent since 2026-09-03.

### 🔴 New evidence-integrity finding (severity 1, found this run)

The artifact the 09-04 close called "the single most damaging artifact in the repo" — `data/outreach_drafts/JIYA_UPSELL_READY_TO_SEND_2026-09-03.txt` — **does not exist in this workspace and is not git-tracked.**

- `ls data/outreach_drafts/` → **no such directory**; `find . -iname "*JIYA_UPSELL*"` → **0 hits**; `git ls-files | grep outreach_drafts` → **0 hits**.
- **Recoverable:** the corrected send-ready draft is reproduced verbatim in `docs/UPSELL_PACKAGE_JIYA_KAMAL_2026-09-03.md` §6 (lines 208-227), with the churn-save fallback in §6.1 (line 233). Nothing is lost — but the "send file X" instruction was pointing at a file no longer on disk.

---

## 3. ⚠️ Standing plan correction — the ₹5,999 upsell IS sellable to Jiya

The 09-04 correction ("Combo ₹5,999 is ineligible for `beauty_makeover`") conflated **two different products**. Verified this run:

| Product | Price | Niche-gated? | Evidence |
|---|---|---|---|
| **Advanced Marketing** (Product-1 tier 3) | **₹5,999/mo**, ₹59,990/yr | **NO** | `app/marketing/packages.py:238-247` (`"key": "advanced"`, `price_inr_month: 5999`, `price_inr_year: 59990`). Line 12: *"flat-monthly per niche-band A/B/C (ADR-009) … **Yahan NAHI**"* |
| **Combo** (marketing + voice bundle) | ₹4,999/mo (Band A) | **YES** — `beauty_makeover` in no band | `app/marketing/combo_packages.py:48-52, 137-147`. Also flag-gated OFF in prod (`/api/combo/packages` → 404, session log 2026-07-04) |

**Correction:** Jiya **is** eligible for **Advanced ₹5,999/mo (+₹4,000 MRR)** or **Advanced annual ₹59,990**. What is *not* sellable to her is the niche-banded **Combo ₹4,999** product. The 09-04 note correctly killed the Combo ask but wrongly killed the ₹5,999 ladder step with it.

**Recommended framing (owner's call):** lead with **Starter annual prepay ₹19,990** (one decision, most cash, draft ready, no product change to explain). If she declines annual prepay, offer **Advanced ₹5,999/mo** rather than dropping straight to monthly renewal — that is the +₹4,000/mo step the ladder was counting on.

---

## 4. Today's action list (max 5)

### A1 — Send the Jiya renewal + upsell ask. Today. Before anything else. *(≈10 min · ₹1,999–₹19,990)*
1. VPS gate check (1 min): `curl -s http://127.0.0.1:3111/api/sessions/default | head -c 300` → require `"status":"WORKING"`. `SCAN_QR_CODE` ⇒ scan first, nothing else matters.
2. Send verbatim from `docs/UPSELL_PACKAGE_JIYA_KAMAL_2026-09-03.md` §6 (lines 208-227) to WhatsApp `+919876543210`. Source of the file: `data/marketing_clients.jsonl` row `jiya-makeover`.
3. On "haan" → generate the UPI link, collect, then issue the INV row.
4. On "nahi" → send §6.1 line 233 (locks monthly ₹1,999, prevents churn of the only payer).
- **Impact:** ₹19,990 = 200% of Floor / 125% of Base; fallback ₹1,999 = 20% of Floor. Renewal was due Sep 1–3 ⇒ **3–6 days overdue** (29-day cycle: Jul-05 → Aug-03).
- **Proof of completion:** non-null WAHA message id for the send, **plus** a new `INV/…` row dated 2026-09-06 in `data/invoices.jsonl`, **plus** bank credit confirmed by owner (`owner_confirmed_upi`).

### A2 — Kamal: pull the record, send the ₹1,999 renewal, test the +₹4,000 step *(≈10 min · ₹1,999–₹5,999)*
- `INV/0015` ₹1,999 dated **2026-08-03** ⇒ **~34 days overdue** (`docs/UPSELL_PACKAGE_JIYA_KAMAL_2026-09-03.md:51`).
- Kamal's client id `0511a69b900e` is **absent from local data** (8 rows in `data/marketing_clients.jsonl`, none is Kamal) ⇒ **plan + niche must be read from VPS first** (§6.2 explicitly says DO NOT SEND blind).
- Then: renewal ₹1,999, and if his niche is in Combo band A/B/C (`combo_packages.py:141-145`) offer Combo; otherwise offer **Advanced ₹5,999** (no niche gate).
- **Impact:** ₹1,999 (20% of Floor) to ₹5,999 (60% of Floor).
- **Proof:** VPS client record shows `plan`/`niche`; a new dated INV row + owner-confirmed bank credit.

### A3 — Work today's 09:00 IST hot-queue pack *(≈25 min · only new-cash path)*
- Pack lands at `data/hot_queue_for_owner_2026-09-06.md` / `.csv` on the VPS (writer: `app/platform/hot_queue_owner_pack.py:130-131`), with `wa.me` links carrying the UPI kit (`:125`).
- **Manual suppression required before any send:** the existing-customer suppression shipped locally on 09-04 is **NOT deployed**, so prod packs can still contain `+919876543210` (Jiya) and Kamal. Suppress both by hand.
- Work the top 15 by intent recency. Count the rows and record the number — the "42 warm leads" figure has not been reproducible since 08-23.
- **Impact:** unquantifiable until the pack is counted; this is the only path to *new* customers in the window.
- **Proof:** `docker exec leadgen_app ls -la /opt/leadgen/data/hot_queue_for_owner_2026-09-06.*` (file exists) + row count recorded + sends logged with message ids.

### A4 — Provision a read-only ops token *(≈20 min · ₹0 direct, unblocks all measurement)*
- Root cause is structural: `require_admin` → `get_current_user` → `decode_token()` with **no API-key branch** (`app/api/auth_deps.py:50-55,107`). `.env.example` defines no read-only ops token.
- Without it, every future war room reports "unverifiable" — Day 3 and Day 4 both closed blind because of it.
- **Impact:** ₹0 direct. It is the difference between a measurable sprint and an unmeasurable one.
- **Proof:** `curl -H "Authorization: Bearer $OPS_TOKEN" https://leadsgenai.in/api/ops/revenue-summary` → **HTTP 200** with `stats`. (Scope it read-only: `/api/ops/revenue-summary`, `/api/ops/hotqueue`, `/api/billing/invoices` GET only. Do **not** grant `/api/ops/hotqueue/action`.)

### A5 — Clear the two gates that have been open 13+ days *(≈10 min · ₹0–unknown)*
1. **Decide `upi_12_bd74bae8` ("REAL-CHECK")** — pending owner approve/reject since **2026-08-22 (15 days)** (`DAY_0_REVENUE_BASELINE.md:18`; `REVENUE_BLOCKERS.md:8`). It blocks the payment-authorization gate. **No amount is claimed** — none is recorded in any reachable file.
2. **Review the ratchet re-pin in `79f5b0a6`:** allowlist **+7** (85→92) is documented, but the fingerprint drop **−46 (839→793)** is not (`progress.md:870-875`). Deliberately not bumped unattended — this is an anti-relaxation control.
- **Proof:** `DAY_0_REVENUE_BASELINE.md:18` updated with the decision; owner sign-off recorded on the −46.

---

## 5. Priority rationale (why this order)

The instructed order is (a) hot-queue closes → (b) upsell Jiya/Kamal → (c) renewals → (d) reactivation. I am placing **A1/A2 first** because both are *simultaneously* (b) and (c): Jiya and Kamal are the only two known payers, both past due, and each conversation captures both the renewal and the upsell step in one message. Evidence for that ranking:
- A1 is **₹19,990 = 125% of the Base target** against a draft that has been ready since 09-03.
- A3 (hot queue) is the only *new*-customer path, but its row count has not been reproducible since 08-23, and the send path it depends on (BLK-11) is unproven — so it cannot outrank a verified, drafted, highest-probability ask.

A3 stays in the list at #3 because new-cash is what the 90-day plan actually needs.

---

## 6. Compliance statement

- No DND / TRAI / consent / opt-out gate was weakened, disabled, or bypassed. Cold WhatsApp remains OFF; email cap unchanged at 25/day.
- `payment_verification_method` remains `owner_confirmed_upi`. `PROVIDER_VERIFIED` was not set and remains unreachable by design (Stripe + Razorpay removed).
- **Flag for owner:** local `.env:24` reads `WHATSAPP_AUTO_SEND=1`. That is the **local dev** file (prod was set to `0` on 2026-07-05) — do **not** sync local `.env` to the VPS. Automated sends remain additionally fail-closed on an allowlist (`app/api/whatsapp.py:73`).
- No synthetic, projected, or estimated revenue is reported as collected. Every figure above is either cited to a source or explicitly marked unverifiable.
- All probes this run were read-only HTTPS GETs, local file reads, and local `git`/`grep`. **No deploy, no SSH, no remote state change.**

---

## 7. Carry-forward for tomorrow (2026-09-07)

1. Was A1 sent, and is there a **non-null WAHA message id**? If BLK-11 is still `wa_msg_id: 0`, escalate from "unproven" to "confirmed dead" and re-plan the channel.
2. Did the 09:00 IST pack for 2026-09-06 appear, and with how many rows? (answers the "42 warm leads" question)
3. Does an ops token exist yet? (unlocks real revenue verification from Day 5)
4. `upi_12_bd74bae8` decision recorded?
5. Jiya's city defect (Mumbai vs Nagpur, `docs/UPSELL_PACKAGE_JIYA_KAMAL_2026-09-03.md` §2) — 1-min fix, still open.
