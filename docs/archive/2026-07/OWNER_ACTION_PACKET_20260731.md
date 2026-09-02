# Owner Action Packet — 2026-07-31

Consolidated. Every item below is an **owner-boundary** action: it needs a human login/OTP, a
human send decision, or a human approval. An agent cannot cross any of them, which is why the
release verdict is `WAIT` and not `GO`.

**Evidence labels:** `DIRECT_HOST_VERIFIED` = probed from the live host at the stated time ·
`GIT_VERIFIED` = re-derivable from this repo · `ASSUMED` = carried forward, not re-checked.

## Preconditions already proven (do not re-do)

| Fact | Evidence |
|---|---|
| Revenue funnel all 200 — `/`, `/pricing`, `/start`, `/audit`, `/demo`, `/site-audit`, `/privacy` | DIRECT_HOST_VERIFIED 2026-07-31T05:5xZ, curl, non-browser |
| Owner-canary RBAC intact — `GET /preflight`, `GET /last`, `POST /send` all **401** unauthenticated | DIRECT_HOST_VERIFIED (POST probe carried `confirm:false`; rejected at auth, **no send occurred**) |
| Protected actions bounded — `PLATFORM_DIAL_DAILY=10` (owner re-enabled 2026-07-31, TEST-MODE allowlist + bot/IVR detection, cap 10/day, no live call fired), `WHATSAPP_AUTO_SEND=0`, `UPI_AUTO_ACTIVATE=0`, `AUTO_EMAIL_OUTREACH=1` (email outreach LIVE, brevo sends verified) | DIRECT_HOST_VERIFIED 2026-08-01, `docker exec printenv` |
| Queues clean — `celery=0`, `dlq:failed_tasks=0`, `dlq:dead=0` | DIRECT_HOST_VERIFIED 05:41Z |

> **SUPERSEDED 2026-08-02 (historical snapshot):** `PLATFORM_DIAL_DAILY` is the boolean
> ON/OFF switch (=`1` prod), NOT a count; per-run cap = `PLATFORM_DIAL_LIMIT=100` after
> platform_dial went FULL CAMPAIGN LIVE. See `docs/context/CURRENT_STATE.md`.

---

## A1 — Owner inbox email canary (one shot)

**Why it's owner-only:** it sends a real email. Double confirmation is enforced server-side.

1. Sign in as super-admin: `https://leadsgenai.in/app/admin-login` → OTP.
2. Preflight (read-only, sends nothing): `GET https://leadsgenai.in/api/admin/owner-email-canary/preflight`
3. Send exactly once: `POST https://leadsgenai.in/api/admin/owner-email-canary/send`

**Owner input required.** The route (`app/api/owner_email_canary.py:22-47`) refuses unless the body carries **all three**:
```json
{ "idempotency_key": "<>=8 chars, unique per attempt>", "confirm": true, "confirm_owner_inbox": true }
```
Missing either boolean ⇒ rejected with `reason: confirm_and_owner_inbox_required`. `GIT_VERIFIED`.

- **Expected result:** one email in `admin@leadsgenai.in`.
- **Evidence to capture:** the `/send` response body, then `GET .../last`, plus the received message headers.
- **Idempotency proof:** re-POST the **same** `idempotency_key` and confirm no second email arrives.
- **Rollback / containment:** none needed — single message to your own inbox. If it misfires, `AUTO_EMAIL_OUTREACH` is already `0`, so nothing else sends.

## A2 — Estique: human 1-click send (2nd paying customer)

1. `https://leadsgenai.in/app/inbox` (Hot Queue).
2. Locate the Estique row, read the drafted message, **edit if needed**, click send.

- **Owner input:** the go/no-go judgement and any copy edit. This is a business decision, not a technical one.
- **Expected result:** one outbound message to one prospect; the row leaves the hot queue.
- **Evidence:** queue row state before/after, the provider send receipt, and any reply.
- **Containment:** bulk email and WhatsApp auto-send stay OFF — this path sends exactly one message per click.

## A3 — Jiya authenticated video review

Two steps, in order.

1. **Arm the cohort gate** (owner, on the VPS `.env`): `VIDEO_CUSTOMER_REVIEW_ENABLED=1` and `VIDEO_CUSTOMER_REVIEW_CLIENTS=jiya-makeover`. Flag name `GIT_VERIFIED` at `app/marketing/video_production/flags.py:42`.
   - Use the repo's pin-safe recreate path so `APP_VERSION` is not lost (ADR-097). Do **not** hand-write `docker compose up`.
2. **Authenticated read-only preview canary** as the Jiya customer, then the approval decision.

- **Expected result:** Jiya sees the review surface; approval is recorded once.
- **Evidence:** the flag values re-probed after recreate, the authenticated page load, and the approval ledger entry.
- **Rollback:** unset `VIDEO_CUSTOMER_REVIEW_CLIENTS` (or set the flag to `0`) and recreate pin-safe. Per ADR-142, **Reject is terminal — there is no regeneration**, so decide before clicking.

## A4 — Consented inbound / browser voice test

1. `https://leadsgenai.in/app/test-call` — browser web-call, no PSTN, no dialing.
2. Confirm consent on the page, run one short call, listen.

- **Expected result:** Swara responds; transcript is captured (web calls store transcript only, no WAV).
- **Evidence:** the transcript and your subjective quality read.
- **Containment:** `PLATFORM_DIAL_DAILY=0` — no external number is dialed. Outbound calling stays HARD OFF regardless of this test.

---

## Explicitly NOT in this packet — keep OFF

Bulk email · WhatsApp auto-send · platform dialing · social publishing · UPI auto-activation ·
sales-autopilot live channels. Each needs its own separate authorization and canary.

**Sales Autopilot posture note (UPDATED 2026-08-01):** owner mandate "sab on karo" →
`SALES_AUTOPILOT_DRY_RUN=0` (REAL execution), `SALES_AUTOPILOT_EMAIL_ENABLED=1` (email live),
`OPENCLAW_REQUIRE_APPROVAL_FOR_AMBER=0` (Boss autonomy). WhatsApp `WHATSAPP_AUTO_SEND=0`
remains 1-click human + `platform_dial` test-mode cap 10 (legal/ban gates — do NOT flip).
> **SUPERSEDED 2026-08-02 (historical snapshot):** platform_dial went FULL CAMPAIGN LIVE —
> cap 10 → `PLATFORM_DIAL_LIMIT=100`, `PLATFORM_DIAL_DAILY`=boolean `1`. See `docs/context/CURRENT_STATE.md`.
Prod `48f0577`, last tick 2026-08-01T14:55Z `dry_run:false` processed 0 (single prospect
`converted`). Prior dry-run posture (from PR #194 canary) superseded by this owner action.
`DIRECT_HOST_VERIFIED 2026-07-31T05:41Z`.

## Known infrastructure gaps (owner/ops, not launch blockers for Marketing P1)

- **Postiz container is ABSENT** → `https://postiz.leadsgenai.in` returns **502**.
  `DIRECT_HOST_VERIFIED`. Own-brand social publishing is down. Social publish is OFF anyway, so
  this blocks nothing today — but the earlier claim that own-brand social is "fully wired" is not
  true while the container is missing.
- **WAHA** answers on `127.0.0.1:3111` with `401 Unauthorized` — i.e. the service is **up** and
  requires its API key. A previous handoff called it "FAILED"; that is inaccurate. Session state
  was not verified (would need the key).
- `leadgen_app_staging` runs `APP_VERSION=latest` — the known ADR-097 provenance pattern, on a
  **non-production** service.
