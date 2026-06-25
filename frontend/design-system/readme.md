# LeadGen AI — Design System

The design system for **LeadGen AI** (leadsgenai.in) — an **AI Automated Marketing + AI Voice Agent** product for Indian local businesses. It posts content, audits Google Business Profiles, generates festival posters, runs WhatsApp campaigns, and (on the Advanced plan) calls every inquiry with a human-like Hindi AI voice to qualify leads.

This repo gives design agents the tokens, components, UI kits and assets to build on-brand LeadGen AI interfaces, mockups and slides.

**Two products, two customer dashboards.** LeadGen AI sells two SKUs — **AI Marketing** and **AI Voice Agent** — and a customer sees a different dashboard per product. This system recreates both customer dashboards plus the internal **Admin Console** (the LeadGen AI team's operator view: every client, the AI agent fleet, MRR, campaigns; deep-indigo sidebar on a slate canvas) and the public **Marketing Website**. The two customer dashboards share one shell (`ui_kits/_shared/shell.jsx`) and differ only in product content.

## Sources
- **Codebase:** `leadgenrationaiagent/` (FastAPI backend + static HTML frontend).
  - Marketing site: `frontend/website/index.html`
  - Customer portal: `frontend/customer_dashboard.html`
  - Admin console: `frontend/admin_dashboard.html`
  - Auth: `frontend/login.html` (customer) · `frontend/admin_login.html` (admin)
  - Logo: `frontend/website/icons/icon.svg` → copied to `assets/logo-mark.svg`
- The product is built as hand-written HTML/CSS (no component framework). This design system **distills** that into reusable tokens + React primitives — it is a recreation, not the production source.

> ⚠️ **Font substitution:** the product loads **Plus Jakarta Sans** + **Inter** from Google Fonts. This system references the same families via Google Fonts (`tokens/fonts.css`) rather than bundled binaries. If you have licensed/self-hosted copies, drop them in `assets/fonts/` and swap the `@import` for `@font-face` rules.

---

## CONTENT FUNDAMENTALS

**Language — Hinglish.** Copy is written in **Romanized Hindi mixed with English** ("Hinglish"), the way Indian SMB owners actually speak. This is the single most defining trait of the brand voice.
- Examples: *"Poora marketing, auto-pilot pe"*, *"Aapko sirf HOT leads"*, *"Sab AI karega"*, *"Naye Leads — inko call karo"*, *"Aaj ka post — copy karke WhatsApp pe daalo"*.
- English is used for product/tech nouns (dashboard, lead, CRM, WhatsApp, AI Voice Agent); Hindi for verbs, connective tissue and reassurance.

**Address — "aap" (you), warm and direct.** Speaks *to* the business owner: *"Aap business batao"*, *"Aapke industry ke liye ready"*. Second person, never corporate-distant.

**Tone — reassuring, plainspoken, money-focused.** Emphasizes ease ("2 minute ka setup"), zero risk ("₹0 charge", "koi card nahi"), and outcomes ("ready-to-buy customers", "paisa yahin hai"). Removes effort: *"baaki AI pe chhod do"*.

**Casing.** Sentence case for body and most headings. UPPERCASE only for tiny eyebrow pills and section labels (e.g. "AI AUTOMATED MARKETING"). Occasional ALL-CAPS word for emphasis ("HOT leads", "FREE").

**Numbers & currency.** Indian conventions: **₹** with Indian comma grouping (₹1,999, ₹5,999), "/mo", "24 ghante", "2 min". Prices are concrete and fixed-monthly (no per-call surprises — a selling point).

**Emoji — YES, used liberally and on-brand.** Emoji act as wayfinding icons and tone-setters throughout the product: 📞 calls, 🔥 hot leads, 📣 posts, ✅ qualified, 💬 WhatsApp, ☀️ "Aaj ke liye", 🚀 upgrade, 🎁 free trial, plus a per-niche emoji set (🏡 ☀️ 🦷 🎓 🏦 …). Use them — a LeadGen screen without emoji feels off-brand.

**Vibe.** Trustworthy local-business sidekick. Festival-aware (Diwali, Holi), WhatsApp-first, results-over-jargon. Indian (🇮🇳) and proud of it.

---

## VISUAL FOUNDATIONS

**Color.** The signature is the **indigo → violet gradient** (`--grad-brand`, `#4f46e5 → #7c3aed`) on every primary CTA, logo well, avatar, number badge and step counter. Brand violet `#6d28d9` anchors the app; the dashboard **sidebar** uses a deep violet vertical gradient (`#2e1065 → #4c1d95`). Neutrals are slightly cool/violet-tinted (ink `#0f1024`, muted `#64647e`, lines `#e8e8f2`), canvases are near-white lilac (`#f6f6fb`). A distinctive **lead-temperature semantic scale** — Hot `#ef4444` / Warm `#f59e0b` / Cold `#3b82f6` — scores every lead. Status uses green/amber/slate (connected / busy / no-answer); WhatsApp green `#1fa855` is its own accent.

**Type.** **Plus Jakarta Sans** for all display/headings — ExtraBold (800), tight `-0.02em` tracking, line-height ~1.12. **Inter** for body & UI (400–600), line-height 1.6. Hero headlines clamp 2.2→3.5rem; gradient-clipped text is used on key hero words.

**Spacing & layout.** 8px base rhythm. Marketing is airy (84px section padding, 1140px container, centered heads with eyebrow→h2→sub). App is denser (1320px, 230px sidebar, 14–18px gaps) with **44px minimum tap targets** (mobile-first SMB users). Sticky nav (marketing) and sticky sidebar + topbar (app).

**Backgrounds.** Mostly clean white / lilac-white. Accent: soft **radial gradient glows** behind the hero and inside dark CTA boxes (violet at low opacity), and subtle vertical section gradients (`bg-soft → #fff`). No photography, no textures, no heavy patterns. Dark panels (final CTA, GBP hook) are ink-to-ink-2 gradients with a violet radial.

**Cards.** White, `1px–1.5px` solid line border, radius **14px (app) / 18px (marketing) / 24px (feature & hero)**, soft violet-tinted shadow. The **featured** state (highlighted pricing plan) swaps to a brand-colored border + `--shadow-brand` glow and a gradient ribbon tag.

**Borders & radii.** Friendly and rounded everywhere: pills (999px) for eyebrows/badges/status, 12px for buttons/inputs, up to 30px for the big CTA box. Borders are thin and low-contrast.

**Shadows.** Soft and diffuse, tinted toward violet/ink rather than pure black. `--shadow-brand` (large indigo-tinted glow) sits under primary CTAs and featured cards; `--shadow-card` (tiny + medium stack) under app panels.

**Motion.** Restrained and friendly. `cubic-bezier(.4,0,.2,1)`, 120–350ms. Signature **hover lift** (`translateY(-2 to -6px)` + shadow) on cards and buttons. Scroll-reveal fade-up on marketing sections. A few playful loops on the hero (pulsing LIVE dot, floating chips) — decorative only.

**Hover / press.** Buttons lift on hover (translateY, no color change for primary; ghost shifts border to indigo-400). Cards lift + gain shadow + brand border. Press is implicit (no aggressive shrink). Focus: 3px indigo ring (`--ring`) — accessibility is taken seriously (WCAG focus-visible rings, aria labels in source).

**Transparency & blur.** Sticky marketing nav uses `backdrop-filter: blur(14px)` over translucent white. Light buttons on dark use `rgba(255,255,255,.12)`. Otherwise surfaces are opaque.

**Imagery vibe.** No stock photos in the product. Visual interest comes from the gradient, emoji, and the live "AI call" chat-card mock. Cool/violet palette overall, warm only in the success-green and emoji accents.

---

## ICONOGRAPHY

Three layers, used together:
1. **Emoji — primary & most-used.** Emoji are the brand's de-facto icon set: nav items, quick actions, section headers, niche tags, buttons. They carry tone, not just meaning. Always available, no asset needed. (See CONTENT FUNDAMENTALS.)
2. **Lucide (line icons)** for marketing feature tiles and some UI — stroke ~2.2, indigo `#4f46e5`, sat in a soft indigo well (`#eef0ff`, radius 14px). The production site loads Lucide via CDN and uses `data-lucide="mic|search|send|…"`. The website UI kit does the same. **Substitution note:** Lucide is linked from CDN (`unpkg.com/lucide`) — it matches the product's own usage.
3. **The logo mark** (`assets/logo-mark.svg`) — a white phone handset + AI voice waves + sound-bars on the indigo gradient, 112px-radius squircle. Used as the app icon and sidebar/nav brand mark. Wordmark "LeadGen AI" in Plus Jakarta Sans 800.

Do **not** hand-draw new SVG icons. Reach for emoji first, Lucide second, the logo mark for branding.

---

## INDEX / MANIFEST

**Root**
- `styles.css` — global entry (consumers link this one file; `@import`s the tokens).
- `readme.md` — this guide.
- `SKILL.md` — Agent-Skill wrapper.
- `assets/logo-mark.svg` — brand mark.

**Tokens** (`tokens/`, all `@import`ed by `styles.css`)
- `fonts.css` · `colors.css` · `typography.css` · `spacing.css` · `effects.css`

**Components** (`window.LeadGenAIDesignSystem_f15a99`)
- `components/core/` — `Button`, `Eyebrow`, `Avatar`, `Card`
- `components/data/` — `StatCard`, `Badge` (status + lead temperature), `Tag` (niche)
- `components/forms/` — `Field`, `Select`
- `components/feedback/` — `Modal`, `Toast` (+ `ToastProvider`/`useToast`), `Tooltip`, `Skeleton`, `EmptyState`
- `components/navigation/` — `Tabs`, `DropdownMenu`, `Pagination`

**UI kits** (`ui_kits/`)
- `dashboard-marketing/` — **AI Marketing** customer dashboard (daily posts, approval queue, Google audit, posters, reach)
- `dashboard-voice/` — **AI Voice Agent** customer dashboard (live Hot/Warm/Cold leads, calls + transcripts, appointments, team routing)
- `dashboard-combo/` — **Combo** customer dashboard for the combo SKU: one shell with a product switcher that toggles between the Marketing and Voice bodies
- `admin/` — **admin console** (operator/team view: all clients, AI agent fleet, MRR, campaigns)
- `auth/` — **auth flow** (login, signup, OTP, forgot-password, magic-link) — split-screen
- `onboarding/` — **Add Customer wizard** (4-step: product → business → plan → done)
- `website/` — leadsgenai.in marketing landing page
- `_shared/` — shared sidebar/topbar/panel shell used by both customer dashboards

**Foundation cards** (`guidelines/`) — specimen cards for the Design System tab (Type, Colors, Spacing, Brand).
