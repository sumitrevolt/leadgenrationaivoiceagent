# Stage 2 — Primary Restoration

Goal: turn the chosen primary screen comp into a working product that **looks and reads like the chosen design**, not "inspired by" it. High-fidelity is the default — always load `references/high-fidelity-assets.md` alongside this file.

## Tell the user the time estimate first

Before you start restoring the chosen screen into runnable code, tell the user — in plain language and in their own conversation language — that turning the design into a working version that runs in the browser is expected to take **about 15–30 minutes**. Phrase it as an estimate (e.g. "around 15–30 minutes" / "around 15–30 minutes"). Do not use the words "stage", "phase", or any internal step numbers.

## The six rules

1. **Restore the chosen primary screen.** This means the comp the user picked in stage 1. Focus on this single screen first — additional pages come in stage 3 if the user requests them.
   - **Restore the product page, not presentation chrome.** Do not assume the stage-1 comp is always a display board. If the chosen comp uses a board / canvas presentation — for example a solid-color backdrop with one centered scaled-down mockup, surrounding margins, or "showcase" framing — treat that backdrop, margin, frame, fixed canvas ratio, and centered-card staging as presentation chrome and strip it away. Restore only the inner page as a real, full-bleed responsive web page. If the comp itself is already a full-bleed page, cropped page detail, multi-screen layout, or another open presentation, restore the page content exactly as presented; there is no canvas to strip. The final product must be a usable responsive page, not a fixed-ratio showcase frame or display-board background.

2. **Copy is 1:1.** All visible text — headlines, subheads, body copy, button labels, form placeholders, microcopy, footer text — matches the comp word-for-word. Do not paraphrase, "improve", or translate unless the comp itself is in another language. If the comp's text is in Korean / Japanese / English, the implementation uses that exact language. When the text is hard to read, OCR the image or ask the user. Never invent.

3. **Generate the assets that actually need a generator.** Use `create-image` for **complex backgrounds, guidance material, and page material images**: hero illustrations, photographic / painterly backgrounds, character art, product shots, scene art, onboarding visuals, empty-state illustrations, flow arrows / annotations, product mockups, OG share images, and any decorative raster with real pictorial content. Do **not** use the generator for things that are not "real images": flat icons (use SVG), simple geometric shapes (use CSS / SVG), solid color blocks, gradients, dividers, basic UI chrome.
   - Use the picked stage-1 comp as the style reference for generated assets: pass it via `edit_image` with `image_path="/path/to/comp.png"` in each `images[i]`. This keeps generated imagery tied to the user's selected direction instead of drifting into a new style.
   - Do **not** pass `use_styles` or `use_picture` for these generated assets — both are workflow intent flags reserved for stage-1 style directions and stage-3 page comps respectively. Ordinary assets, component images, illustrations, and supporting artwork must omit both.
   - Save raw renders to `verdent-design/stage3/source-renders/`.
   - Save final wired-in versions to `verdent-design/images/` with names like `{module}-{purpose}.{ext}` (e.g. `hero-background.png`, `pricing-card-illustration.png`, `onboarding-guide-step-1.png`).
   - Every comp asset that qualifies as a "real image" must be generated before restoration is complete.
   - If an asset carries the design's style — not just content — recreate that style carrier. Do not replace a branded illustration, texture, product mockup, or guide visual with a plain CSS block.

4. **Implement implied interactions and motion.** Hover, focus, active, transitions, modal open/close, tab switching, accordion, navigation, form validation — anything the comp visually implies a state for. The restored product must not feel like a static screenshot.

5. **No emoji by default.** Do not add emoji to UI copy, feature labels, buttons, empty states, notifications, or status chips unless the approved comp or the user explicitly includes emoji. Use SVG icons, typography, color, illustration, and motion for personality.

6. **High-fidelity layout & color (hard rule).** The comp is the single source of truth; redesign is forbidden.
   - **Layout:** section order, column ratios, key element positions match the comp; do not add/remove sections.
   - **Color:** sample every color from the comp (brand, surface layers, text layers, accent, chart colors) and write them into the Tailwind v4 `@theme` block. Do **not** leak framework default palettes — no shadcn neutral grays, no Tailwind blue-500 default, no recharts/chart.js default colors. Light/dark base tone follows the comp; do not "improve contrast" by inventing greys.
   - **Type & spacing:** display/body sizes, weights, line-heights, section padding, card gutters follow the comp's proportions. No default framework scales.
   - **Self-check:** before reporting done, view the restored screen side-by-side with the comp (browser + comp image) and confirm the three points above.

## Hero / first-screen height

The hero (above-the-fold first screen) must not be artificially tall. A common AI failure mode is to make the hero `min-h-screen` or 900px+ "for impact" — this pushes the next section out of view, hurts scannability, and feels generic.

