# Stage 1 — Style Exploration

Goal: give the user **default four genuinely different design directions** for the product's primary screen (landing hero / app home / etc.) so they can pick a direction with confidence. If the user explicitly asks for 1–4 style directions, use that requested count.

## Tell the user the time estimate first

Before you start generating the design directions, tell the user — in plain language and in their own conversation language — that producing the design directions is expected to take **about 5–10 minutes**. Phrase it as an estimate (e.g. "around 5–10 minutes" / "around 5–10 minutes"). Do not use the words "stage", "phase", or any internal step numbers.

## Hard rules

1. **Image-only.** Do not write any HTML, CSS, JS, JSX, scaffolding, or component code in this stage. The deliverables are 4 PNG files plus a one-line rationale per comp. The user has not picked a direction yet — code is a bet on an unconfirmed design and gets thrown away.
2. **Exactly 4 comps.** Not 1, not 2, not 5. Four is enough contrast for a confident pick, not so many that the user freezes.
3. **Distinct layout languages, not just different palettes.** Vary at least three of: grid system, typographic scale, asymmetry vs symmetry, image-to-text ratio, motion-implied composition, decorative system, **and how the comp is presented (full-bleed vs board vs cropped detail)**. Diversity of *presentation* counts as much as diversity of *style* — multiple comps that all use the identical centered-board framing read as one template even with different palettes.
4. **A real UI design comp, never just promotional artwork.** Each comp must be a genuine app/web user-interface mockup that follows standard UI conventions — navigation/header, clear information hierarchy, real interactive components (buttons, inputs, cards, lists, tables, tabs, etc.), and real content blocks. The comp must not be only a poster, banner, splash screen, or pure brand key-visual with no real interface structure. Bold hero layouts are strongly welcome: the hero may use oversized type, highly decorative typography, expressive composition, and strong visual impact. The constraint is on the whole comp, not the hero's layout language — as a whole, it must still read like a usable product interface with real UI structure around or beyond the hero, not a detached promotional asset.
5. **Match the user's product type without cramming every feature.** When the user states what they are building (e.g. an e-commerce app, a creator marketplace for uploading and selling designs, a dashboard, a SaaS site), the comp must show the key modules or primary view that make the product type recognizable — e.g. e-commerce needs a product/listing/pricing entry; a creator marketplace needs a focused upload or selling flow glimpse. A beautiful hero alone is not enough, but the comp must NOT pack every product feature, panel, metric, and data block into one screen. Real products usually focus a single screen on one primary task or view.

6. **Senior-design-director taste.** Reject AI defaults: purple→blue gradients, generic glassmorphism cards, AI-stock illustrations, emoji-as-icon.
7. **Each prompt specifies** subject, composition, type system, a *named* color system (not "modern"), and what to avoid. Texture/material, lighting, and era/movement are optional — add them only when they truly serve that direction; never force an era reference onto every comp (it flattens diversity). See `examples/comp-prompt.md`.
8. Use `create_image` when no references are supplied. Use `edit_image` when the user supplies references or when `software-saas-references.md` selects reference-anchored mode.
9. **Emit one image tool call with `use_styles=true`; set `n` to the style count and provide an `images` array with the same number of elements.** The style count must stay within 1–4. Default stage 1 uses `n=4`; if the user explicitly asks for 1–4 style directions, use that requested count. Use `create_image` for no-reference style exploration, or `edit_image` for reference-anchored style exploration. Each element has its own `prompt`, `title`, and `palettes`; `edit_image` items also include `image_path`. The tool generates the comps concurrently from this one call. See `examples/comp-prompt.md` for the full no-reference batch format.

