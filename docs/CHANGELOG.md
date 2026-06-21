# Changelog & Release Notes — LeadGenAI

> Format: [Keep a Changelog](https://keepachangelog.com/) style · **Full history:** [`SESSION_LOG.md`](SESSION_LOG.md)
> **Deploy tag:** Docker image rebuild on VPS · **Public URL:** https://leadsgenai.in

---

## [Unreleased]

### Added
- Enterprise doc pack: PRD, Architecture, Agent Registry, Prompt Library index, Client Onboarding Kit, Security Playbook, DR, Workflow Maps, KPI Spec, RACI, this CHANGELOG
- Admin UPI configure API (`POST /api/admin/upi/configure`) + `data/platform_upi.json` fallback
- Honest `ready_for_first_paid_customer` gate (requires armed UPI VPA)
- Architecture Explorer 100% engine coverage (60%→70/70): 6 new retention-engine nodes + accurate `files:` mapping · `scripts/explorer_apply_engines.py`
- `scripts/sync_api_docs.py` — auto-regenerate API.md endpoint index (773 ops) from `app.openapi()` (`--check` CI drift gate)

### Changed
- **Marketing plan feature lists expanded** — `app/marketing/packages.py` (Trial 11 · Starter 15 · Growth 18 · Advanced 14) synced to `/pricing`, landing, explorer, sales kits, **`PROJECT_HANDOFF.md` §2**, **`PRODUCT_HANDOFF_SOP.md` §1.3**, `PROJECT_SOP.md` PART D, `CLIENT_ONBOARDING_KIT.md` §5 (deploy `7745725`)
- `/api/public/pay-info` reads unified `upi_config`
- Godfile refactor merged to main: `growth.py` −55% / `marketing.py` −62% → split into `growth_revenue`/`growth_crm`/`growth_deliverability`/`growth_feature_flags` + `marketing_tools`/`marketing_models` (routes unchanged)
- `docs/API.md` base URL → `https://leadsgenai.in`

### Security
- Stripe webhook fail-CLOSED in production when secret unset (503, mirrors Twilio)
- Closed 3 audit-flagged HIGH test gaps: Twilio prod-503, Vobiz status-webhook dedup, customer-portal invoice cross-tenant IDOR (`tests/test_hardening_gaps_2026.py`)

---

## [2026-06-20] — Handoff + readiness infra

### Added
- `docs/PROJECT_HANDOFF.md` — complete takeover doc
- `docs/PROJECT_SOP.md` — engineering + business SOP
- Track B admin features: revenue trend, client timeline, system health detail (flag-gated)
- Customer inline lead status edit (B4)
- `scripts/vps_enable_readiness_flags.py`

### Fixed
- Boot-grace scheduler skip on restart storm
- Celery flood guard (`acks_late=False` + Redis NX lock on self_improve)

---

## [2026-06-18] — Telephony + payments pivot

### Removed
- Razorpay gateway entirely (manual UPI primary)
- Exotel provider (Vobiz only)

### Added
- Vobiz stream cross-path parity (metering + qualify + webhooks)
- UPI admin activate flow in God Mode

---

## [2026-06-16] — F–M production hardening batch

### Added
- Activation readiness 13 probes (`/api/activation/readiness`)
- Customer webhooks (Svix-style HMAC)
- Customer TOTP 2FA
- MCP-as-product + A2A agent card
- Eval gate, ops alerts, engineer agents (Pranav/Vidya/Arnav)
- Per-tenant feature flags

---

## [2026-06-11] — Product split pricing (ADR-009)

### Changed
- Two products: Marketing vs Voice (no bundle USP)
- Marketing: ₹1,199 / ₹2,999 / ₹6,999
- Voice: flat band A/B/C pricing

---

## [2026-06-09] — Production cutover

### Changed
- SQLite+systemd → Docker Postgres+Redis+Celery
- Live at leadsgenai.in

---

## Release process (how to update this file)

1. Ship feature/fix to `main`
2. Add bullet under `[Unreleased]` or new dated section
3. On VPS deploy verify: `/health` = production
4. Move `[Unreleased]` → `[YYYY-MM-DD]` when tagging mentally (no semver tag required yet)

**Categories:** Added · Changed · Fixed · Removed · Security
