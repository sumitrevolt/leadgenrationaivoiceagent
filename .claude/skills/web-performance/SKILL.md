---
name: web-performance
description: Web performance + Core Web Vitals review for the LeadGen AI public pages (landing, /pricing, /audit, /blog, /b/{slug} mini-sites). Use when changing public HTML/CSS/JS, when pages feel slow, or to improve conversion + SEO (faster pages = more leads + better Google ranking). Triggers - "page is slow", "performance", "core web vitals", "lighthouse", landing/pricing page change.
---

# Web Performance & Core Web Vitals (LeadGen AI)

Measure-first. For a lead-gen business, page speed directly drives conversion (every 1s slower ≈ ~7% fewer conversions) AND local SEO ranking. This matters for actually getting leads, not just polish.

## When to Use
Editing landing/`pricing.html`/`audit.html`/blog/mini-site, or investigating slowness.

## Process (measure → fix → re-measure)

1. **Measure first.** Lighthouse / PageSpeed Insights on the live URL (mobile profile — Indian SMB traffic is mostly mobile). Record LCP, CLS, INP, TBT. Don't optimize blind.
2. **Targets:** LCP < 2.5s, CLS < 0.1, INP < 200ms (mobile, 4G).
3. **Quick wins for this stack:**
   - **Cloudflare in front** (see docs/INFRA_HARDENING_GUIDE.md) → cache static (`/site/*`, posters, blog), edge compression, HTTP/3. Biggest win.
   - **Images/posters:** SVG posters are light (good); compress any raster, lazy-load below-fold, set width/height (avoid CLS).
   - **No render-blocking:** inline critical CSS, defer non-critical JS (the vanilla-JS pages are already light — keep them that way; no heavy frameworks).
   - **Fonts:** system-ui stack (already used) — no web-font download.
   - **3rd-party scripts:** Stripe/analytics load async/deferred, not blocking.
4. **Server side:** Caddy gzip/brotli on; app responses fast (PgBouncer pooling helps); cache `/api/data/niches` etc. where static.
5. **Re-measure** after each change — prove the metric moved.

## Red Flags
- Optimizing without a Lighthouse baseline. · A heavy JS framework added to a vanilla page. · Images without dimensions (CLS). · Render-blocking 3rd-party script. · Caching API responses that are user-specific.

## Verification
- Before/after Lighthouse scores (mobile) — LCP/CLS/INP improved, in target. Show the numbers, not "feels faster".
