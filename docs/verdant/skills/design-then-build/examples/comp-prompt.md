# Example: Stage 1 Style-Comp Prompt

A complete, copy-pasteable prompt for the `create-image` skill covering all seven required elements for stage-1 style exploration.

Adapt the placeholders to the specific brief. Covering these dimensions is recommended — leaving one fully unspecified tends to let the model drift toward its default aesthetic. The one exception is `REFERENCE ERA / MOVEMENT`, which is **optional**: only include it when a specific direction genuinely calls for an era anchor, and leave it out for modern / futuristic / clean / neutral directions.

> **Note:** the typefaces, brands, and product references in the filled example below are illustrative — they show how a senior designer makes each dimension concrete. Replace them with whatever fits the actual brief. The **structure** is what matters; the specific names are not prescriptive. If a direction does not need an era anchor, omit the `REFERENCE ERA / MOVEMENT` line entirely.

## Template

> **Placeholder note:** The values inside `{curly braces}` are only illustrations of how to make each dimension concrete — they are **NOT recommended defaults**. Replace them freely to fit the direction.

```json
// create_image tool call — single style direction (use as one element in the `images` array)
{
  "n": 1,
  "use_styles": true,
  "images": [
    {
      "prompt": "SUBJECT: The primary screen of a {one-line product description} ({a landing page, app home, dashboard, mobile screen, etc. — whatever the product is}); primary action is {CTA verb + object}.\n\nCOMPOSITION: {grid system, e.g. 'asymmetric two-column 60/40 with text left, oversized type leaking off the right edge'}.\n{type-to-image ratio, e.g. '70% type, 30% image'}.\n{decorative system, e.g. 'one large halftone hero illustration; one style-carrying guidance visual or product mockup; thin horizontal rule under the wordmark; a single oversized arabic numeral as page indicator'}.\n\nTYPE SYSTEM: Headline in {named typeface, e.g. 'Söhne Breit'} at {size, e.g. '110pt'}, very tight tracking ({-2%}).\nBody in {named typeface, e.g. 'Söhne'} at 18pt, neutral leading.\nSmall caps for section labels at 11pt, +8% tracking.\n\nCOLOR SYSTEM: Use the same exact colors here that you also pass through `palettes`.\nBackground {named color, e.g. 'warm off-white #F4F1EA'} for the page canvas and broad surfaces.\nPrimary / ink {named color, e.g. 'ink black #0A0A0A'} for headline, body text, and core UI chrome.\nAccent {named color, e.g. 'cadmium red #C9301C'} used only on CTA + page numeral.\nThese colors are instructions for coloring UI elements; do not draw color swatches, color chips, a swatch strip, palette samples, or hex labels anywhere in the image, including outside the UI, in display-board whitespace, outer margins, or along canvas edges. The colors should appear only through actual UI usage.\nNo gradients. No purple-to-blue.\n\nTEXTURE / MATERIAL: {e.g. 'matte newsprint paper texture, very subtle grain, no glossy surfaces'}.\n\nLIGHTING: {e.g. 'flat editorial lighting, no glow, no rim light, no AI bokeh'}.\n\nREFERENCE ERA / MOVEMENT (OPTIONAL): {e.g. 'only if this direction truly needs a historical or movement anchor; otherwise omit this line'}. Only add an era/movement reference when that specific direction genuinely calls for it. Do NOT put an era anchor on every comp — forcing era references flattens diversity and tends to make everything look retro/vintage. Many strong directions (modern minimal, futuristic, clean editorial, neutral product UI) need NO era reference at all; leave this line out entirely for those.\n\nAVOID (these are high-frequency AI defaults — steer clear unless a direction deliberately calls for one): purple-to-blue or teal-to-pink gradients; AI-stock illustrations; faceless silhouette people; emoji-as-icon; glassmorphism; uniform corner rounding on every element; same padding rhythm in every section; no color swatch strip or hex labels anywhere in the image, including outside the UI / canvas margins.",
      "title": "{direction name}",
      "palettes": ["#bg", "#ink", "#accent"]
    }
  ]
}
```

## Filled example (contemporary focused direction for a productivity SaaS)

