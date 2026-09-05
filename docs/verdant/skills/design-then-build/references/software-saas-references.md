# Software / SaaS reference anchors

When the product is a **software / SaaS landing page** (or any UI product whose visual quality bar is set by sites like Stripe / Linear / Notion / Vercel / Framer / Obvious / Arc / Raycast), pure text-to-image `create_image` reliably produces generic "AI imagined SaaS" comps. The fix is **reference anchoring**: every comp is an `edit_image` remix of a real, hand-picked landing page screenshot.

This file is loaded by `references/style-exploration.md` whenever the brief is software-class.

## When this applies

Apply reference-anchored mode if **any** is true:
- The product is a SaaS / dev tool / AI agent / productivity app / B2B platform.
- The user explicitly references a site (`like Linear`, `obvious.ai`, `Stripe-style`, etc.).
- The brief requires "premium / editorial / Stripe-level / Notion-level" quality.

Skip (use normal `create_image`) only for: games, consumer mobile apps with no web equivalent, content sites (news, magazine, blog), e-commerce.

## Hard rules (override `style-exploration.md` defaults for software class)

1. **Use `edit_image` with `use_styles=true`, not `create_image`.** Each generated comp is anchored to one real reference screenshot. Default stage 1 uses 4 comps; if the user explicitly asks for 1–4 style directions, use that requested count.
2. **Collect references first.** Before any image call, secure 4 reference screenshots (one per direction). Either:
   - User-provided URL/screenshot (preferred) — fetch via `web_fetch` or read provided file.
   - Manager/worker-supplied references in the prompt.
   - If user gave none, ask: "Pick 1–4 sites you like (Linear, Stripe, Obvious, Vercel, Framer, Notion, Arc, Raycast, etc.), or I'll choose high-bar references for you." Wait or pick canonical references matching the style count.
   - Save all references to `<project-root>/design/stage0-references/` with descriptive names (`ref-1-obvious-ai.png`, etc.). Always keep them — stage 2 reads them.
3. **One reference → one comp.** Never blend multiple refs into one prompt. Each comp must be traceable to exactly one source.
4. **Edit prompt must specify, in this order:**
   - The product name + one-line product description (so headlines/copy fit the actual product).
   - **Preserve from reference:** layout skeleton, section order, hero composition pattern, type scale rhythm, image placement.
   - **Replace from reference:** all copy → product-relevant English; product screenshot → product-relevant dashboard mock; logos → product logo + 6 plausible customer wordmarks.
   - **New token system (concrete, no abstract words):**
     - background hex, text hex, accent hex (one accent only)
     - font family class (e.g. "Inter / Söhne-style geometric sans", "Tiempos-style serif")
     - hero size (e.g. "70vh, not full-screen"), nav height (64px), max content width (1200px)
   - **Forbidden:** no abstract style words alone (`clean`, `modern`, `editorial`, `premium`) without a concrete token next to them.
5. **Output is still a 9:16 brand display board** per `style-exploration.md` canvas rules — solid background, mockup at 65–75% width, ~3 viewports tall. The reference defines the *interior* of the mockup, not the canvas framing.
6. **Diversity contract for multiple comps.** When generating 2–4 comps, the references must collectively span at least three of:
   - color temperature (warm / cool / neutral)
   - background lightness (dark / light / mid)
   - typography mood (geometric sans / humanist sans / serif-led / mono-led)
   - composition (centered text + product / split / floating UI / browser frame)
   - decoration density (zero-decoration vs subtle texture/illustration)

## Canonical software-class reference shortlist

Use these when the user does not name sites. Pick references that span the diversity axes above.

| # | Site | Visual DNA in one line |
|---|---|---|
| 1 | obvious.ai | Warm off-white + deep green CTA + oversized centered editorial display + landscape backdrop dashboard. |
| 2 | linear.app | Near-black + violet/blue subtle gradients + dense geometric sans + product UI floats. |
| 3 | stripe.com | White → soft gradient + Söhne-style sans + dual-color brand bands + dense product-illustration hero. |
| 4 | vercel.com | Pure black/white + monospace accents + sharp grid + minimal color, type does the work. |
| 5 | notion.so | Soft white + serif headlines + warm illustrated mascots + content-density blocks. |
| 6 | framer.com | High-contrast dark + electric accent + oversized motion-implying display + floating UI cards. |
| 7 | arc.net | Cream + warm color blocks + oversized handwritten-feel display + playful product photography. |
| 8 | raycast.com | Pure dark + red accent + tight monospace + keyboard-shortcut motifs throughout. |

Always cite which reference each comp is anchored to in the user-facing presentation:
> Comp 1 — Ink & Amber, anchored to obvious.ai's editorial display + landscape dashboard pattern.

## Mini-spec per comp (mandatory)

Every comp returned to the user is paired with this 6-field micro-spec:

```
Comp N — {direction name}
  Anchor:      {reference site}
  Background:  #XXXXXX
  Text:        #XXXXXX
  Accent:      #XXXXXX
  Typography:  {family or family-class}
  Composition: {one of centered-text+product / split / floating UI / browser frame}
```

This forces concrete commitments and gives stage-2 restoration unambiguous tokens.

## Failure modes specific to software class

| Mistake | Why it fails | Fix |
|---|---|---|
| Using `create_image` with abstract style words | Produces "AI-imagined SaaS" — generic, immediately spotted. | Use `edit_image` against a real reference. |
| Multiple comps anchored to the same reference | Differences become palette-only; user has no real choice. | Each comp from a different reference; for 2–4 comps, span ≥3 diversity axes where possible. |
| Blending 2+ references into one prompt | Layout breaks; loses the source's coherence. | One ref → one comp. |
| Skipping the mini-spec | Stage 2 has to re-invent tokens; restoration drifts. | Always include the 6-field spec block. |
| Copying the reference's exact copy / brand | Looks like a clone, not a redesign. | Rewrite all copy/logos to fit the user's product. |
| Forgetting the 9:16 display-board canvas | Output reads as a screenshot, not a brand comp. | Canvas rules from `style-exploration.md` still apply. |
