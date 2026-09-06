# ADR — DND/NCPR compliance ceiling (OPS-010) and the durable opt-out ledger

**Date:** 2026-09-07 (cycle 5, 04:40 IST) · **Status:** proposed (owner decision required for §6.1/§6.2)
**Author:** Autonomous Admin / Virtual Council · **Authority:** local code + research only — no deploy, no SSH, no remote state change
**Scope:** `app/utils/dnd_checker.py`, `app/automation/orchestrator_pipeline.py` (§5 gate), automated WhatsApp rail

---

## 1. Decision under consideration

OPS-010: `DNDChecker` has no external NCPR/DND lookup provider (Exotel removed 2026-06-18). Every un-cached number returns `verified=False`, and the §5 TRAI invariant treats **unverified == DND == promotional BLOCK**. Therefore the automated WhatsApp rail will correctly send to ~zero leads even after deploy.

The obvious "fix" — let a consent/opt-in record override the DND block — was evaluated and **REJECTED**. Evidence in §3.

---

## 2. What was inspected (local truth first)

| File / symbol | Finding |
|---|---|
| `app/utils/dnd_checker.py:150-209` `_check_via_registry` | Three paths: `DND_API_URL`+`DND_API_KEY` (generic HTTP), `DND_CARRIER_SCRUB=1`+Vobiz creds, else `source="no_provider", verified=False` |
| `app/utils/dnd_checker.py:187-201` | **`DND_CARRIER_SCRUB=1` is a global fail-open switch** — returns `is_dnd=False, verified=True` for *every* number with no per-number check. Env-off by default, but it must never be armed to "work around" OPS-010 |
| `app/utils/dnd_checker.py:44-45, 225-243` (pre-fix) | Opt-outs lived in a process-local dict with a 7-day expiry; `add_to_local_dnd()` had **zero callers** in `app/`, `scripts/`, `tests/` |
| `.env.example:243` | `DND_API_URL=https://api.dnd-check.in` — a placeholder domain, not a real provider. Implies a capability that does not exist |
| `app/utils/dnd_checker.py:133-148` `filter_dnd` | Correctly fail-closed: only `verified and not is_dnd` passes |

## 3. Research findings (web, 2026-09-06/07)

### 3.1 Consent does **not** override DND for promotional content — the rejected fix

> "There is no consent mechanism that overrides a DND registration for genuinely promotional content; a subscriber who has opted out of a category stays opted out regardless of what the sender's own records say about prior engagement."
> — SMPPCenter, *NCPR and DND Scrubbing for Bulk SMS in India*

> "Can a business override a customer's DND registration with prior consent? **Not for genuinely promotional content.** Service Explicit messages (existing customers with logged opt-in consent) still pass through NCPR scrubbing."
> — ibid.

**Council decision:** a consent-ledger override for promotional WhatsApp would be a compliance regression wearing the costume of a fix. **Not implemented.**

### 3.2 …but voice is different (TCCCPR 2018)

> "Calls to DND-registered numbers are prohibited **unless the customer has given explicit consent**."
> — Scalify Labs, *TRAI-Compliant AI Calling India 2026*

Transactional headers (opted-in) may call DND numbers when prior consent is documented; promotional headers may not. So a consent path is legitimate **for voice**, not for promotional messaging.

### 3.3 The real unblock: customer-triggered (Service Implicit) is exempt

> "Service Implicit messages are triggered directly by a customer's own action or an existing relationship … **exempt from DND scrubbing** and can be sent at any hour to a valid number regardless of NCPR status."
> — SMPPCenter

> "NCPR scrubbing only applies to promotional (commercial) messages."
> — ibid.

**Implication:** replying to a lead who messaged us first (`197126499872961`) is customer-triggered and **not** subject to NCPR scrubbing. The correct rail design is to send **only** into inbound-initiated sessions (WhatsApp 24-hour customer-service window) — not cold promotional blasts.

### 3.4 Who scrubs

NCPR/DND scrubbing is performed **by the sending platform / aggregator at send time**, not by a business-side API query against TRAI. The article provides no business-to-TRAI API endpoint. Subscribers register preferences via 1909 / SMS to 1909 / TRAI DND 2.0 app.

**Implication:** buying "a DND check API" is the wrong shape. The right shape is a BSP/aggregator that scrubs at send time and gives you scrubbing logs.

### 3.5 Exposure

| Item | Value |
|---|---|
| Penalty | up to **₹5 lakh per violation**, number blacklisting, IT Act 72A for repeat violations (Scalify Labs) |
| Misclassification | "misclassifying a promotional message as service-implicit risks the sender's own number being … disconnected on first complaint, with a two-year blacklist" (SMPPCenter) |
| Promotional window | 09:00–21:00 IST (TRAI voice) / commonly 10:00–21:00 (SMS) |
| Opt-out SLA | honoured within 24 hours; scrubbing logs retained |

### 3.6 New risk — OPS-013: WhatsApp general-purpose AI chatbots

Meta changed Business API terms (Oct 2025, reported by TechCrunch) to bar general-purpose chatbots; reported effective **2026-01-15**. Task-scoped bots (support, bookings, orders) remain allowed; "not all chatbots are banned" (respond.io).

**LeadGen sells an AI WhatsApp agent.** If it behaves as a general-purpose assistant rather than a task-scoped bot, the number risks a ban. **Owner decision required** — recorded as OPS-013, not auto-changed.

---

## 4. Decision