```json
// create_image tool call — single style direction example
{
  "n": 1,
  "use_styles": true,
  "images": [
    {
      "prompt": "SUBJECT: Landing-page hero for a calm, focused note-taking app for academics; primary action is 'Start writing'.\n\nCOMPOSITION: Asymmetric two-column 60/40 grid, text left, oversized lowercase wordmark leaking 12% off the right edge.\n75% type, 25% image.\nA single thin horizontal rule under the navigation; a large arabic numeral '01' as section anchor in the bottom-left margin.\nOne small manuscript-card product mockup shows the note style without turning into a generic app screenshot.\n\nTYPE SYSTEM: Headline in 'Geist' at 112pt, tracking -2%, weight Medium. Geist is the choice because the brief asks for contemporary focus, precision, and calm.\nBody in 'Inter' at 17pt, leading 1.5.\nSection labels in small caps 'Inter' at 10pt, tracking +10%.\n\nCOLOR SYSTEM: Background warm cream #F2EEE5. Primary ink #111111. Accent oxblood #6B1F1F used only on CTA and the '01' numeral. No gradients. Do not show swatches, palette blocks, or hex labels anywhere in the image, including outside the interface, board margins, or canvas edges.\n\nTEXTURE / MATERIAL: Soft matte interface surface with a barely visible fine grain. Nothing glossy.\n\nLIGHTING: Flat editorial lighting. No glow, no bokeh, no AI rim light.\n\nThis direction does not need an era anchor, so the optional REFERENCE ERA / MOVEMENT line is intentionally omitted. NOT Notion, NOT Linear, NOT generic SaaS.\n\nAVOID (these are high-frequency AI defaults — steer clear unless a direction deliberately calls for one): purple-to-blue / teal-to-pink gradients; AI-stock illustrations; faceless silhouettes; emoji-as-icon; glassmorphism cards; uniform corner rounding; same padding rhythm across sections; no visible palette swatches or hex labels anywhere in the image, including outside the UI / canvas margins.",
      "title": "Contemporary Focus",
      "palettes": ["#F2EEE5", "#111111", "#6B1F1F"]
    }
  ]
}
```

## Why each section matters

| Section | Why it matters |
|---|---|
| SUBJECT | Without a concrete primary action, the model defaults to "tech homepage with a screenshot". |
| COMPOSITION | Forces a layout-language commitment, which is the variable that has to differ across the 4 comps (more than color does). |
| TYPE SYSTEM | Naming actual typefaces removes the model's tendency to pick Inter / Helvetica by default. |
| COLOR SYSTEM | Named colors with a purpose (background / primary / accent + where it appears) prevents AI-default gradients. The specified colors are for coloring interface elements; do not draw color swatches, color chips, swatch strips, palette samples, or hex value labels anywhere in the image, including outside the UI, board margins, or canvas edges. Colors should appear only through actual UI usage. |
| TEXTURE / MATERIAL | Differentiates "real material" from "vector flat" — the difference between an editorial comp and a Dribbble shot. |
| LIGHTING | Cuts off AI bokeh / rim-light defaults that scream "AI-generated". |
| REFERENCE ERA / MOVEMENT | **Optional. Only when it truly serves the direction.** Do NOT add an era anchor to every comp — forcing era references flattens diversity and tends to make everything look retro/vintage. Many strong directions (modern minimal, futuristic, clean editorial, neutral product UI) need NO era reference at all. |
| AVOID | Common AI defaults tend to drift back in unless explicitly named — listing them steers the model away from its most predictable fallbacks. |

## Filled example (no-reference `create_image` batch call for stage-1 exploration)

> **Important**: The four styles below (Minimal Luxe / Futuristic Tech / Editorial / Warm Friendly) are ONE illustrative combination — not a required set. Pick four directions that fit the actual brief (see `references/style-exploration.md`). What matters is that the four chosen styles, layouts, and palettes have strong contrast so the user has a real choice.
>
> Adapt `SUBJECT` and `PAGE STRUCTURE` to match the actual product type — for an app, dashboard, or mobile screen, describe the relevant functional screen and its structure rather than defaulting to a landing-page layout. Be restrained when describing product-function screens: choose only the key modules needed to explain the product identity, not every feature, panel, or data block in the product; real products use whitespace and pagination / split views to organize information.
>
> Emit a single `create_image` tool call only when no reference images are used. For reference-anchored exploration, emit the same `use_styles=true` style-count flow via `edit_image`, with one `image_path` per item. Default stage 1 uses `n=4`; if the user explicitly asks for 1–4 style directions, set `n` and the `images` array length to that requested count. Each item has its own `prompt`, `title`, and `palettes`.
>
> This example set is intentionally contemporary-first: only one of the four directions uses an explicit era / retro anchor. Retro is an optional minority choice, not the default. Do not attach an era to every direction; doing so pulls all comps toward vintage and flattens stylistic diversity.

