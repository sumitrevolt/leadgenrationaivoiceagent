---
name: leadgenai-design
description: Use this skill to generate well-branded interfaces and assets for LeadGen AI (leadsgenai.in) — an AI Automated Marketing + AI Voice Agent product for Indian local businesses — either for production or throwaway prototypes/mocks. Contains design guidelines, colors, type, fonts, assets, and UI kit components for prototyping. Brand voice is Hinglish (Romanized Hindi + English), indigo→violet, emoji-forward.
user-invocable: true
---

Read the `readme.md` file within this skill, and explore the other available files.

If creating visual artifacts (slides, mocks, throwaway prototypes, etc), copy assets out and create static HTML files for the user to view. If working on production code, you can copy assets and read the rules here to become an expert in designing with this brand.

If the user invokes this skill without any other guidance, ask them what they want to build or design, ask some questions, and act as an expert designer who outputs HTML artifacts _or_ production code, depending on the need.

## Quick orientation
- **Tokens:** `styles.css` → `tokens/*.css`. Link `styles.css` and use the CSS custom properties (`--grad-brand`, `--brand`, `--hot/--warm/--cold`, `--font-display`, etc).
- **Components:** React primitives in `components/` — `Button`, `Eyebrow`, `Avatar`, `Card`, `StatCard`, `Badge`, `Tag`, `Field`, `Select`. Each has a `.prompt.md` with usage.
- **UI kits:** `ui_kits/dashboard-marketing/` (AI Marketing customer), `ui_kits/dashboard-voice/` (AI Voice Agent customer), `ui_kits/dashboard-combo/` (both-products switcher), `ui_kits/admin/` (operator console), `ui_kits/website/` (marketing site). Full recreations to copy from. The customer dashboards share `ui_kits/_shared/shell.jsx`; combo reuses the marketing + voice bodies.
- **Assets:** `assets/logo-mark.svg`.

## Non-negotiable brand rules
1. **Write copy in Hinglish** — Romanized Hindi mixed with English, addressing the owner as "aap". (e.g. "Aapko sirf HOT leads".)
2. **Use the indigo→violet gradient** on primary CTAs / brand moments; deep-violet sidebar in the app.
3. **Emoji are part of the design** — use them for nav, actions, niches, headers. Don't strip them.
4. **Plus Jakarta Sans (800, tight)** for headings, **Inter** for body.
5. Lead scoring uses the **Hot / Warm / Cold** color scale. Indian ₹ currency and conventions.
