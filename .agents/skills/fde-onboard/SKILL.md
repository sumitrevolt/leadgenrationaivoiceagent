---
name: fde-onboard
description: Full done-for-you client onboarding — website→KB seed, first content pack, mini-site, lead-capture widget, customer login, drip journey. Use when the user says "naya client onboard karo", "client setup", "done-for-you", "onboarding", "client ko live karo", or after a client signs up and needs their whole stack stood up.
---

# FDE Onboard (done-for-you client setup)

`app/marketing/onboarding.py` — client add hote hi auto-setup. Gated `AUTO_ONBOARD=1` (hourly sweep) ya manual `onboarding.run_onboarding_sweep()`. Defensive (kabhi raise nahi).

## What auto-setup stands up (per client)
1. **Website → KB seed** — `deep_extract` (Crawl4AI/trafilatura) client website → `KnowledgeBase` + LightRAG, namespace `client:<id>`. Voice/chat ab client-grounded.
2. **First content pack** — `data/client_packs/<id>.html` (posts/posters/captions).
3. **setup_done** flag → dobara nahi chalega.

## Full manual onboarding flow
1. **Add client**: `clients_store` onboard (admin `/app/clients`) → `client_id` + `slug`.
2. **Customer login**: `POST /api/customer/auth/set-password {email,password,client_id}` (admin) → client `/app/login` se apna dashboard. Optional: customer khud TOTP 2FA enroll kar sakta (`/api/customer/2fa/*`) ya magic-link (`MAGIC_LINK=1`).
3. **Mini-site**: `/b/<slug>` auto-live (booking + reviews). Customize: `/app/minisite-builder` (palette/3-layout/logo).
4. **Web widget**: `GET /api/marketing/embed-snippet?slug=<slug>` → client apni site pe `<script>` paste kare (CORS-free iframe; leads dashboard me `source_slug` se link).
5. **Content**: `auto_content` daily queue (1-click copy/PNG/WA). Festivals: `POST /api/marketing/festival-autoschedule`.
6. **Bulk via FDE**: ek brief se sab → `fde-deploy` skill (Neo).
7. **Automation me daalo**: cadence/journey (gated engines — `automation-flags` skill).

## Gotchas
- Auto-publish (Meta/GBP) blocked → content "ready", human 1-click post.
- KB seed (deep_extract) heavy — `AUTO_ONBOARD=1` background hourly; manual ke liye sweep call.
- Anti-hijack: signup guard name/phone-dedupe pe owned-client pe login attach block karta.

## Verify
Client onboard → `/b/<slug>` 200 (mini-site) · `data/client_packs/<id>.html` exists · KB query namespace `client:<id>` semantic hit · login `/app/login` → customer dashboard apna data dikhता.
