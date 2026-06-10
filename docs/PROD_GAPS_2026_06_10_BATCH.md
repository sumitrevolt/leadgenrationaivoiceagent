# Prod-readiness gap analysis + batch (2026-06-10 PM)

## Honest kamiya (research + live-state audit ke baad)

Research basis: FastAPI prod guides (Render/TestDriven/dev.to zero-downtime + Alembic-from-day-one), open-source SaaS revenue stack (Formbricks/Fider = feedback, Hyperswitch-pattern = payment recon, Churnkey-pattern = dunning jo humara already hai).

**Claude-buildable (IS batch me closed):**
1. **Alembic adopt incomplete** — scaffold + 5 revisions repo me the, par live Postgres kabhi `stamp head` nahi hua → schema drift create_all pe depend. FIX: `scripts/alembic_baseline.sh` (dry-run default, `--apply` = sirf stamp, zero DDL).
2. **Revenue-leak blind spot** — Razorpay me payment aaye par webhook miss ho (downtime/secret) to koi record nahi banta, kisi ko pata nahi chalta. FIX: `app/billing/payment_recon.py` daily READ-only recon (gated `PAYMENT_RECON=1`), digest job wired, mismatch = email alert.
3. **Retention measurement zero** — client khush hai ya nahi = guess. FIX: `app/platform/nps.py` NPS/CSAT collector (public submit rate-limited, detractor alert gated `NPS_ALERTS=1`, promoter → review-request suggest, per-client WhatsApp survey drafts ban-safe).
4. **Programmatic SEO sirf Google-crawl pe depend** — 460+ pages/blogs ka Bing/Yandex instant-index nahi. FIX: `app/marketing/indexnow.py` (FREE IndexNow, key self-host `/indexnow-key.txt`, blog job me sitemap-diff auto-submit gated `INDEXNOW=1`, admin manual force route).

**USER-ACTION pending (Claude build NAHI kar sakta — paisa/paperwork/dashboard):**
- Razorpay dashboard webhook register + `RAZORPAY_WEBHOOK_SECRET` (dunning/topup/auto-invoice/recon sab iski events pe better)
- DLT (Udyam se re-apply) + Exotel KYC+recharge → cold-calling unlock
- Cloudflare token perms widen (zone create + R2) → CDN/WAF + offsite backups
- UPI_VPA set · HA/2nd server (spend) · secondary cold-email domain

**Jaan-bujhke deferred (ADR-lite):**
- Blue-green deploys: Caddy `lb_try_duration 25s` + CI auto-rollback already near-zero-downtime dete hain; doosra app-port + Caddy host config touch karna risk > reward abhi. Revisit jab paying clients > 10.
- SOPS/age secrets: `.env` gitignored + VPS-only abhi kaafi; SOPS tab jab >1 operator ho.

## Naye flags (default OFF = zero behaviour change)
`NPS_ALERTS` · `PAYMENT_RECON` · `INDEXNOW` (registry `AUTOMATION_FLAGS` me added)

## Routes
- PUBLIC: `POST /api/growth/nps/submit` (10/60s) · `GET /indexnow-key.txt`
- Admin: `GET /nps/stats` · `GET /nps/request-drafts` · `GET/POST /revenue/recon(/run)` · `POST /seo/indexnow`

## Wiring
- digest job → `payment_recon.run_if_enabled()` · blog job → `indexnow.submit_sitemap_if_enabled()`
- ⚠️ `/indexnow-key.txt` = naya main.py route → deploy ke baad HARD RELOAD zaroori.