| # | Decision | Status |
|---|---|---|
| D1 | **Do not** build a consent override for promotional WhatsApp/voice-marketing | Decided (rejected, §3.1) |
| D2 | Make opt-outs **durable** — JSONL ledger, never expiring, consulted before any cache or provider | **IMPLEMENTED** (§5) |
| D3 | Do **not** arm `DND_CARRIER_SCRUB` as an OPS-010 workaround — it is a global fail-open | Decided |
| D4 | Re-classify automated sends by category; only inbound-initiated `service_implicit` may skip NCPR gating | **Proposed — owner decision (§6.1)** |
| D5 | Select a BSP/aggregator that scrubs at send time and supplies scrubbing logs | **Proposed — owner decision (§6.2)** |
| D6 | Remove the misleading placeholder `DND_API_URL` from `.env.example` | **IMPLEMENTED** (§5.2) |

## 5. What changed (local, not deployed)

### 5.1 Opt-out authority — `app/utils/dnd_checker.py` (**REVISED cycle 6, same day**)

- `check_single()` now consults the CANONICAL opt-out ledger **first** and returns `is_dnd=True, verified=True, source="consent_ledger_optout"` — a recorded STOP can never be overridden by a stale cached "not DND" or by any provider result.
- `add_to_local_dnd()` writes through via `record_opt_out(phone, reason=..., channel="dnd_local")`; a `suppressed=False` result is logged as a compliance incident.
- `remove_from_local_dnd()` clears **only** the in-memory entry and logs a warning: lifting a real opt-out requires `consent_ledger.opt_back_in()` with documented re-consent. It deliberately does **not** lift the durable suppression.
- `export_local_dnd()`/`import_local_dnd()` read/write the canonical store; `is_opted_out()` delegates.
- **Correction (cycle 6):** the first revision of this change created a *second* store, `data/dnd_optouts.jsonl`. That was a **duplicate workflow** — this codebase already has one canonical cross-channel suppression authority (`app/telephony/consent_ledger.py`, DB-backed when `CONSENT_DB=1`, JSONL fallback, fail-closed, already consulted by `app/integrations/whatsapp.py::send_permitted()`). The duplicate was **removed** and replaced with delegation. `tests/test_dnd_optout_ledger.py::test_no_duplicate_optout_store_is_created` guards against it returning.
- Fail-closed preserved: if the authority is unreachable, `_is_suppressed()` logs and returns **True**; "I cannot reach the opt-out list" is never answered as "they did not opt out".

### 5.1b Inbound STOP was not reaching the canonical ledger — `app/api/whatsapp.py`

`app/api/webhooks.py:161` records `record_opt_out(...)` on STOP; `app/api/whatsapp.py` (2 inbound handlers, ~L372 and ~L531) called only `runner.suppress(...)`, so **a WhatsApp STOP never reached the cross-channel ledger** and stayed invisible to voice. Both sites now record it too (guarded, never raises).

### 5.2 `.env.example`
`DND_API_URL=https://api.dnd-check.in` replaced with a commented, explicitly-labelled placeholder so nobody believes a provider is wired.

### 5.3 Tests — `tests/test_dnd_optout_ledger.py` (11)
Write-through · idempotency across three spellings of one number · survives a fresh instance (restart) · blocks as **verified** DND · **opt-out beats a poisoned non-DND cache entry** · excluded by `filter_dnd` · removal unblocks · missing file ⇒ empty and still fail-closed · export/import round-trip · normalisation variants · unrelated number not blocked.

## 6. Open, owner-gated items

### 6.1 D4 — message-category re-classification (touches the §5 gate)
Proposed: automated sends carry `category ∈ {promotional, service_implicit}`. `service_implicit` requires **proof** of an inbound-initiated session (inbound message timestamp within the WhatsApp 24h window). Promotional stays exactly as today — fail-closed. This is a *narrowing with proof*, not a bypass, but it edits a compliance gate, so it is **not** being done unattended.

### 6.2 D5 — BSP with NCPR scrubbing
Needed from the provider, in writing: (a) scrubbing performed at send time, (b) list freshness/refresh cadence, (c) scrubbing logs retained, (d) promotional window enforcement.

---

## 7. Verification evidence

- `pytest tests/test_dnd_optout_ledger.py` → **11 passed**
- Regression: `test_suppression_compliance_gates` + `test_voice_compliance_slice_2026_07_05` + `test_whatsapp_automation_body` + `test_ops_readonly_token` → **61 passed**
- `ruff check` → All checks passed · `check_secrets.py` → OK (50 files)
- `prod_check.py` → see §8
- **Pre-existing failure, proven unrelated:** `tests/test_compliance.py::test_dnd_fail_open_honoured_outside_production` fails identically on the unmodified `HEAD` version of `dnd_checker.py` (verified by temporarily restoring `git show HEAD:app/utils/dnd_checker.py`, re-running, then restoring the new file). Cause: the gate still detects production even though the test deletes `ENVIRONMENT`/`APP_ENV`. Not introduced by this cycle; recorded, not fixed.

## 8. Honest limits

- Everything is **local-only and undeployed**; prod behaviour is unchanged.
- The ledger uses a JSONL file. At scale this should become a Postgres table with a unique index on the normalised key — noted for the owner, not done unattended (schema migration).
- §3.x sources are vendor/commercial guides, not TRAI primary text. They agree with each other and with TCCCPR 2018 as understood, but **legal confirmation is the owner's call** before D4 ships.
