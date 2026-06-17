---
name: security-review
description: Security + hardening review for the LeadGen AI platform (FastAPI + payments + public endpoints + telephony compliance). Use BEFORE merging any change that touches auth, user input, payment webhooks, public endpoints, secrets, or outbound calling/messaging. Triggers - "is this safe", "security review", "before I ship", new public route, new env/secret, payment/DLT/DND code.
---

# Security & Hardening Review (LeadGen AI)

OWASP-grade review tailored to THIS stack. AI agents default to the happy path — this skill forces the security checks senior engineers do before production.

## When to Use
Any change touching: auth/JWT, user input, `/api/public/*` (no-auth), payment webhooks (`/api/billing/webhooks/*`), telephony (calls/WhatsApp/email outbound), secrets/.env, file writes, or external API calls.

## Process (verify each, cite evidence)

1. **Public endpoint abuse** — every `/api/public/*` and unauth route MUST have: honeypot (where forms, `_rate_limited` bucket), rate-limit dep (`rate_limit("name", N, sec)` from `app/api/ratelimit.py`), Turnstile where applicable (`verify_turnstile`), input length caps, no LLM/cost amplification without throttle. LLM-backed endpoints (`app/api/ai.py`) ab `require_admin` + `tier_rate_limit("ai",30,60)` — naya LLM endpoint isi pattern me gate karo (open free-LLM = abuse surface).
2. **AuthZ not just AuthN** — `require_admin` / `require_customer` on every write. Billing/customer mutations MUST scope to authed client via `_authed_client_id` dep (IDOR-closed, `app/api/billing.py`) — no cross-tenant read/write. Verify the dep is actually applied, not just imported. Anonymous "demo-client" fallback prod me 401 (data.py hole closed).
3. **Payment integrity** — webhook signature verify (Razorpay) is MANDATORY before acting; signature fail-CLOSED. Never trust client-sent amounts. `verify-payment` server-side signature + idempotent (PENDING→PAID). 🚨 Razorpay BLOCKER: `.env` me PLACEHOLDER keys (`rzp_test_you…`/`your-razorpa…`) hain — real `rzp_live_` keys kabhi set nahi hue → checkout/payment-links/topup/dunning DEAD jab tak fix na ho. Pehla paid customer se pehle MUST fix.
4. **Secrets** — only in `.env` (gitignored). NEVER in code/CLAUDE.md/scripts/commits. New secret? Confirm it's `.env`-only + `.env.example` documents the NAME (not value). Check `git diff` for accidental secret leak.
5. **Injection / input** — SQLAlchemy params (no f-string SQL), validate phone/email, sanitize anything rendered to HTML (XSS), cap upload sizes.
6. **Telephony/messaging compliance (₹10L risk)** — DLT + 140-series + DND scrub + 10am-7pm + AI-disclosure for cold calls; DND fail-CLOSED. WhatsApp bulk auto-send = ban → 1-click/official-API only. No foreign trunks for India-domestic.
7. **Dependency + headers** — new dep? check it's maintained. CORS not `*` in prod. Security headers via middleware.

## N.1 hardening LOCKED (verify present, NEVER weaken)
These already shipped — a change that removes/loosens any = regression, reject:
- **IDOR**: `_authed_client_id` dep on every billing mutation (`app/api/billing.py`) — server derives client_id, never trusts body.
- **Webhook signatures fail-CLOSED in prod**: Twilio/Exotel/WhatsApp/Razorpay return 503 when signing secret unset (no unsigned action). (`app/telephony/webhooks.py`)
- **SSRF block on /site-audit**: `app/marketing/website_auditor.py` resolves host + blocks loopback/private/link-local/reserved (cloud-metadata 169.254.169.254, 10./172.16./192.168., 127.0.0.1).
- **Atomic invoice numbering** (no gaps/dupes) + **GST gated on `GST_GSTIN`** (unregistered = no tax charged).
- **Consent ledger** (`app/telephony/consent_ledger.py`): opt-out → instant cross-channel suppression; DND fail-CLOSED.

## Red Flags
- "It's internal so no auth needed" (it's reachable). · New `/api/public/*` with no rate-limit. · Acting on a webhook before signature check. · A secret value in a non-.env file. · Auto-send WhatsApp/cold-call without DLT/consent gate.

## Verification (evidence required)
- Show the auth dependency on the route + a test hitting it unauth → 401/403. Billing mutation → show `_authed_client_id` scoping.
- For webhooks: show signature-verify runs first + prod fail-CLOSED (503 when secret unset).
- `git diff` clean of secrets — run `python scripts/check_secrets.py` (wired in `/verify`; false-positive line = `nosecret`). `grep -rn "WHATSAPP_AUTO_SEND\|MISSED_CALL"` confirms gates default-off.
- "Seems safe" is never sufficient — show the check.