- **Default cap: hero is ~70–85vh on desktop**, never `100vh` unless the comp explicitly shows a fullscreen takeover with no content below the fold.
- The next section (features / social proof / product preview) **must start being visible** before the user scrolls — at least a hint (10–15vh) should peek under the hero on a 1440×900 viewport.
- Use `min-height` with a **vh cap** (e.g. `min-h-[680px] lg:min-h-[78vh]`), not a hardcoded huge value. On short laptop screens the hero must not eat the entire viewport.
- If the comp shows the hero as ~1 viewport tall **with the next section already visible**, replicate that ratio. Measure proportions against the comp, not against your own instinct.
- On mobile the hero may take more vertical space, but still leave the second section's title peeking on a 390×844 viewport.
- Vertical rhythm of the rest of the page also matters: each section ~480–720px on desktop, never two sections stacked back-to-back without breathing room, never one module padded to fake length.

## Motion restoration

A faithful frontend is animated at the points the design implies. Add motion deliberately, not as decoration.

- **Page entry:** hero content, primary CTA, and main visual should enter with style-appropriate timing unless the product is intentionally static.
- **Scroll reveal:** marketing / landing sections should reveal as they enter the viewport when that matches the comp's premium or editorial feel.
- **State feedback:** buttons, cards, nav items, form fields, tabs, modals, drawers, menus, and accordions need hover / focus / active / open / close states.
- **Style match:** luxury / finance motion is slow and restrained; tools are fast and clear; playful brands can be springier.
- **No cheap motion:** do not add random bounce, shake, sparkle, confetti, or emoji animation just to prove animation exists.
- **Accessibility:** respect `prefers-reduced-motion` for non-essential motion.

Use `framer-motion` for choreographed entry / scroll-linked motion implied by the comp. Use CSS transitions for simple hover/focus states. Do not pull in GSAP unless the comp is timeline-heavy.

## Default tech stack (web)

Unless the user has already declared a stack, or the project genuinely needs SSR / heavy routing / CMS, **default to `Vite + React + TypeScript + Tailwind`**. Do not deliberate, do not present a menu — pick this and move. Builders hire AI to make this call.

**Scaffold (exact commands):**

Use the bundled first-preview template. It already contains Vite + React + TS + Tailwind v4, `@/` alias, fixed-px Tailwind breakpoints, `framer-motion`, `react-router-dom`, a hand-authored `public/favicon.svg`, and no default Vite clutter.

```bash
rsync -a ~/.verdent/skills/design-then-build/templates/vite-react-tailwind/ ./
npm install
```

Fallback only if the template is missing:

```bash
# Vite scaffold may refuse to write into a non-empty dir; scaffold to a temp folder and move in.
npx --yes create-vite@latest temp-scaffold --template react-ts
mv temp-scaffold/* temp-scaffold/.* . 2>/dev/null; rm -rf temp-scaffold
npm install
npm install -D tailwindcss @tailwindcss/vite        # Tailwind v4 — no postcss/autoprefixer config
npm install framer-motion react-router-dom
```

Install dependencies in one pass from the template. Do not run multiple `npm install` commands unless the first install fails or the user changes stack. In `vite.config.ts` use the Tailwind plugin, and in your root CSS file use `@import "tailwindcss";` (v4 syntax — **no `tailwind.config.js`, no `@tailwind base/components/utilities`**).

**Best practices to apply on every restoration:**

- **TypeScript strict on.** Don't downgrade to JS to "save time"; the comp doesn't care, but future iteration does.
- **Path alias `@/` → `src/`** in both `vite.config.ts` (`resolve.alias`) and `tsconfig.json` (`paths`). Avoid `../../../` import chains.
- **One section per file** under `src/sections/` (Hero, Features, Pricing, CTA, Footer). Page composes them. Don't dump everything in `App.tsx`.
- **Tailwind tokens, not arbitrary values everywhere.** Define brand colors / fonts in CSS via `@theme { --color-brand: …; --font-display: …; }` (v4 way) so the design system is centralized.
- **Fonts via `<link rel="preconnect">` + `display=swap`.** Self-host only if the comp brand demands it.
- **Images:** generated assets live in `verdent-design/images/`. In JSX use `width`/`height` attributes (prevent CLS) and `loading="lazy"` for everything below the fold. Hero image `fetchpriority="high"`.
- **Animations:** `framer-motion` for choreographed entry / scroll-linked motion implied by the comp. Pure CSS `transition` for hover/focus. Don't pull in GSAP unless the comp is timeline-heavy. Always respect `prefers-reduced-motion`.
- **Icons as SVG components** (`src/icons/*.tsx` or inline). Never raster icons. Never `create-image` for icons. Flat single-color icons use `currentColor` so they inherit the surrounding text color.
- **Favicon:** create a hand-authored `public/favicon.svg` for every web restoration and reference it from `index.html` as `/favicon.svg`. It belongs to final asset pass, not the first preview gate.
- **No emoji substitution:** emoji must not replace icons, bullets, status marks, empty-state art, or brand personality unless the comp/user explicitly requires it.
- **No `any`, no unused imports, no `console.log` left in.** Run `tsc --noEmit` before reporting complete.
- **Accessibility floor:** semantic `<header>/<nav>/<main>/<footer>/<section>`, `alt` on every `<img>`, focus-visible rings preserved, color contrast ≥ AA on body text.

