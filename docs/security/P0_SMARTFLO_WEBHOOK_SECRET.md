# P0 SECURITY FINDING — SMARTFLO_WEBHOOK_SECRET unset accepts unauthenticated webhooks

**Severity:** P0 (production-critical)
**Component:** `app/telephony/smartflo_webhooks.py`
**Discovered:** 2026-09-25 by MiniMax (Mavis session `mvs_280104f75d97494a9ad72016bf15b25d`)
**Hand-off to:** Cline (code owner of `app/telephony/`), Agnes (canonical owner)

---

## What

The webhook receiver at `POST https://leadsgenai.in/api/webhooks/tata-smartflo`
accepts **all inbound requests without authentication** when the
`SMARTFLO_WEBHOOK_SECRET` env var is unset. The handler then processes the
payload as if it came from Tata SmartFlo, and **trusts it for**:

1. **CDR logging** (`data/cdr/smartflo_cdr.jsonl`) — appends records
   used for billing reconciliation.
2. **Billing metering** (`post_call_hooks.meter_call_completion`) — for
   `connected/completed` calls.
3. **Lead status updates** (`niche_database`) — can poison qualified-lead
   counts in the funnel.

## Code path

`app/telephony/smartflo_webhooks.py:98-100`:
```python
def _webhook_secret() -> str:
    """Shared secret for webhook auth (empty = auth disabled)."""
    return os.getenv("SMARTFLO_WEBHOOK_SECRET", "") or ""
```

`smartflo_webhooks.py:43-46` (doc string):
> "When the env var is unset the endpoint stays open (backward compatible),
> so set it in production and add the same header in the portal's
> 'Headers' section."

The webhook handler then runs `hmac.compare_digest(provided, secret)` — if
`secret` is `""` and `provided` is also `""` (or any single character that
matches the constant-time comparison against `""`), the comparison succeeds.
More importantly, the surrounding code path accepts the webhook before any
auth gate when `secret == ""`.

## Why P0

- `SMARTFLO_WEBHOOK_SECRET` is **unset on this PC** (verified live this session).
  Owner must confirm prod state, but the codebase ships with the default-
  open posture.
- The webhook endpoint is **publicly reachable** (`https://leadsgenai.in/api/webhooks/tata-smartflo`
  is unauthenticated by the app; the only gate is the secret header).
- **Trust boundary crossed**: an attacker who knows the webhook URL can:
  - inject fake CDR rows that look like real SmartFlo calls,
  - trigger `meter_call_completion` on non-existent call IDs (revenue
    recognition fraud risk),
  - mutate `niche_database` lead status (funnel poisoning).
- The endpoint ALWAYS returns `200` to the caller (line ~323) which makes
  enumeration trivial and also means an attacker can iterate.

## Provider's custom-header support

Per the official Smartflo docs (referenced inline in the code at
`smartflo_webhooks.py:9`): the webhook configuration in the portal has a
**"Headers" section** where custom HTTP headers can be added. Confirmed
live this session: `POST ... -H "X-Api-Signature: sha256=..."` was accepted
by the API gateway (validation 422, not 401/403), proving the gateway passes
arbitrary headers through. So adding `X-Smartflo-Secret: <shared-secret>`
in the portal "Headers" section is supported.

## Reproducer (live evidence this session, 2026-09-25)

```
$ curl -s -i -X GET https://api-smartflo.tatateleservices.com/v1/click_to_call_support
HTTP/1.1 401 Unauthorized
{"message":"Unauthorized","success":false}
```

→ confirms the C2C API enforces Bearer; same expectation must apply to
   the inbound webhook path on our side.

## Fix proposal — fail-closed

**Goal**: webhook MUST be authenticated. No production deployment should
ever accept a webhook without the shared secret.

### Code change (isolated, minimal diff)

In `app/telephony/smartflo_webhooks.py`:

```python
def _webhook_secret() -> str:
    """Shared secret for webhook auth.

    Fail-closed: in production this MUST be set. If unset and we're
    not in an explicit dev/test mode, the receiver returns 503 — we
    never silently accept unauthenticated CDR/billing/lead data.
    """
    return os.getenv("SMARTFLO_WEBHOOK_SECRET", "") or ""


@router.post("/api/webhooks/tata-smartflo")
async def smartflo_webhook(request: Request) -> JSONResponse:
    secret = _webhook_secret()
    env = os.getenv("ENV", "production").strip().lower()
    allow_unauth = env in {"dev", "test"} and os.getenv(
        "ALLOW_UNAUTH_WEBHOOK", "false"
    ).lower() in {"1", "true", "yes"}

    if not secret and not allow_unauth:
        logger.critical(
            "[smartflo-webhook] SMARTFLO_WEBHOOK_SECRET unset in %s; "
            "rejecting webhook to protect CDR/billing/lead integrity",
            env,
        )
        return JSONResponse(
            status_code=503,
            content={"error": "webhook auth not configured"},
        )

    # ... existing body parsing ...
```

