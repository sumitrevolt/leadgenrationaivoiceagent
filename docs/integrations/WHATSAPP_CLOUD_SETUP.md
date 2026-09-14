# WhatsApp Cloud API — setup + one-flag switch runbook (2026-09-14)

**Goal:** the platform currently runs WhatsApp through the self-hosted **WAHA** provider
(`WHATSAPP_PROVIDER=waha`). This doc makes the **official Meta WhatsApp Cloud API** path
configurable and verifiable so switching is a **one-flag operation** once the Meta
credentials exist.

**Code status (this branch, `ops/whatsapp-cloud`):** both engines stay wired;
`senders` are chosen in exactly one place — `app/integrations/whatsapp.py::get_whatsapp_sender()`
(WAHA when `WHATSAPP_PROVIDER=waha` + `WAHA_BASE_URL`, else Cloud API). Audit findings and the
three gaps fixed on this branch are at the bottom.

---

## 1. Owner steps (browser, Meta side) — nothing here can be done from the repo

1. **Create a Meta app** — https://developers.facebook.com/apps → *Create app* → business type.
   Use the **same** app/business that already owns the Pages/Instagram assets where possible
   (app `LeadsGenAI`, id `1278868110768460`, is the known owner app).
2. **Add the WhatsApp product** to that app (*Add product* → WhatsApp → *Set up*).
3. **Note the two IDs** from *WhatsApp → API Setup*:
   - **Phone number ID** → `WHATSAPP_PHONE_NUMBER_ID` (a numeric id, **not** the phone number)
   - **WhatsApp Business Account ID** → `WHATSAPP_BUSINESS_ACCOUNT_ID`
4. **Mint a permanent token**: *Business settings → Users → System users* → create/choose a
   system user → *Generate token* → select the app → permissions
   **`whatsapp_business_messaging`** (+ `whatsapp_business_management` if you want the verify
   script to also read the WABA) → **never expires** → `WHATSAPP_BUSINESS_TOKEN`.
   (The temporary 24 h token on the API Setup page is fine for a first smoke, not for prod.)
5. **Copy the App Secret**: *App settings → Basic → App secret* → `WHATSAPP_APP_SECRET`
   (this is what verifies `X-Hub-Signature-256` on every inbound webhook).
6. **Set the webhook**: *WhatsApp → Configuration → Webhook → Edit*:
   - **Callback URL** → `https://leadsgenai.in/api/webhooks/whatsapp`
     (alternative, equally valid: `https://leadsgenai.in/api/wa/webhook` — see §4)
   - **Verify token** → the value you put in `WHATSAPP_VERIFY_TOKEN` (you choose it; generate
     with `python -c "import secrets;print(secrets.token_urlsafe(32))"`)
   - Meta immediately GETs the URL with `hub.mode=subscribe&hub.verify_token=…&hub.challenge=…`;
     the app must answer with the challenge. If it fails → token mismatch or the flag/route is
     not deployed (see §5 troubleshooting).
7. **Subscribe to fields**: tick **`messages`** (required; that's inbound texts + delivery
   statuses). Add `message_template_status_update` if you want template-approval events later.