10. **Each comp commits to one three-color palette in both places.** Give each direction a clear `[background, primary/ink, accent]` color system of 3 `#RRGGBB` values. Pass those colors through each element's `palettes` for workflow metadata, and express the same colors directly in that element's prompt body. The palette is just 1 main color + 2 supporting colors. Keep the three colors clearly different from each other — no other constraints. Do not rely only on the separate `palettes` parameter; the image model must also see the hex values and usage instructions in the prompt text itself. This palette is a coloring instruction — how the interface is colored — and may only appear through the actual colors of UI elements such as background, text, buttons, cards, and accents. Absolutely do NOT render the palette itself anywhere in the generated image: not inside the UI, not in display-board whitespace, not along canvas edges, not in outer margins around the design, and not beside the mockup. No color swatches, color chips, swatch strips, palette legends, sample color blocks, hex value labels, or any other visible palette reference may appear anywhere in the image. A common violation is placing three vertical color blocks with hex labels on the right side / side edge of the canvas and pretending it is "outside the interface" — this is still forbidden. The palette is used through UI colors, not drawn or labeled.

## Presentation (presentation is a variable, not a fixed template)

You are acting as a world-class digital product design director. There is **no fixed framing**. Choose the composition and presentation that flatters each direction. Forcing multiple comps into the identical framing is the #1 cause of comps that "all look the same with different colors."

**Vary the presentation across multiple comps** — when generating 2–4 comps, use at least two clearly different presentation modes so they never read as one template. How you present each comp is entirely free: pick whatever flatters that direction. The presentation mode is an open creative choice, not a menu. For example (not an exhaustive list): a **display board** (scaled-down mockup on a clean solid backdrop), a **full-bleed** page filling the frame edge-to-edge, a **cropped detail** zooming the hero + one key section, multi-screen layouts, grid showcases, or any other mode that suits the direction.

**Present the whole comp flat and front-on (a straight 2D design comp). Do not tilt, rotate, or place the entire comp in 3D space / on a device-in-space mockup, and do not frame it as a product-shot.** This constrains only how the comp as a whole is presented — it does NOT restrict the design *inside* the page. Perspective, depth, 3D objects, product imagery, shadows, and other visual richness within the page content are all fair game; let the design direction decide.

Whatever presentation you choose, the page design *inside* it must follow the quality rules below. Composition, proportion, framing, margins, and how much of the page you show are all free creative choices — let the design direction decide.

**Page design quality:**
- Realistic UI conventions for the product type (web, app, mobile, dashboard, etc.); clear information hierarchy; generous breathing room between modules.
- Practice restrained content density. One screen should focus on **one primary task / one primary view**. Real websites, apps, and clients do not stack a dozen feature modules into one frame; they use whitespace, clear hierarchy, and pagination / split views / tabs to organize information. A dashboard or admin product does NOT mean every panel, chart, statistic strip, and table belongs on the same screen — real dashboards still leave breathing room and emphasize 1–2 main regions while secondary information is tucked away or paginated. As guidance, a primary screen usually needs only **3–5 major modules** to explain the product; fewer, better-resolved modules feel more credible than an overfilled control panel. If content is heavy, first reduce same-screen module count or split the view, instead of squeezing everything into one screen and compressing density.
- Each section keeps a sensible height; no two modules crammed together.
- Internal proportions must stay realistic. Never compress sections, type, images, cards, or the footer to fit. If something doesn't fit, scale the whole design down — do not squash its parts.
- Images, product screenshots, cards, avatars, and icons must never look stretched or distorted.
- Footer stays clean, simple, and real — never sloppy because space ran out.
- If content is heavy, reduce detail count, **never** reduce module height.

**Output goal:**
- Convey overall style, brand feel, type rhythm, and core page structure.
- Small body text does not need to be fully legible.
- The whole image must read like a real, high-quality product interface / UI design comp (a website, web app, mobile app, dashboard, etc. — whatever the product is).

## Saving outputs

Copy the returned images into `<project-root>/verdent-design/stage1/` with names `comp-1-{style}.png` … `comp-N-{style}.png`, where `N` is the generated style count. Keep the original `create-image` output files untouched; do not rely on the global `create-image` cache as the only copy.

## Presenting to the user

Show the comps with **one short design rationale each** — what era, what taste, who it's for. Do not pick a "winner" yourself. Let the user choose.

Use plain language. Do not say "stage 1" or "phase 1" to the user.

