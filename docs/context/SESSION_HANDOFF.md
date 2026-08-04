# SESSION_HANDOFF — 2026-08-04 (revenue P0 #240: offer/order attribution spine)

## Where things stand

- **Prod `/health` = `33651cfc`** (PR #236 deploy). 5/5 app-image services equal + healthy, `VOICE_LAUNCH_KILL=0`, celery/DLQ = 0.
- **`origin/main` = `8309b60`** — ahead of prod by docs + `requirements.lock.txt` + tests only. **No deploy owed**; the lock fix takes effect on the next image build.
- **AI-generated revenue = ₹0.** Jiya ₹1,999 is manually onboarded and stays excluded.

## Shipped this session

| PR | What | State |
|---|---|---|
| #236 | interested-reply offer footer: canonical `upi_config` resolver + NPCI deep-link, **no amount prefill** | MERGED + DEPLOYED `33651cfc` |
| #238 | post-deploy prod truth + `UPI_AUTO_ACTIVATE` drift record | MERGED `b1b67f3` |
| #239 | `pydantic_core` 2.47.0 → 2.46.4 in the lock (closes #237) | MERGED `8309b60` |
| #241 | **immutable offer/order entity + fail-closed payment binding** | OPEN — CI running |

Issue **#237 CLOSED with proof**: `tests` workflow = `success` on main at `8309b608`, ending a failure streak unbroken since `d451b56c`.

## #240 — what #241 does and does NOT do

**Does:** `app/marketing/offers.py` — append-only immutable offers. `LG-<uuid4 hex 32>` reference (full entropy, not truncated — deal id is *already* `uuid4().hex[:12]`). `package_code`/`quoted_amount`/`currency` frozen at issuance so a catalogue price change cannot retro-quote. Revision creates a new order with `supersedes_order_ref`. Pricing fails closed on unknown packages. `submit_payment(order_ref=...)` re-resolves server-side and rejects unknown/expired/superseded/paid/plan-mismatched; persists `deal_id`, `package_code`, `expected_amount`, `amount_mismatch`.

**Cardinality decided from code:** `upsert_deal` dedupes by phone/email and returns the existing row → deal is long-lived → deal 1..N offer (Main→Combo upgrade, Voice bands, repeat top-ups). Hence a separate entity, **not** fields on the deal.

**Does NOT:** the reply footer still issues no order. Nothing in the reply path knows *which package* was pitched — there is no campaign→package mapping — and guessing would reintroduce the Starter-blind bug #236 exists to prevent.

## Next actions, in order

1. **Merge #241** once required checks are green (expected-head protection). No deploy strictly required — but deploying makes `offers.py` live for the admin queue work below.
2. **Campaign→package mapping** — the blocker for auto-issuing an order on an interested reply. Until it exists, do not bind a package in `_draft`.
3. **`/upi/pending` admin UI** — surface `order_ref`, `deal_id`, `package_code`, `expected_amount` vs submitted, and `amount_mismatch`. API already returns them; the UI does not render them yet (`frontend/admin_dashboard.html:4845`).
4. **Provisioning binding** — key invoice/tenant/onboarding off `order_ref`; `offers.mark_status(ref, "paid")` on approval. Never observed end to end (`LIVE_NOT_PROVEN`).
5. **Outreach ramp** — only AFTER attribution + provisioning. Volume before attribution produces more unattributable credits, not revenue.

## Do NOT

- Do not broaden `UPI_AUTO_ACTIVATE_CLIENTS` (prod `UPI_AUTO_ACTIVATE=1`, allowlist = exactly one client id, fail-closed verified — docs previously said `=0`, that was drift).
- Do not add `am=` to the offer footer without a bound order — catalogue is multi-price.
- Do not call owner bank confirmation "provider-verified".
- Do not `reset --hard` the VPS checkout; `scripts/deploy_vps.sh` uses its own candidate worktree.

## Gotcha found this session

`app/marketing/offers.py::_write_all` must **not** use `locked_rewrite` — mutating callers already hold `file_lock` on the same path, and re-entering the sidecar lock hangs until timeout. Outer lock guards read-modify-write; the write is lock-free atomic tmp+fsync+`os.replace`.