```json
// create_image tool call — 4 style directions in one batch
{
  "n": 4,
  "use_styles": true,
  "images": [
    {
      "prompt": "Output one independent design comp (one cohesive page, not a collage or comparison wall).\n\nSUBJECT: Landing-page hero for a calm, focused note-taking app for academics; primary action is 'Start writing'.\nPAGE STRUCTURE: Nav with wordmark; hero with headline + sub + CTA; 1 product-glimpse module; 1 social-proof or feature module; clean footer.\n\nSTYLE: MINIMAL LUXE — contemporary restrained minimalism.\nSuggested anchor: contemporary product minimalism with oversized whitespace, precise alignment, quiet premium restraint, and a refined sans-serif voice. No historical era anchor.\nLean away from: neon glow, HUD lines, dense multi-column grids, organic blobs.\nComponents: one oversized hero title, one hairline divider, one small product screenshot card.\nLayout: vast whitespace, symmetric vertical-centered single-column grid.\nColor: a calm warm-cream background (around #F5F3EE), near-black ink (around #1A1A1A) for text, and a muted taupe accent (around #9C8B6E) on the CTA. Keep it restrained — a dominant background with a single small accent reads well here.\nType: Söhne / Helvetica Neue ultra-light, large hero title.\nAvoid: garish neon, dense columns, heavy dark backgrounds (unless the direction genuinely calls for it).",
      "title": "Minimal Luxe",
      "palettes": ["#F5F3EE", "#1A1A1A", "#9C8B6E"]
    },
    {
      "prompt": "Output one independent design comp (one cohesive page, not a collage or comparison wall).\n\nSUBJECT: Landing-page hero for a calm, focused note-taking app for academics; primary action is 'Start writing'.\nPAGE STRUCTURE: Nav with wordmark; hero with headline + sub + CTA; 1 product-glimpse module; 1 social-proof or feature module; clean footer.\n\nSTYLE: FUTURISTIC TECH — contemporary dark SaaS / data-interface direction.\nSuggested anchor: current high-contrast dark product interfaces, precise telemetry, restrained HUD language, angular framing, and machine-like clarity. No Y2K or retro-futurist styling.\nLean away from: beige paper texture, warm friendly illustration.\nComponents: one sharp hero statement, one luminous product frame, one compact telemetry strip.\nLayout: asymmetrical interface architecture with directional panels and hard-edged alignment, on a deep background.\nColor: a deep near-black blue background (around #0A0E1A), pale ice-blue text (around #E8F4FF), and a cyan glow accent (around #00F0FF). The accent can carry larger glowing areas if it serves the look.\nType: condensed techno sans, uppercase labels, hard hierarchy.\nAvoid: beige paper mood, warm-friendly illustration.",
      "title": "Futuristic Tech",
      "palettes": ["#0A0E1A", "#E8F4FF", "#00F0FF"]
    },
    {
      "prompt": "Output one independent design comp (one cohesive page, not a collage or comparison wall).\n\nSUBJECT: Landing-page hero for a calm, focused note-taking app for academics; primary action is 'Start writing'.\nPAGE STRUCTURE: Nav with wordmark; hero with headline + sub + CTA; 1 product-glimpse module; 1 social-proof or feature module; clean footer.\n\nSTYLE: EDITORIAL / SWISS — contemporary editorial product direction.\nSuggested anchor: rigorous modern editorial grids, disciplined type hierarchy, dense but readable information rhythm, and confident contemporary sans typography. No historical designer or era anchor.\nLean away from: neon glow, glass cards, sparse hero-only layout.\nComponents: one commanding headline block, one disciplined image column, one pull-quote or chapter marker.\nLayout: dense modular grid with multiple aligned columns and visible editorial rhythm.\nColor: a clean white field (around #FFFFFF), near-black ink (around #111111) for text, and a strong red accent (around #C8102E) on a pull-quote marker or chapter number.\nType: Helvetica Neue / Akzidenz-Grotesk with disciplined scale contrast and baseline rhythm.\nAvoid: neon glow, glass cards, soft organic composition.",
      "title": "Editorial Grid",
      "palettes": ["#FFFFFF", "#111111", "#C8102E"]
    },
    {
      "prompt": "Output one independent design comp (one cohesive page, not a collage or comparison wall).\n\nSUBJECT: Landing-page hero for a calm, focused note-taking app for academics; primary action is 'Start writing'.\nPAGE STRUCTURE: Nav with wordmark; hero with headline + sub + CTA; 1 product-glimpse module; 1 social-proof or feature module; clean footer.\n\nSTYLE: WARM FRIENDLY / MEMPHIS — warm friendly / Memphis direction.\nSuggested anchor: Ettore Sottsass / Memphis Group 1981-87 / 2020s friendly SaaS illustration. Warm optimism, playful geometry, approachable energy.\nLean away from: monochrome severity, cold chrome, dark backgrounds.\nComponents: one welcoming hero title, one rounded product card, one small spot illustration or CTA.\nLayout: buoyant composition with soft offsets and friendly shapes.\nColor: a warm cream background (around #FBE9D0), warm dark-brown ink (around #3D2A1F) for text, and an orange accent (around #E07A3C) on the CTA or a spot illustration. Feel free to bring in more warmth if it suits the direction.\nType: warm geometric sans with friendly proportions and relaxed rhythm.\nAvoid: monochrome severity, cold chrome, dark backgrounds.",
      "title": "Warm Friendly",
      "palettes": ["#FBE9D0", "#3D2A1F", "#E07A3C"]
    }
  ]
}
```