**Model recommendation (Executes only after all style generation `create_image` tool calls complete)** When you generate the comps and invite the user to choose one, also include a short recommendation that they use **the most capable Claude Opus model currently available in the app** for development, so the frontend maintains high fidelity to the design mockups. Write this recommendation in the user's own language (match the language they are using in the conversation). Keep it to one friendly sentence, e.g. "We suggest using the most capable Claude Opus model currently available in the app for development to ensure the frontend fully matches the design mockups with high fidelity."

## Skip condition

If the user's prompt already contains a detailed product design plan and style spec (concrete style direction, palette, type system, page list or screen flow), skip this stage and go straight to stage 2 with the user's brief as the chosen direction. Tell the user the brief is already specific enough to move forward directly.

## Gate

**Do not proceed to stage 2 until the user picks one comp.**

If the user does not explicitly choose, ask them.

## Common mistakes

| Mistake | Why it fails | Fix |
|---|---|---|
| Reducing the default style count "to save time" without user request | The user cannot pick a direction without contrast. | Default to 4; only use 1–4 when the user explicitly asks for that count. |
| Four palette variants of the same layout | The user picks based on layout / taste, not color. Same layout = no real choice. | Vary layout language across at least three axes. |
| Making the whole comp a poster / brand key-visual instead of a usable UI | Looks flashy but is not a real product interface and cannot guide development. | Follow app/web UI conventions: navigation + real components + content blocks, tied to the user's stated product features. The hero can be bold, oversized, and highly expressive; only the overall comp must remain a usable interface. |
| Missing a clear per-comp palette | Comps read as anonymous images with no distinct color system. | Commit each comp to one `[background, primary/ink, accent]` palette of three `#RRGGBB` values. |
| Rendering the palette as visible swatches / color chips / a swatch strip anywhere in the image, including outside the interface, in board margins, or along the canvas edge; especially placing three vertical color blocks with hex labels on the side of the canvas | Real product interfaces do not display sample color blocks or hex labels; that is internal design-tool information, and moving it outside the UI still leaks the palette into the generated image. | Express the palette only through the actual colors of UI elements — background, text, buttons, and accents. No swatch, color chip, palette legend, sample block, or hex label appears anywhere in the image. |
| Writing scaffolding code "to save time later" | Direction may change. Code is wasted. | Image-only until the user picks. |
| Saying "phase 1" to the user | Confuses non-technical builders. | "I'll show you four directions to pick from." |
| Describing multiple styles in one prompt | Collages styles, repeats one layout, or loses style-card alignment. | Emit one image tool call with `use_styles=true`, `n` set to the style count, and an `images` array with the same number of elements — each with its own `prompt`, `title`, `palettes`; use `edit_image` with `image_path` when reference-anchored. |
| Palettes lack contrast across the four cards | Cards no longer communicate four distinct directions. | Aim for four distinct `[background, primary/ink, accent]` palettes with varied backgrounds. |
| Packing every product feature / panel / data block into one screen (over-dense "everything on one screen" control-panel cramming) | Real products do not work this way; it looks crowded, distorted, and untrustworthy, and the hierarchy gets buried. | Focus one screen on one primary task / primary view, with 3–5 major modules. Use whitespace plus pagination / split views / tabs for secondary information; dashboards also need breathing room and a clear main region. |
| Generated directions all read as the same design family | Variants of one family (e.g. multiple flavors of minimalism) give the user no real choice. | Spread the generated comps across clearly different directions (e.g. Minimalism / Futuristic Tech / Japanese editorial / Swiss / Brutalist / Memphis / Y2K / Skeuomorphic / Hand-drawn), or any other genuinely contrasting set. |
| Picking a winner for the user | The user's taste is the point of this stage. | Present neutrally. They choose. |
| Missing stage copies | Stage 2 cannot find inputs; user cannot review. | Always copy into `verdent-design/stage1/`, keep the original `create-image` outputs untouched, then `ls` to verify. |
| Multiple comps use the identical framing | Same presentation = comps read as one template with palette swaps. | For 2–4 comps, vary presentation: use at least two of display-board / full-bleed / cropped across the set. |
| Compressing footer / sections to fit | Footer looks sloppy; hierarchy collapses. | Scale the whole design down instead. Reduce detail count, not module height. |
