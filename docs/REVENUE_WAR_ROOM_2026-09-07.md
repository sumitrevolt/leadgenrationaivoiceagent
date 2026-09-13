# Daily Revenue War Room — 2026-09-07 (08:30 IST) — Sprint Day 5 of 8

**Authority:** plan + local fixes only. No deploy, no SSH, no remote state change, no compliance gate touched.
**Ladder in force:** Floor ₹9,995 / Base ₹16,000 / Stretch ₹25,000 (net-new **collected**) — `docs/REVENUE_TARGET_REBASELINE_2026-09-03.md` §3. ₹5,00,000 = 90-day milestone, not measured here.
**Payment rule:** manual UPI only; `payment_verification_method = owner_confirmed_upi`. `PROVIDER_VERIFIED` remains unreachable by design (Stripe + Razorpay removed).

---

## 1. Production truth — pull result

| Check | Result | Source |
|---|---|---|
| `GET https://leadsgenai.in/health` | **healthy**, `environment: production`, version **`bdf82eec`**, uptime **2h 43m 20s** (restart ≈ 05:47 IST), `dsh_allowlist: ["jiya_makeover"]` | live probe 2026-09-07 08:31 IST |
| Prod vs repo | prod `bdf82eec` **IS an ancestor** of local HEAD `82e3ea17`; local ahead by **2 commits**, both docs-only (`79291e2b` merge PR #477, `82e3ea17` council ledger docs) ⇒ **no code drift** | `git merge-base --is-ancestor` + `git log --oneline bdf82eec..HEAD` |
| Prod deploy time | `bdf82eec` committed **2026-09-07 05:39 IST** — a deploy ran overnight before this war room | `git log -1 --format="%h %ad %s" bdf82eec` |
| `GET /api/ops/revenue-summary` | **HTTP 401** (no auth) | live probe 08:31 IST |
| Same, with local `FASTAPI_MCP_TOKEN` | **HTTP 401** | live probe 08:31 IST |
| `GET /api/ops/hotqueue` | **HTTP 401** (same gate) | `app/api/ops_mcp_tools.py:105` |
| `GET /api/billing/invoices` | **HTTP 401** (prior runs) | `progress.md` |

### 🔴 Verdict: production revenue truth is UNREACHABLE for the 4th consecutive war room.

**BUT — the root cause changed today, and it is now one env var away from being fixed.**

The 09-06 diagnosis ("`require_admin` accepts JWT only, no API-key branch") is **no longer true in production**. The OPS-008 read-only ops key shipped:

- `git show bdf82eec:app/api/auth_deps.py | grep -c "OPS-008"` → **1** — the allowlist + `_ops_readonly_allows()` are live.
- `git show bdf82eec:app/config.py | grep ops_readonly_token` → **`ops_readonly_token: str = ""`** — the setting exists.
- `git show bdf82eec:app/api/ops_mcp_tools.py | grep require_admin_or_ops_readonly` → **lines 41 and 105** — both GET endpoints (`revenue-summary`, `hotqueue`) are wired to it.

So the code is complete and deployed. The 401 persists for exactly one reason:

- `_ops_readonly_allows()` returns `False` immediately when `settings.ops_readonly_token` is empty (`app/api/auth_deps.py:149-151`) — **fail-closed by design**.
- Local `.env` contains **no** `OPS_READONLY_TOKEN` (`grep -ci OPS_READONLY .env` → **0**).
- The VPS `.env` value is unknown to us and cannot be read (SSH is owner-gated).

**I cannot distinguish "token unset on VPS" from "token set to a value I don't have."** Both produce 401. Only the owner can resolve this — see **A3**.

**Re-probe at 08:42 IST:** still **401**; prod unchanged at `bdf82eec`, uptime 2h 54m — stable, no drift during this run.

### Collected revenue — honest statement

| Metric | Value | Basis |
|---|---|---|
| **Collected today (2026-09-07)** | **₹0 confirmed** — ledger unreachable. This is *"no confirmed collection"*, **NOT "confirmed zero"** | No invoice/UTR artifact in repo; ops endpoints 401 |
| **Net-new collected, sprint Day 1–4** | **₹0 evidence-backed** | Day 1–3 = ₹0 (`docs/REVENUE_WAR_ROOM_2026-09-06.md` §1); Day 4 (09-06) produced two send-ready drafts but **no collection evidence** |
| **Gap to Floor ₹9,995** | **₹9,995** (100%) · required pace **₹2,499/day × 4** | ladder §3 ÷ 4 remaining days |
| **Gap to Base ₹16,000** | **₹16,000** (100%) · required pace **₹4,000/day × 4** | same |
| **Gap to Stretch ₹25,000** | **₹25,000** (100%) · required pace **₹6,250/day × 4** | same |
| Days remaining | **4** (Sep 7–10 inclusive; window Sep 3–10) | ladder §3 |

### Local data is entirely test artifacts — do NOT read it as pipeline

Every local "revenue-shaped" file inspected this run is synthetic:

| File | Content | Verdict |
|---|---|---|
| `data/revenue_attribution.jsonl` | 12 rows, all `business: "Example Business"`, `email: "owner@biz.in"`, **`amount_inr: 0`** | test fixture |
| `data/deals.jsonl` | 2 rows — `"Lead"` / `9876543210` and `"Example Business"` / `owner@biz.in` | test fixture |
| `data/cadence_leads.jsonl` | 1 row — `"Example Business"` | test fixture |
| `data/wa_conversations.jsonl` | inbound only, all from `9876543210`, all **`"mid": ""`** | test fixture |
| `data/invoices.jsonl`, `data/upi_payments.json`, `data/payments.jsonl` | **absent** | no local ledger |

**Baseline dispute — carried, still unresolved (do NOT silently pick one):**
- `DAY_0_REVENUE_BASELINE.md` — lifetime **₹7,997**, MRR ₹3,998, 2 customers; its own line items sum to **₹5,997** (unexplained ₹2,000 gap).
- Bot fleet + `memory/decisions.md:1150` — **₹1,999** verified cash (Jiya `INV/2026-27/0001`).
- **Planning rule:** treat ₹1,999–₹3,998 as verified cash; ₹5,997 / ₹7,997 as unverified. Does not move the ladder (it measures *net-new*).

---

## 2. Highest-ranked UNRESOLVED blocker

### The matrix's #1 is no longer cash-blocking — status correction

**BLK-11 — WhatsApp delivery path.** Rank **#1**, score **900** (`REVENUE_BLOCKERS.md:55`).

New evidence settles the 09-04 vs 08-23 conflict, and it splits the blocker in two:

| Path | Status | Evidence |
|---|---|---|
| **Manual send** | ✅ **WORKING** | Real WAHA message id **`3EB00CFC09FB70376AA279`** to `197126499872961` on 2026-09-05 07:01 IST, plus follow-up **`3EB0767664B1732E444721`** at 08:14 IST — `data/outreach_drafts/INBOUND_197126499872961_FOLLOWUP_2026-09-07.txt` |
| **Automated sweep** | ⚠️ **STILL UNPROVEN** | `esc_0904_1252.jsonl` ts 12:22 IST → `"wa_msg_id": 0`, `"wa_auto_sent_none": 1829` (09-04 evidence, unrebutted since) |

**Operating conclusion:** every action below uses the **manual** path, which is proven. BLK-11 therefore no longer blocks today's cash — it blocks *automation at scale only*. It should be re-ranked below the automation backlog, **not** deleted: the moment volume matters, it is #1 again.

### 🔴 The actual #1 today: OPS-011 — read-only ops token not armed

This blocker postdates `REVENUE_BLOCKERS.md` (created 09-06) and must be inserted at the top. It is the only reason this is the **4th consecutive blind war room**.

- Council ledger `scripts/council_ledger_sync.py:390-405` → **`OPS-011`, status `BLOCKED`, priority `P1`, deadline `2026-09-07T21:00:00+05:30`**.
- Acceptance: *"HTTP 200 with stats from `/api/ops/revenue-summary` using the key; POST `/api/ops/hotqueue/action` still 401/403 for the same key."*
- Cost of leaving it: **every remaining sprint day is planned and closed against ₹0 instead of truth.** With 4 days left, that is 4 more blind closes.

**Second: BLK-01 residual — `upi_12_bd74bae8`.** Open since **2026-08-22 (16 days)**. One ambiguous UPI row ("REAL-CHECK") pending owner approve/reject — a payment-authorization gate (`REVENUE_BLOCKERS.md:8`). Small cash, but it is the last open item on an otherwise-closed blocker and it poisons ledger integrity while open.

---

## 3. Resolved since last run — verify, then stop re-litigating

| Item | Status | Evidence |
|---|---|---|
| Existing-customer suppression in hot-queue pack | ✅ **DEPLOYED** | `git merge-base --is-ancestor 8546c170 bdf82eec` → **YES**. Prod no longer serves Jiya/Kamal as fresh leads. (09-04 flagged it as local-only/undeployed — that is now stale.) |
| OPS-008 read-only token *code* | ✅ **DEPLOYED** | `git show bdf82eec:app/api/ops_mcp_tools.py` → `require_admin_or_ops_readonly` at lines 41, 105 |
| Prod version drift | ✅ **NONE** (code) | prod `bdf82eec` is ancestor of local HEAD; the 2 commits ahead are docs-only |

---

## 3.1 Price verification — every ₹-figure below re-verified against source this run

The 09-06 war room inherited several price claims from 09-04 without re-checking them. I re-verified all of them from source before issuing A1–A5. **All figures used below are confirmed correct.**

### Product-1 — AI Automated Marketing (`app/marketing/packages.py`)

| Tier | Monthly | Annual | `marketing_only` | `public` | Sellable? |
|---|---:|---:|---|---|---|
| `starter` | **₹1,999** | **₹19,990** | `True` | *(unset)* | ✅ **yes** — this is what Jiya is on |
| `growth` | ₹2,999 | ₹29,990 | `True` | **`False`** | ❌ **NO** |
| `advanced` | **₹5,999** | **₹59,990** | `False` | *(unset)* | ✅ **yes** |

Sources: `packages.py:192-196` (starter), `:206-212` (growth), `:239-246` (advanced). Line 12: *"flat-monthly per niche-band A/B/C (ADR-009) … **Yahan NAHI**"* — this file is **not** niche-gated. Grep for `available_for|allowed_niche|niche_gate|restricted|eligible` in `packages.py` → **0 hits**.

### ⚠️ Correction — do NOT sell the ₹2,999 "Growth" tier

`packages.py:207-212` marks `growth` as **`public: False`** with the tagline *"Legacy/internal only — hidden from public pricing, backward compatibility ke liye."*

I nearly recommended ₹2,999 as a soft landing step for Kamal between Starter and Advanced. **That would have been wrong** — it is not a public tier. The only sellable step up from Starter ₹1,999 is **Advanced ₹5,999/mo** (or Starter annual ₹19,990). This is now pinned here so no future run repeats the mistake.

### Product-2 — AI Voice Calling Agent (`app/marketing/voice_packages.py:38-84`)

| Band | Monthly | Annual | Sample niches |
|---|---:|---:|---|
| **S** Starter Voice (100 min) | ₹1,999 | ₹19,990 | any niche, 100-min cap |
| **F** Freemium (10 calls/mo) | ₹0 | ₹0 | any niche |
| **A** Volume | **₹4,999** | ₹49,990 | Insurance · Coaching · Solar · Hospital Appts · Upskilling · Travel |
| **B** Mid-premium | **₹9,999** | ₹99,990 | Home Loans · Study Abroad · Dental · Modular Kitchen · Finance Advisory · CA |
| **C** Premium | **₹19,999** | ₹1,99,990 | IVF · Immigration · Commercial Solar · HVAC · Hair Transplant |

**Verified:** all five bands match the A2 draft. One harmless copy drift: the draft's band-B list says "CA **& Legal**" while the code says "**Modular Kitchen**, … CA". No price is affected — but when you name the niche list to the lead, use the **code's** wording.

### Top-up minute packs (`packages.py:353-355`)

100 min **₹1,499** · 250 min **₹3,499** · 500 min **₹5,999**. Useful as a low-friction add-on if a lead stalls on the main ask.

---

## 4. Today's action list (5)

### A1 — Send the Jiya ₹19,990 annual prepay ask. First thing. *(≈10 min · up to ₹19,990 = 200% of Floor)*

**Why first:** highest-probability, highest-value, and the draft is already on disk and verified. Priority (b) in the ladder ordering.

- **Draft:** `data/outreach_drafts/JIYA_SEND_READY_2026-09-07.txt` (exists, 4,564 B, prepared 09-06 20:30 IST — **this file is real and present**, unlike the phantom file flagged on 09-04).
- **Ask:** Annual prepay **₹19,990** (vs ₹23,988/yr = 2 months free). Fallback: monthly renewal ₹1,999.
- **Gate first:** `curl -s http://127.0.0.1:3111/api/sessions/default | head -c 300` → require `"status":"WORKING"`. If `SCAN_QR_CODE`, scan before sending.
- **Product note (corrected):** do **not** pitch the niche-banded **Combo ₹4,999** to `beauty_makeover`. ₹5,999 **is** sellable — it is **Advanced Marketing** (`app/marketing/packages.py:238-247`, not niche-gated). Keep annual ₹19,990 as the lead ask.

**Proof of completion:**
```
# non-null message id from the manual send
curl -s -X POST http://127.0.0.1:3111/api/sendText \
  -H 'Content-Type: application/json' \
  -d '{"chatId":"919876543210@c.us","text":"<draft verbatim>","session":"default"}' \
  | python -c "import sys,json; print(json.load(sys.stdin).get('id'))"
# must print a non-empty id like 3EB0...; "0"/null = NOT sent, escalate
```

### A2 — Third touch on the only genuine inbound buyer, then apply the stop rule. *(≈5 min · ₹4,999–₹19,990)*

**Why:** `197126499872961` is the **only** inbound buyer in the pipeline — inbound on 09-04 18:21 IST ("AI Voice Calling Agent ke baare me baat karni hai"), proposal + UPI sent 09-05, **no reply since**. Two acceptance gates (09:30, 11:30 IST on 09-05) already missed; 09-06 logged 0 messages. Priority (a)/(d).

- **Draft:** `data/outreach_drafts/INBOUND_197126499872961_FOLLOWUP_2026-09-07.txt` — asks one qualifying question (which niche → which band).
- **Bands are real, not invented:** `app/marketing/voice_packages.py:38-84` — A ₹4,999 · B ₹9,999 · C ₹19,999 · Starter Voice ₹1,999 (100 min) · Freemium ₹0 (10 calls/mo).
- **Compliance:** this lead messaged us first → replying to an inbound enquiry is **not** cold outreach, no DLT template required. **Do not add this number to any cold campaign.** Cold outbound stays DLT-gated and OFF.
- **Stop rule (honour it):** if no reply to this third touch, mark **NOT-INTERESTED** with msg-ids `3EB00CFC09FB70376AA279` / `3EB0767664B1732E444721` as evidence and stop. Re-engage only via the 30-day reactivation path.

**Proof of completion:**
```
# 1) reply check BEFORE sending
grep "197126499872961" /var/lib/leadgen/runtime/wa_inbound.jsonl | tail -5
# 2) then send, and capture the id
curl -s -X POST http://127.0.0.1:3111/api/sendText \
  -H 'Content-Type: application/json' \
  -d '{"chatId":"197126499872961@c.us","text":"<draft verbatim>","session":"default"}' \
  | python -c "import sys,json; print(json.load(sys.stdin).get('id'))"
# 3) record EITHER a captured reply OR an explicit NOT-INTERESTED row
```

### A3 — Arm `OPS_READONLY_TOKEN` on the VPS. Owner, ~2 min. Unblocks every remaining sprint day. *(no direct cash · removes the blindness)*

**Why:** P1, deadline **today 21:00 IST** (`scripts/council_ledger_sync.py:390-405`). Until this is done, Day 6/7/8 closes are blind too.

```
# generate
python -c "import secrets; print(secrets.token_urlsafe(32))"
# add to /opt/leadgen/.env  ->  OPS_READONLY_TOKEN=<value>
# restart is required for the setting to load, then:
```
**Proof of completion:**
```
curl -s -o /dev/null -w "revenue=%{http_code}\n" \
  -H "Authorization: Bearer $OPS_READONLY_TOKEN" \
  https://leadsgenai.in/api/ops/revenue-summary      # MUST be 200
curl -s -o /dev/null -w "hotqueue=%{http_code}\n" \
  -H "Authorization: Bearer $OPS_READONLY_TOKEN" \
  https://leadsgenai.in/api/ops/hotqueue             # MUST be 200
curl -s -o /dev/null -w "mutation=%{http_code}\n" -X POST \
  -H "Authorization: Bearer $OPS_READONLY_TOKEN" \
  https://leadsgenai.in/api/ops/hotqueue/action      # MUST be 401 or 403
```
The third check is the security invariant — if it returns 200/201, **revoke the token immediately** and report.

### A4 — Kamal: Advanced ₹5,999/mo upsell (+₹4,000 MRR), or at minimum lock the ₹1,999 renewal. *(≈10 min · ₹1,999–₹5,999)*

**Why:** priority (b) + (c). Kamal is one of only 2 paying customers; churn protection outranks new-logo hunting at this ARPU.

- **Source:** `docs/UPSELL_PACKAGE_JIYA_KAMAL_2026-09-03.md` (same package as Jiya, Kamal section).
- **Ask ladder (verified §3.1):** the **only** sellable step up from Starter is **Advanced ₹5,999/mo** (₹59,990/yr). Fallback: monthly renewal ₹1,999.
- **Do NOT offer ₹2,999 "Growth"** — `public: False`, legacy/internal only (`packages.py:207-212`).
- **Do not** pitch the niche-banded Combo ₹4,999 unless Kamal's niche falls in a band — verify against `app/marketing/combo_packages.py` first.
- **Add-on option if he stalls:** a minute top-up — 100 min ₹1,499 / 250 min ₹3,499 / 500 min ₹5,999 (`packages.py:353-355`). Far easier "yes" than a 3× tier jump, and it still moves today's collected number.

**Proof of completion:**
```
curl -s -X POST http://127.0.0.1:3111/api/sendText \
  -H 'Content-Type: application/json' \
  -d '{"chatId":"<KAMAL>@c.us","text":"<draft>","session":"default"}' \
  | python -c "import sys,json; print(json.load(sys.stdin).get('id'))"
# + a dated note in progress.md with the UPI amount and owner_confirmed_upi decision
```
**Caveat I cannot resolve:** I have no renewal date for Kamal — the invoice ledger is behind the same 401. Pull the date from `/api/ops/revenue-summary` **after A3** and sequence the ask before expiry.

### A5 — Close out `upi_12_bd74bae8` and read today's 09:00 IST hot-queue pack. *(≈10 min · ledger integrity + pipeline)*

Two unrelated items, both needed before tomorrow's close:

1. **`upi_12_bd74bae8`** — the last open item on BLK-01, pending since **2026-08-22**. Owner decision only: **approve or reject**. Rejecting is a valid outcome; leaving it open is not — it is a payment-authorization gate and it poisons the ledger.
2. **Hot-queue pack** — fires 09:00 IST. **As of 08:42 IST it has not fired yet** (`date` probe), so run this after 09:00. Confirm it appeared and count rows. The existing-customer suppression is now **deployed** (§3), so Jiya/Kamal must **not** appear as fresh leads — if they do, that is a regression, report it.

**Proof of completion:**
```
# 1) written approve/reject decision, dated 2026-09-07, with the row id
# 2) pack row count (exclude header)
ls -la /var/lib/leadgen/runtime/hotqueue/ | grep 2026-09-07
wc -l < <pack-file>
grep -ciE "jiya|kamal" <pack-file>     # MUST be 0 — suppression regression check
```
**Compliance floor, unchanged:** email cap **25/day** stays; cold WhatsApp stays **OFF**; DND/TRAI + consent + opt-out handling untouched.

---

## 5. What I did NOT do

- Did not deploy, SSH, or touch remote state. Prod `bdf82eec` arrived via an owner-gated deploy that ran at 05:39 IST before this run.
- Did not weaken any compliance gate. A3's key is GET-only on 2 allowlisted paths and is fail-closed when unset.
- Did not report any revenue number without production evidence. Every ₹-figure above is either a **price from code** or a **ladder target from docs**, never a projection.
- Did not resolve the ₹7,997 vs ₹5,997 vs ₹1,999 baseline dispute — it needs the ledger, which needs A3.

---

## 6. Carry-forward for the next run

1. Was A1 sent? Non-null WAHA id?
2. Any reply from `197126499872961`? If none after touch 3 → NOT-INTERESTED recorded?
3. **Does `/api/ops/revenue-summary` now return 200?** (A3 — the single highest-leverage item)
4. `upi_12_bd74bae8` decision recorded?
5. Kamal's renewal date (only obtainable after A3).
6. Did the 09-07 hot-queue pack show 0 existing-customer rows?
