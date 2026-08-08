# CP2-2 — Cursor handoff: wire the offer producer

Re-verified on fresh `origin/main` `5ae5a4b9` (2026-08-08):

```
$ grep -rn "issue_offer" --include=*.py --include=*.html . \
    | grep -v "^./tests/" | grep -v "^./app/marketing/offers.py" | grep -v "^./docs/"
(no output)
```

`app/marketing/offers.py` is a complete, documented, tested subsystem — immutable
`LG-<uuid4hex>` references, supersede chain, expiry, price freeze against
retro-quoting — and the consumer side is hardened (`/api/upi/submit` accepts an
`order_ref` but re-resolves it server-side and refuses unknown / expired /
superseded / already-paid / plan-mismatched references). **It has zero production
callers.** So the offer store is empty in production, `order_ref` is never
recorded, and issue #240's Definition of Done is unmet: reconciling a UPI credit
is still a business-name match.

This is **not** a new task ledger. It is the payload for the **existing** Owner OS
external-agent mission mechanism (`app/dev_control/external_agents`, the same one
WS-PRF1 dispatches onto). No second control plane, no competing branch, no new
coordination database.

## Why Claude did not implement it

The producer belongs at the interested-reply offer seam in
`app/platform/reply_agent.py`, with the queue surface in
`frontend/admin_dashboard.html`. Both are held by Cursor — `admin_dashboard.html`
and `tests/test_reply_offer_payment_block.py` are uncommitted-modified in the
primary checkout. Under the one-writer rule those are Cursor's to change.

⚠️ **Precondition (Owner packet item 1).** That primary checkout is on the
**dead pre-rewrite lineage** (base 2026-06-17, ~1801 phantom commits, 35
uncommitted files). This mission specifies a **fresh worktree off `origin/main`**.
Do not start it from the existing dirty checkout — a PR from there would carry the
phantom history.

## Register the mission (canonical path)

`POST /api/dev-tasks/missions` → `external_agents.orchestrator.create_mission`.
The payload below was validated locally against the canonical schema
(`Mission(**payload).validate()` → `SCHEMA-VALID`, state `CREATED`, risk `AMBER`).
`AMBER` is deliberate: it cannot self-advance and requires the Owner's approval,
which is the gate this work should sit behind.

```json
{
  "mission_id": "cp2-2-offer-producer-20260808",
  "title": "CP2-2: wire the offer producer so order_ref exists in production",
  "executor": "cursor",
  "reviewer": "claude-cloud",
  "declared_risk": "AMBER",
  "idempotency_key": "cp2-2-offer-producer-2026-08-08",
  "parent_goal_id": "issue-240",
  "priority": 20,
  "branch": "cursor/cp2-2-offer-producer",
  "worktree": "fresh isolated worktree off origin/main — NOT the dirty primary checkout",
  "base_sha": "5ae5a4b9d7c1ed72dd0dff6dfd3470a2c1b41e81",
  "allowed_paths": [
    "app/platform/reply_agent.py",
    "frontend/admin_dashboard.html",
    "app/api/upi_payments.py",
    "tests/test_reply_offer_payment_block.py",
    "tests/test_offer_producer_wiring.py"
  ],
  "prohibited_paths": [
    "app/marketing/offers.py",
    "app/platform/upi_payments.py",
    "app/marketing/packages.py",
    "app/marketing/voice_packages.py",
    "app/telephony/",
    ".env",
    ".github/workflows/security-scan.yml",
    "requirements.lock.txt"
  ],
  "rollback_plan": "git revert the single producer commit; the offers store simply stops gaining rows. No schema, no migration, no flag."
}
```

Repository: `github.com/sumitrevolt/leadgenrationaivoiceagent`, base `5ae5a4b9`.

## Scope — entry points

1. **Mint the offer.** `run_reply_triage` (~`reply_agent.py:1320`) already holds the
   prospect record `p` and can resolve the deal by email. Resolve deal → call
   `offers.issue_offer(deal_id, package_code)` → thread the returned `order_ref`
   into the offer block.
2. **Carry it.** UPI `tn=` must carry `order_ref` **plus** the business name (the
   name is for human legibility; the reference is what reconciles).
3. **Surface it.** `/upi/pending` must render `order_ref`, `deal_id`,
   `expected_amount` and `amount_mismatch` — `submit_payment` already persists all
   four (`app/platform/upi_payments.py:462-477`). Approving a credit becomes a
   match, not a guess.

## Hard requirements

- **Pricing/consent authority is `offers.py`, and it is off-limits.** The offer
  freezes `package_code` / `quoted_amount` / `currency` at issuance; a later
  `packages.py` change must never retro-quote. Do not read live pricing at payment
  time.
- **`am=` only when a package is bound.** #236 deliberately ships no amount
  prefill; quoting Starter blind underprices a Combo (₹5,999) or Voice (₹4,999+)
  prospect. Emit `am=` only from an issued offer's `quoted_amount`.
- **Idempotency.** Same deal + same package must reuse one `order_ref`, never mint
  a second. A revision creates a NEW order carrying `supersedes_order_ref` and
  leaves the original intact and auditable.
- **Tenant isolation.** An offer must never be visible or resolvable across
  clients.
- **Consent / suppression / DND gates unchanged.** An opt-out must still suppress
  cross-channel instantly. Do not add a send path.
- **Compatibility with PR #285.** That PR makes an approved or auto-activated
  payment call `offers.mark_status(order_ref, STATUS_PAID)`. Before it, an order
  stayed payable forever and a second `upi_ref` under the same `order_ref` slipped
  past the `(upi_ref, client_id, plan)` duplicate guard → a second `_try_activate`
  → metered usage re-zeroed → duplicate Rule-46 GST invoice. **PR #285 must land
  first, or this mission opens that hole the moment issuance starts working.**
  Assume `resolve_payable` refuses `already_paid`; do not re-implement closure.

## Acceptance criteria

1. `offers.issue_offer()` has at least one production caller.
2. An issued `order_ref` reaches the UPI `tn=` field.
3. `/upi/pending` surfaces `order_ref`, `deal_id`, `expected_amount`,
   `amount_mismatch`.
4. `am=` is emitted **only** when a package is bound.
5. Same deal + same package reuses one `order_ref` — proven by a test that issues
   twice and asserts one reference.
6. An offer is never resolvable across tenants.
7. Consent/suppression behaviour is unchanged.

## Required tests

New `tests/test_offer_producer_wiring.py` proving an offer is issued **exactly
once** per deal+package, plus green:
`test_offers_order_ref.py` · `test_offers_commercial_authority.py` ·
`test_upi_order_ref_binding.py` · `test_reply_offer_payment_block.py`

Required checks: `scripts/prod_check.py` · `scripts/check_secrets.py` · CI `tests`
· CI `security-scan`.

## Prohibited

No merge. No deploy. No protected-flag activation (`WHATSAPP_AUTO_SEND`,
`PLATFORM_DIAL_DAILY`, `REPLY_AUTO_SEND`, `UPI_AUTO_ACTIVATE`,
`SELF_IMPROVE_LOOP`). No `.env` change. No real customer contact, message, call or
payment. No edit to any `prohibited_paths` entry. No second orchestrator,
scheduler, registry, task database or coordination store.

## Required finish state

`READY FOR OWNER REVIEW` — Draft PR with exact head SHA, the diff, test evidence,
and any residual risk stated plainly.