**When to deviate (only these reasons count):**

| Trigger | Switch to |
|---|---|
| User explicitly named a stack ("use Next.js" / "Astro" / "plain HTML") | Their stack. Don't argue. |
| Content site / blog / SEO-critical landing with marketing pages | `Astro` (islands; less JS shipped) or `Next.js` (if they also want app routes). |
| The project is an actual app with auth / DB / API routes | `Next.js` App Router. |
| Canvas / WebGL focus | Vite + React still fine, or vanilla TS + Vite if React adds nothing. |

If none of these triggers fire, **use the default and move on**. Listing alternatives "for transparency" wastes the user's time.

## Verdent parallel setup

This skill runs inside Verdent agent. Use `create_image` / `edit_image` tool calls for image generation, and reserve `bash_background` for the long-running dev server only.

After the user picks a comp:

1. Start essential raster generation with `create_image` / `edit_image` tool calls first: hero / background image and at most 1 supporting raster asset. Do not generate logo raster or below-the-fold thumbnails before first preview.
2. In the main thread, copy the frontend template, install dependencies, write tokens, and build the page structure.
3. After dependencies install, start `npm run dev` with `bash_background` and keep it running. Do not wait until TypeScript or production build passes to start the dev server.
4. When the hero generation finishes, copy the result into `public/` or `verdent-design/images/` and wire it. If it is not ready when the page is otherwise previewable, use a styled CSS / SVG placeholder and open first preview anyway.

Main agent owns code, layout, tokens, and component structure. Do not use subagents to edit core source files (`src/App.tsx`, `src/index.css`, `src/sections/*`) before first preview. Background work is for image generation and dev server only.

Do not poll background image generation repeatedly. Continue frontend work, then check the background result once when the page is ready to wire assets.

## First preview gate

Goal: get the user's first look quickly. First preview is not "restoration complete" — it is an early review checkpoint.

After scaffolding and installing dependencies, start the dev server early and keep it running. Use it for first preview as soon as the page renders. Do not wait for production build before first preview; production build belongs to final validation.

As soon as the chosen primary screen is runnable and visually coherent on desktop, open the preview for the user. This first preview only requires:

- The dev server runs without a blank screen.
- The primary screen's main layout, colors, type, and key assets are in place.
- The desktop view is close enough for direction review.
- Obvious broken states are fixed.

Do not satisfy final-completion requirements before opening first preview unless they are cheap and already done. Do not run full 360 / 768 / 1440 responsive verification before first preview. Basic mobile CSS should not be intentionally broken, but full responsive verification belongs to the final gate.

Asset budget before first preview:

- Generate only assets that dominate the primary screen above the fold, usually the hero / background image and no more than 1–2 essential raster assets.
- For first preview, use a hand-authored SVG/text wordmark by default. Do not generate logo raster images before first preview unless the approved comp is primarily a logo/brand mark study.
- Do not block first preview on below-the-fold card thumbnails, secondary illustrations, logo variants, favicon, OG images, or `assets/MANIFEST.md`.
- Use styled CSS / SVG placeholders for non-essential raster assets, then replace them during final QA.
- If multiple raster assets are needed after first preview, generate them in parallel where the tool/runtime supports it. Never serially generate below-the-fold assets before first preview.

Tell the user plainly:

> "The homepage is ready for a first look. I opened it for you now. I'll keep checking mobile, responsiveness, and visual details while you review the overall direction."

Then continue responsive QA, visual fixes, asset checks, production build, and final validation. Do not ask whether to design other pages until the final gate below passes.

## Responsive (non-negotiable)

The implementation **must** work on mobile. This is not a stage-4 follow-up.

- **Three breakpoints minimum:** mobile ≤640px, tablet 641–1024px, desktop ≥1025px.
- **Mobile-first CSS.** Base styles for mobile, layer up with `min-width` media queries / Tailwind `md:` `lg:` modifiers.
- **No horizontal scroll** at viewport widths 360, 414, 768, 1024, 1440. Verify by setting these viewport widths.
- **Touch targets ≥44×44px** on mobile.
- **Navigation collapses appropriately** (hamburger / bottom nav / drawer) when the desktop nav doesn't fit.
- **Type scales down sensibly** — desktop `text-6xl` heroes become readable mobile sizes, not unscaled overflows.
- **Images responsive** — `width:100%; height:auto`, `object-fit`, or Next.js `<Image>` with `sizes`. No fixed-pixel images that break the layout.
- **Tables / wide content** get a horizontal-scroll container or a stacked-card variant on mobile.
- **Canvas projects:** scale the canvas via `devicePixelRatio` and viewport, support touch input where mouse/keyboard was assumed.

