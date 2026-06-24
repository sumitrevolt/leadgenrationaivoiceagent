---
name: design-review
description: LeadGen ke frontend/UI surfaces ka visual-craft + AI-slop review — generic AI-design catch, spacing/hierarchy/contrast, mobile-380px + dark, accessibility, CTA visual-clarity. Use jab koi frontend/HTML/CSS/landing/mini-site/admin-dashboard change ho, "design dekho", "UI review", "page acchi lag rahi?", "mobile pe toota", "AI-generated jaisa lag raha", ya ship se pehle koi visible page touch hui ho. Conversion STRATEGY = conversion-optimization/cro; yeh skill VISUAL EXECUTION + slop-catch ke liye hai.
---

# Design Review (visual craft + AI-slop catch)

Solo dev = koi designer nahi → khud ki UI ko 6 ALAG design-lens se dekho. **GUESS mat karo — preview-tools se ACTUALLY dekho** (screenshot/resize/inspect), warna review jhootha hai. Output: `file:line + issue + fix`, Critical/High pehle.

## Pehle: kya review karna hai (LeadGen surfaces)
- **Public (conversion-critical):** `/audit` `/site-audit` (#1-2 lead magnets) · `/demo` · `/compare` · `/pricing` · `/start` · `/blog` · `/b/{slug}` per-client mini-sites · widget embed. Source: `frontend/*.html`.
- **App/admin:** `/app/marketing` (28 tabs) · `/app/automation` Mission Control · admin dashboards · `/app/customer`.
- **AI-image outputs:** Pollinations posters/og-images (`app/marketing/ai_image.py`) — generic/garbled to nahi.

## Dekhne ka tareeka (preview-tools, mat-guess)
1. `preview_start` → page kholo. `preview_screenshot` = desktop baseline.
2. `preview_resize` **380px (mobile-first India)** + dark-mode → screenshot. LeadGen audience mostly mobile/slow-network.
3. `preview_snapshot` = structure/content. `preview_inspect` = exact CSS (spacing/contrast values), aankh se mat aandaazo.
4. Frontend change hua to `python scripts/check_html_js.py` bhi.

## 6 Lenses (har ek alag pass)

### 1. AI-slop catch 🤖 (gstack ka core)
Generic-AI-design ke tell-tale signs hunt karo: purple/indigo gradient-soup, emoji-bullet spam (✨🚀💡), lorem-ipsum/placeholder ("Your Company"), **fake stats/testimonials** (invented numbers = trust + legal risk), "As an AI"/TODO leftover, do-teen alag font/button-style ek page pe, center-aligned everything. Real, specific, LeadGen-brand copy hona chahiye.

### 2. Visual craft 🎨
Spacing rhythm consistent (4/8px scale, random margins nahi) · alignment grid · clear hierarchy (ek H1, scannable) · color/token consistency (hardcoded hex bikhre to nahi) · button/card states (hover/active/disabled) defined.

### 3. Responsive + dark 📱
380px pe: horizontal-scroll/overflow nahi, text readable (≥14px), tap-targets ≥44px, tables/28-tabs collapse sahi. Dark-mode: contrast tehre, invisible-on-dark text nahi. (LeadGen mobile + dark dono serve karta.)

### 4. Accessibility ♿
Text contrast ≥4.5:1 (`preview_inspect` se verify) · `<img alt>` · form `<label>`/aria · keyboard focus visible · color-alone se meaning nahi.

### 5. Conversion-craft (visual) 🎯
*Yeh `conversion-optimization`/`cro` se ALAG — woh funnel/copy strategy; yeh visual execution.* Primary CTA above-fold + visually-dominant (ek primary, rest secondary) · trust-signals (legal links, real proof) visible · form-friction (kam fields, error inline) · `/audit`+`/pricing`+`/start` pe value-prop 5-sec me clear.

### 6. Brand consistency 🧩
marketing.html ↔ mini-sites ↔ admin ek family lagein (same palette/logo/tone) · Hinglish copy consistent · DO products (Marketing vs Voice) ka framing sahi (mix nahi — `product-split-adr`).

## Output
`## Critical (toota/trust-risk)` · `## High (craft/conversion)` · `## Consider (polish)` — har item `frontend/file:line + issue + fix`. Critical+High fix → re-screenshot proof → ship via `leadgen-ops`. Pure UX/funnel strategy chahiye to `conversion-optimization`.

Adapted from garrytan/gstack `design-review` / `design-shotgun` methodology (MIT) — ported as a LeadGen markdown skill (no Bun/TS dep; uses LeadGen's own Claude Preview tools).
