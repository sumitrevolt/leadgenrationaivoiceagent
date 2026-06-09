---
name: security-review
description: Security + hardening review for the LeadGen AI platform (FastAPI + payments + public endpoints + telephony compliance). Use BEFORE merging any change that touches auth, user input, payment webhooks, public endpoints, secrets, or outbound calling/messaging. Triggers - "is this safe", "security review", "before I ship", new public route, new env/secret, payment/DLT/DND code.
---

# Security & Hardening Review (LeadGen AI)

OWASP-grade review tailored to THIS stack. AI agents default to the happy path — this skill forces the security checks senior engineers do before production.

## When to Use
Any change touching: auth/JWT, user input, `/api/public/*` (no-auth), payment webhooks (`/api/billing/webhooks/*`), telephony (calls/WhatsApp/email outbound), secrets/.env, file writes, or external API calls.

## Process (verify each, cite evidence)

1. **Public endpoint abuse** — every `/api/public/*` and unauth route MUST have: honeypot (where forms), rate-limit (`_rate_limited`), input length caps, no LLM/cost amplification without throttle. ⚠️ KNOWN GAP: `/api/ai/command` is unauth + calls free-LLM — add rate-limit/auth before promoting.
2. **AuthZ not just AuthN** — `require_admin` / `require_customer` on every write. Customer endpoints must scope to `sub=client_id` (no cross-tenant read). Verify the dep is actually applied, not just imported.
3. **Payment integrity** — webhook signature verify (Razorpay/Stripe) is MANDATORY before acting. Never trust client-sent amounts. `verify-payment` must check signature server-side.
4. **Secrets** — only in `.env` (gitignored). NEVER in code/CLAUDE.md/scripts/commits. New secret? Confirm it's `.env`-only + `.env.example` documents the NAME (not value). Check `git diff` for accidental secret leak.
5. **Injection / input** — SQLAlchemy params (no f-string SQL), validate phone/email, sanitize anything rendered to HTML (XSS), cap upload sizes.
6. **Telephony/messaging compliance (₹10L risk)** — DLT + 140-series + DND scrub + 10am-7pm + AI-disclosure for cold calls; DND fail-CLOSED. WhatsApp bulk auto-send = ban → 1-click/official-API only. No foreign trunks for India-domestic.
7. **Dependency + headers** — new dep? check it's maintained. CORS not `*` in prod. Security headers via middleware.

## Red Flags
- "It's internal so no auth needed" (it's reachable). · New `/api/public/*` with no rate-limit. · Acting on a webhook before signature check. · A secret value in a non-.env file. · Auto-send WhatsApp/cold-call without DLT/consent gate.

## Verification (evidence required)
- Show the auth dependency on the route + a test hitting it unauth → 401/403.
- For webhooks: show signature-verify runs first.
- `git diff` clean of secrets. `grep -rn "WHATSAPP_AUTO_SEND\|MISSED_CALL" ` confirms gates default-off.
- "Seems safe" is never sufficient — show the check.