Before asking to continue with more pages, verify responsiveness — either by running the project and checking at the three breakpoints, or by walking the CSS / component tree and confirming each section has explicit responsive rules. State the verification method in the response.

## Final gate (before asking to continue)

Run through this checklist after the first preview. All rules that say "before reporting complete" apply to this final gate, not to the first preview gate. If any answer is "no", finish before asking the user whether to continue with more pages.

- [ ] The chosen primary screen comp restored?
- [ ] Every visible text 1:1 with the comp?
- [ ] Every "real image" asset (complex backgrounds / guidance material / page materials) generated and named correctly? (Icons & geometric shapes excluded.)
- [ ] Interactions and motion wired (entry, hover, focus, active, modals, tabs, transitions, validation, reduced-motion fallback)?
- [ ] No emoji added unless explicitly present in the comp or requested by the user?
- [ ] Responsive at 360 / 768 / 1440?
- [ ] Every icon as SVG? `public/favicon.svg` created and referenced from `index.html` as `/favicon.svg`? Every logo has both solid and alpha versions? `assets/MANIFEST.md` written?

**After passing the checklist**, tell the user responsive and visual QA is complete, then ask:

> "The primary screen is complete. Do you want to continue designing other related pages for this product?"

- **Yes** → proceed to stage 3 (extended-pages).
- **No** → skip to stage 4 (continued-build).

## Common mistakes

| Mistake | Why it fails | Fix |
|---|---|---|
| Not fully restoring the primary screen | The user expects a complete, usable primary screen before deciding on additional pages. | Restore the full primary screen before reporting stage 2 complete. |
| Paraphrasing / "improving" comp copy | Implementation no longer matches what the user approved. | 1:1 copy. OCR or ask if unclear. |
| Using the image generator for icons | Hallucinated strokes and stray pixels. | Hand-author SVG with matching stroke weight and `currentColor` for single-color icons. |
| Replacing visual design with emoji | Looks generic, breaks fidelity, and makes the product feel unserious. | Use SVG icons, typography, color, illustration, and motion instead. |
| Restoring presentation chrome as part of the page | When the chosen comp uses a board / canvas presentation, shipping the solid backdrop, side margins, fixed ratio, or centered showcase card makes the product look like a staged mockup instead of the real site. | Only strip board / canvas chrome when it exists. Restore the actual page as a full-bleed responsive product, and do not carry over showcase framing, display-board background, or fixed canvas proportions. |
| Leaving the page static | A screenshot-like page feels unfinished and misses implied UI states. | Add entry, hover, focus, active, open/close, and reduced-motion-aware transitions. |
| Dropping guidance visuals / style-carrying assets | The restored page loses the approved style even if layout is close. | Generate or rebuild onboarding visuals, product mockups, empty states, textures, and annotations. |
| Hard-coded pixel widths | Breaks mobile and 4K. | Mobile-first, three breakpoints. |
| Treating responsive as a later task | Product is unusable on phones until then. | Verify responsiveness before this stage is "done". |
| Reporting complete without `ls` verification | Missing files surface only when the user opens the app. | `ls` `verdent-design/images/`, `verdent-design/icons/`, `verdent-design/logo/` and confirm before reporting. |
| Asking the user "Vite or Next.js?" for a static landing page | Burns trust; they hired AI to make this call. | Default to Vite + React + TS + Tailwind. Only deviate for the triggers in "When to deviate". |
| Using Tailwind v3 syntax (`tailwind.config.js`, `@tailwind base;`) on a v4 install | Build breaks or styles don't apply. | v4: `@import "tailwindcss";` + `@theme` block. No JS config needed. |
| Raster icons via `create-image` | Hallucinated strokes, blurry at scale. | Hand-author SVG components. |
| Using subagents to edit core source before first preview | Causes conflicts and context drift. | Main agent owns code; use `create_image` / `edit_image` tool calls for image generation and `bash_background` only for the dev server. |
| Waiting synchronously for hero image before building frontend | Wastes setup time. | Start hero generation with `create_image` / `edit_image` tool call, then build the page shell. |
| Running `npm create vite@latest .` in an existing project dir | Scaffold refuses or aborts ("Operation cancelled"). | Use the bundled template first; fallback scaffold into `temp-scaffold/` then `mv` contents. |