8. **Message templates**: business-initiated messages (anything outside a 24 h customer-service
   window — drip/reactivation/lead follow-up) need an **approved template**. Submit them in
   *WhatsApp → Message templates*; register the same names locally with
   `POST /api/wa/templates` (`name` must match Meta's template name exactly). Free-form text
   only delivers inside the 24 h window after a customer message.
9. **Registration caveat**: the Cloud API phone number must **not** be registered on the
   WhatsApp app / another provider (see §6 — this is the main risk with the currently linked
   number).

## 2. Env vars (`.env` on the VPS — values never in the repo/chat)

| # | Variable | Where to get it | Required |
|---|---|---|---|
| 1 | `WHATSAPP_BUSINESS_TOKEN` | System user token, `whatsapp_business_messaging` | ✅ |
| 2 | `WHATSAPP_PHONE_NUMBER_ID` | API Setup → Phone number ID | ✅ |
| 3 | `WHATSAPP_BUSINESS_ACCOUNT_ID` | API Setup → WABA ID | recommended (verify script lists subscribed apps) |
| 4 | `WHATSAPP_APP_SECRET` | App settings → Basic → App secret | ✅ (webhook POST is fail-closed without it in production) |
| 5 | `WHATSAPP_VERIFY_TOKEN` | you choose it; same value typed into Meta's webhook config | ✅ |

Optional: `WHATSAPP_BUSINESS_NUMBER` (digits + country code; used for the mismatch check and by
the WAHA path) · `WHATSAPP_GRAPH_VERSION` (default `v18.0`) · `WHATSAPP_PROVIDER`
(`cloud` \| `waha`).

## 3. Verify (after pasting credentials)

```bash
cd /opt/leadgen          # or the repo root locally
python scripts/whatsapp_cloud_verify.py
```

- Exit **1** + an itemised "where to get it" checklist = a required value is missing.
- Exit **2** = Meta rejected the call (bad/expired token, wrong phone id) — the Meta error
  message + code is printed.
- Exit **0** = the phone-number call succeeded; the script prints `display_phone_number`,
  `verified_name`, `quality_rating`, plus WABA/subscribed apps (best-effort) and warns if
  `WHATSAPP_BUSINESS_NUMBER` does not match Meta's display number.
- It **never prints** the token, app secret or verify token (lengths only).

Then confirm on the running app: `GET /api/wa/status` (admin JWT) → `provider`,
`cloud_creds_present: true`, `selfhost_active: false` once switched.

## 4. The switch (one flag) + rollback

A number is on **Cloud API XOR WAHA — never both**. Switching is:

```bash
# 1) edit /opt/leadgen/.env  (owner-only; values never pasted in chat)
#    WHATSAPP_PROVIDER=cloud
# 2) recreate ONLY the app service with the RUNNING image tag (never :latest)
cd /opt/leadgen
APP_VERSION=$(docker compose -f docker-compose.vps.yml ps --format '{{.Image}}' app | sed 's/.*://') \
  docker compose -f docker-compose.vps.yml up -d --no-deps --force-recreate app
```

Rollback = set `WHATSAPP_PROVIDER=waha` back and recreate the same way (plus re-link the WAHA
session if it was logged out — §6).

⚠️ **`WHATSAPP_AUTO_SEND` stays `0`** through the switch. Turning it on is the ban-risk gate and
is separate: it also requires the recipient on `WHATSAPP_SEND_ALLOWLIST` (canary) and not
opted-out/suppressed — all enforced fail-closed at the sender boundary
(`app/integrations/whatsapp.py::send_permitted`, §5 of CLAUDE.md).

## 5. Webhook routes that exist in the app (both live, both signature-verified)

| Route | File | Handles |
|---|---|---|
| `GET/POST /api/webhooks/whatsapp` **(recommended)** | `app/api/webhooks.py` | STOP/opt-out (+consent ledger) · WhatsApp Flow `nfm_reply` lead capture · onboarding-interview capture · delivered=ack marking · reply_agent Hinglish draft · failed-status auto-suppress |
| `GET/POST /api/wa/webhook` | `app/api/whatsapp.py` | same signature gate · STOP/opt-out · raw inbound store `data/wa_inbound.jsonl` (no reader in-tree) · reply_agent draft · failed-status auto-suppress |

Both read the same `WHATSAPP_VERIFY_TOKEN` / `WHATSAPP_APP_SECRET`. Meta allows one callback URL
per WhatsApp product, so pick one — the first one does strictly more inbound processing.

Troubleshooting the handshake: `403 verification_failed` = verify token mismatch (or
`WHATSAPP_VERIFY_TOKEN` unset) · 404 = the running image predates the route · every POST
returning `{"ok":false,"reason":"bad_signature"}` = `WHATSAPP_APP_SECRET` wrong/absent
(in production an absent secret is a hard deny — by design).

## 6. Risk: the currently linked number is on the WhatsApp app

The WAHA path links an **existing WhatsApp account** by QR (a companion/Web session). Meta's
phone-number docs are explicit: *"Numbers already in use with WhatsApp cannot be registered
unless they are deleted first."* (https://developers.facebook.com/docs/whatsapp/cloud-api/phone-numbers).
A number linked to a Web/companion session is **in use** by that account — so you cannot simply
"point Cloud at the same number":

- Adding the number to Cloud API requires **deleting the WhatsApp account for that number**
  first (WhatsApp app → Settings → Account → Delete my account). Deleting removes the app's chat
  history and cannot be undone.
- The WAHA session must be **logged out** so the two registrations never coexist. There is no
  app route for this — log the companion device out on the phone (WhatsApp → Linked devices →
  log out of the WAHA session) and/or stop the WAHA container
  (`docker compose -f deploy/compose/docker-compose.waha.yml down`).
- Coexistence is what gets numbers **banned or deregistered** — treat "cloud + WAHA on the same
  number" as forbidden, matching the comment in `.env.example`.

Practical low-risk sequence: use a **second number** for the Cloud API first (verify the whole
path end-to-end with `scripts/whatsapp_cloud_verify.py` + the webhook handshake), then migrate
the primary number only when you're ready to delete it from the WhatsApp app.

## 7. What cannot be done from this repo

- Creating the Meta app, adding the WhatsApp product, minting the System User token, copying the
  App Secret — all Meta-console actions.
- Setting the webhook URL / verify token / subscribed fields in Meta.
- Submitting or approving message templates (and the template names must match Meta's).
- Business verification / display-name approval.
- Knowing **which** webhook URL prod currently has configured: the repo contains two valid
  routes and no way to read Meta's config (only the owner console shows it).

## 8. Audit findings on this branch (code, verified)

| # | Finding | Verdict |
|---|---|---|
| A1 | `app/tasks/whatsapp_automation.py::_meta_config()` read `WHATSAPP_BUSINESS_TOKEN`/`WHATSAPP_PHONE_NUMBER_ID`/`WHATSAPP_BUSINESS_ACCOUNT_ID`/`WHATSAPP_BUSINESS_NUMBER`/`WHATSAPP_PROVIDER` from **raw `os.getenv` with no Settings fallback** → in a container that injects a subset of env, configured creds could read empty and the path silently no-op. | **FIXED** — env-first, then `settings` (`_env_or_setting`). |
| A2 | Graph version was **duplicated**: shared `GRAPH_API_VERSION` (`app/integrations/whatsapp.py`, env-overridable) vs a hardcoded `v18.0` URL in `app/tasks/whatsapp_automation.py`. A version bump would have moved the campaign sender but not this task. | **FIXED** — the task imports the shared constant. |
| A3 | `/api/wa/webhook` GET read the verify token from **raw `os.getenv` only** (its sibling `/api/webhooks/whatsapp` was already Settings-first) → 403 handshake even with the token configured. | **FIXED** — Settings-first + env fallback. |
| A4 | Both GET handshakes compared the verify token with `==` (a shared secret). | **FIXED** — `verify_webhook_token()` (`hmac.compare_digest`, fail-closed on unset/non-ASCII). |
| A5 | `/api/wa/webhook` POST wrapped signature verification in `except: pass` → an error while reading/verifying let the payload through **unverified**. | **FIXED** — fail-closed (mirrors `app/api/webhooks.py`). |
| A6 | Webhook POST *does* verify `X-Hub-Signature-256` with `WHATSAPP_APP_SECRET` (`verify_meta_signature`, constant-time, production fail-closed when unset). | already correct — untouched. |
| A7 | `app/marketing/whatsapp_campaign.py` reads creds via `settings` and provider via `is_active_provider()` (env→Settings); `app/integrations/whatsapp.py` reads token/phone id via `settings`. | already correct — untouched. |
| A8 | **Reported, NOT fixed (out of this change's scope):** `app/tasks/whatsapp_automation.py::send_template_message` POSTs to Graph **directly**, bypassing `send_permitted()` (canary allowlist + opt-out/suppression ledger). Its own gates are `WHATSAPP_AUTO_SEND` + `HARD_OFF` + true daily cap + fail-closed DND. If `WHATSAPP_AUTO_SEND=1` is set for the campaign path with a canary allowlist, this legacy task would message non-allowlisted leads — owner decision needed (route it through `get_whatsapp_sender()` or retire it). | open finding |
| A9 | **Reported, NOT fixed:** `emergency_stop()` in the same module mutates `/opt/leadgen/.env` with `sed -i` from app code (`.env` is owner-only per §5/§8). | open finding |

Tests added: `tests/test_whatsapp_cloud_webhook_verify.py` (9 tests — handshake from Settings,
wrong/unset token deny, non-ASCII deny, POST bad-signature deny, verifier-exception deny,
valid-signature accept). Existing suites re-run green: `test_track_upgrades.py`,
`test_whatsapp_campaign.py`, `test_whatsapp_automation_body.py`,
`test_whatsapp_auto_send_gate.py`, `test_whatsapp_pending_drafts.py`,
`test_whatsapp_selfhost.py`, `test_wa_inbound_session.py`, `test_wa_conversation.py`,
`test_onboarding_whatsapp_interview.py`, `test_social_whatsapp_provider.py`,
`test_waha_compose_security.py`.

## 9. UNVERIFIED (do not claim these work)

- **No live Cloud API call has ever been made from this repo** — the verify script's success path
  (exit 0) is unexercised until real credentials exist; only the missing-config path (exit 1) and
  the rejection path (exit 401 → exit 2, bogus token) have been observed.
- The webhook handshake against **real Meta servers** is unverified (the local tests simulate
  Meta's GET/POST).
- Which webhook URL prod currently has configured in Meta (no console access from here).
- Whether the finally-chosen number survives Cloud onboarding (depends on the §6 deletion step).