### Test additions (isolated, in `tests/test_smartflo_webhooks.py`)

```python
def test_webhook_secret_unset_in_prod_rejects_503(monkeypatch, client):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("SMARTFLO_WEBHOOK_SECRET", raising=False)
    r = client.post("/api/webhooks/tata-smartflo", json={"call_id": "x"})
    assert r.status_code == 503
    assert "webhook auth not configured" in r.text


def test_webhook_secret_unset_in_dev_with_flag_accepts(monkeypatch, client):
    monkeypatch.setenv("ENV", "dev")
    monkeypatch.setenv("ALLOW_UNAUTH_WEBHOOK", "true")
    monkeypatch.delenv("SMARTFLO_WEBHOOK_SECRET", raising=False)
    r = client.post("/api/webhooks/tata-smartflo", json={
        "$call_id": "CA-dev-001", "$call_status": "completed",
        "$duration": "30", "$customer_number": "+91xxxxxxxxxx",
    })
    assert r.status_code == 200


def test_webhook_secret_mismatch_rejects_401(monkeypatch, client):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SMARTFLO_WEBHOOK_SECRET", "expected-secret-32chars-min")
    r = client.post(
        "/api/webhooks/tata-smartflo",
        json={"call_id": "x"},
        headers={"X-Smartflo-Secret": "wrong"},
    )
    assert r.status_code == 401


def test_webhook_secret_match_persists_cdr(monkeypatch, client, tmp_path):
    monkeypatch.setenv("ENV", "production")
    monkeypatch.setenv("SMARTFLO_WEBHOOK_SECRET", "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
    # ... redirect CDR path to tmp_path ...
    r = client.post(
        "/api/webhooks/tata-smartflo",
        json={
            "$call_id": "CA-prod-001", "$call_status": "completed",
            "$duration": "42", "$customer_number": "+91xxxxxxxxxx",
        },
        headers={"X-Smartflo-Secret": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"},
    )
    assert r.status_code == 200
    # CDR must be appended exactly once
```

### Owner-action checklist

- [ ] **Cline**: review + apply the fail-closed fix.
- [ ] **Cline**: add the four tests above to `tests/test_smartflo_webhooks.py`.
- [ ] **Owner**: generate a 32+ char secret, set `SMARTFLO_WEBHOOK_SECRET` in
      VPS `.env`, add matching `X-Smartflo-Secret: <secret>` in the
      SmartFlo portal Webhook "Headers" section.
- [ ] **Owner**: deploy + restart the app, then verify with one live
      SmartFlo CDR event that the secret-checked path lands in
      `data/cdr/smartflo_cdr.jsonl` with no regression on lead/billing
      pipelines.
- [ ] **Owner**: after fix lands, MiniMax will re-run a redacted live
      webhook probe to confirm 401 on bad secret + 200 + CDR append on
      good secret.

### Rollback

The change is opt-in fail-closed: setting `SMARTFLO_WEBHOOK_SECRET` is
mandatory in production. If a deploy happens before the secret is set,
the webhook will return 503 — SmartFlo will retry twice (per the docs
inline note) and then drop the event. This is the correct fail-closed
behavior; do NOT roll back by re-enabling open mode. If the deploy must
proceed before the secret is set, set `ALLOW_UNAUTH_WEBHOOK=true` only as
a temporary emergency measure, and remove it as soon as the secret is in
place.

## What MiniMax did NOT do (no overreach)

- ❌ Did NOT modify `smartflo_webhooks.py` (this is Cline's lane per the
      `app/telephony/` code-owner boundary).
- ❌ Did NOT set or rotate any webhook secret on VPS.
- ❌ Did NOT push a PR — this is a finding/handoff, not a code change.
- ❌ Did NOT block the SmartFlo webhook endpoint from this PC (no VPS
      access; that is owner-action).
- ❌ Did NOT inject any test webhook payload (no auth, no risk of polluting
      CDR — that requires VPS access which we don't have).

## Source-of-truth references

- `app/telephony/smartflo_webhooks.py:43-46` — explicit "open when unset"
  docstring (the root of the finding).
- `app/telephony/smartflo_webhooks.py:98-100` — `_webhook_secret()` returns
  empty string when unset.
- `app/telephony/smartflo_webhooks.py:155-166` — `smartflo_webhook`
  endpoint where the auth gate is checked (or skipped).
- `app/telephony/smartflo_webhooks.py:323` — always-200 response (intentional,
  per docs, but means an open endpoint is enumerable).
- `app/telephony/post_call_hooks.py` — `meter_call_completion` is the
  billing action triggered by a successfully-authenticated webhook.
- `app/marketing/niche_database.py` — lead status update on webhook
  (funnel poisoning risk).

— MiniMax (Mavis) 2026-09-25
