# High Fidelity Asset Pipeline

Run **always** during restoration (stage 2 and stage 3). This aims to restore as much visual detail as possible, though pixel-level identical results are not guaranteed due to technical constraints. This is **in addition to** the rules in `references/restoration.md` — every step here is mandatory.

## Image assets

### Generation priority and budget

Asset generation is expensive and slow — be deliberate. Order and cap as follows:

1. **Before first preview, generate only the primary hero / main banner image if it is essential.**
   - **Primary hero / main banner image** — the single largest visual on the primary screen (hero background, hero illustration, or hero product shot). Save under `verdent-design/images/hero-*.{png,jpg,webp}`.
   - Use a hand-authored SVG/text wordmark for first preview unless the approved comp is primarily a logo/brand mark study.
2. **Before the final gate, complete the full asset pass:**
   - **Logo** — the brand logo, in the variants the page actually uses (full lockup, mark, alpha cutout). Save under `verdent-design/logo/`.
   - **Primary hero / main banner image** — if not already generated before first preview.
3. **Then generate up to 5 more supporting assets**, picked by visual weight:
   - Section banners, feature illustrations, product mockups, large empty-state visuals, OG share image, secondary photographic backgrounds.
   - Rank candidates by the area they occupy and how strongly they carry the brand style. Generate the top 5; **drop everything below the cut**.
4. **Hard cap depends on page type:**
   - **Image-heavy pages** (gallery / showcase / portfolio / e-commerce grid / lookbook / template library — pages whose value *is* a wall of similar images): logo set + 1 hero + **5 supporting is the absolute cap. Do not ask the user.** If the comp shows 30 product cards, generate the 5 most prominent and reuse / variate them across the rest. Repetition is fine for this page type.
   - **Visually composed pages** (the page is built from many distinct visual elements, and removing any one of them breaks the design — e.g. a landing page where the hero, the floating product card, the illustrated character, the data chart preview, the testimonial portrait, the section background, and the footer banner are all *different* assets that each carry a specific role): logo set + 1 hero + 5 supporting is the soft cap. If the page genuinely needs more **non-substitutable** assets to look correct, stop and ask the user before exceeding the cap. "Non-substitutable" means: cannot be reused as a duplicate, cannot be replaced by CSS / shapes, and the page would visibly look wrong without it.
5. **For everything else, use code substitutes:** CSS gradients, solid color blocks, simple geometric shapes via CSS, or repeating an already-generated asset. **Do not use SVG as a substitute for raster artwork** — SVG is reserved for flat single-color icons (see "Icons" below). Hand-authoring SVG illustrations, patterns, or scenes hallucinates strokes, weights, and detail; the result looks generic and off-brand. If a decorative element needs real pictorial content and missed the cap, drop it or simplify to a CSS shape.
6. Record the chosen budget in `assets/MANIFEST.md` so the next stage knows what was intentionally skipped.

### Generation rules

1. **Identify every raster asset** used in the page: hero, illustrations, photos, backgrounds, guidance visuals, empty states, product mockups, annotations, decorative shapes that are not pure CSS.
2. **Regenerate each asset via the `create-image` skill** using the design comp as reference, **with the text removed**. Text is rebuilt in code, never baked into the asset — otherwise typos and translations require a re-render. Do **not** pass `use_styles` or `use_picture` for these asset images — both are workflow intent flags reserved for stage-1 style directions and stage-3 page comps respectively.
   - **Exception — the asset itself is a UI / interface screenshot.** When the asset shown in the comp is a product screenshot, app interface, dashboard preview, phone mockup, browser window, code editor, etc., the UI text inside that screenshot **is part of the artwork, not page copy**. Keep the text. Treat the whole UI as a single image asset and extract it intact, including its labels, menus, charts, code, chat bubbles, data, etc. Do **not** try to rebuild that interface in HTML — it lives in the page as one image. Only the page's own copy outside the screenshot follows the "remove text, rebuild in code" rule.
   - Heuristic: if removing the text would make the asset meaningless (a blank dashboard, an empty phone, a featureless code block) → keep the text and extract as-is. If removing the text leaves a usable illustration / photo / background → strip text and rebuild in code.
3. **Preserve original aspect ratio and pixel dimensions** implied by the layout.
4. **Right-angled assets only.** No pre-baked rounded corners. Rounding is applied in CSS / view code, not in the asset. This keeps the same asset reusable across components with different corner radii.
5. **Naming:** `{module}-{purpose}-{variant?}.{ext}` — e.g. `hero-background.png`, `pricing-card-illustration.png`, `dashboard-chart-overview.png`. Names must be readable and grep-able.

## Icons

- Only **flat, solid-color icons** in the design qualify here.
- **Export as SVG**, not PNG/JPG/WebP. Hand-author the SVG using `<path>`, `<rect>`, etc. Do not use the image generator to "draw" an icon — it hallucinates strokes, weights, and pixel artifacts.
- Single-color icons should use `fill="currentColor"` or `stroke="currentColor"` so the icon inherits text color.
- Match stroke width, cap, join, corner radius, and optical size from the comp.
- Verify clarity at 16 / 20 / 24 / 32px. If it blurs or weight shifts, fix the SVG, not the CSS.
- Naming: `icon-{name}.svg` under `verdent-design/icons/`.

## Cutouts and background removal

Use this when a subject must be layered independently: transparent logos, people, products, devices, stickers, foreground hero subjects, or any asset that crosses layout backgrounds.

1. **Prefer source layers first.** If Figma/source design is available, export the original layer. Export vectors as SVG; do not rasterize a vector and then cut it out.
2. **Use a dedicated cutout/background-removal model or tool before asking a general image model to invent transparency.** General generators often produce fake checkerboard backgrounds, halos, or damaged edges.
3. **For generated subjects, create a clean subject render first, then remove the background deterministically** with a dedicated remover, `rembg`, ImageMagick masking, or manual mask cleanup.
4. **Preserve natural shadows only when they are part of the intended layered asset.** Otherwise recreate shadows in CSS so they respond to layout and theme.
5. **Inspect every cutout on dark, light, and brand-colored backgrounds** before wiring it into the app.

Bugcases to actively check:

- Fake transparency: checkerboard pattern baked into the PNG.
- White/black halo around logos or product edges.
- Hair, fur, glass, smoke, or semi-transparent fabric destroyed by the mask.
- Subject edges eaten away, especially fingers, cables, handles, and thin strokes.
- Background leftovers in holes or concave shapes.
- Shadow removed so the subject looks like a sticker, or shadow baked so it clashes with CSS lighting.

Save cutouts under `verdent-design/images/` or `verdent-design/logo/` with `-alpha` / `-cutout` suffixes when useful, and list them in `assets/MANIFEST.md`.

## Logo (two artifacts per logo)

The logo gets special treatment because it appears at every size and on every background.

### 1. High-resolution solid-background logo
- Generate a clean, high-res version based on the original logo.
- If the logo is a **lockup with wordmark/text**, export the mark and the text together as one image.
- Solid background using the brand's intended background color.

### 2. Alpha-transparent logo
- Produce a version with a **true transparent background**.
- **Do not** use the image generator to "make" the transparent version — the generator hallucinates edges and halos around the mark.
- Instead: take the solid-background logo and remove the background **deterministically**:
  - ImageMagick: `convert solid.png -fuzz 5% -transparent "#FFFFFF" alpha.png`
  - `rembg` if available
  - Manual masking for tricky marks
- Save as PNG with alpha, or SVG when the mark is geometric.

Save under `verdent-design/logo/`.

## Asset manifest

Write `assets/MANIFEST.md` listing every exported asset:

```markdown
# Asset Manifest

## Images
| File | Source comp | Purpose |
|---|---|---|
| `verdent-design/images/hero-background.png` | `verdent-design/stage1/comp-2-editorial.png` | Landing hero background |
| `verdent-design/images/pricing-card-illustration.png` | `verdent-design/stage2/pages/page-3-pricing.png` | Pricing card decorative art |

## Icons
| File | Source | Purpose |
|---|---|---|
| `verdent-design/icons/icon-arrow-right.svg` | hand-authored from `comp-2` | CTA button arrow |

## Logo
| File | Background | Purpose |
|---|---|---|
| `verdent-design/logo/logo-solid.png` | `#0A0A0A` | Print, dark headers |
| `verdent-design/logo/logo-alpha.png` | transparent | Inline use over arbitrary backgrounds |
```

This is what a developer or designer will read in stage 4 and beyond to wire assets correctly.

## Common mistakes

| Mistake | Why it fails | Fix |
|---|---|---|
| Baking text into asset images | Typos, translations, A/B copy require a re-render. | Remove text in `edit` prompts; rebuild text in code. |
| Pre-baked rounded corners | Asset can't be reused at a different corner radius. | Right-angled assets; round in CSS. |
| Using generator for the transparent logo | Halos and hallucinated edges around the mark. | Generate solid-bg, remove background deterministically. |
| Rasterizing a Figma vector and then cutting it out | Loses crisp edges and creates avoidable cleanup work. | Export vectors as SVG directly from Figma/source. |
| Accepting fake transparency | Checkerboard or matte color gets baked into the app. | Inspect alpha on dark, light, and brand backgrounds. |
| Ignoring cutout edge bugcases | Hair, glass, thin strokes, and product holes look broken in the final UI. | Run the cutout checklist before wiring assets. |
| Generic asset names like `bg1.png`, `image2.png` | Cannot find or grep; cross-referencing in code is painful. | `{module}-{purpose}-{variant}.ext`. |
| Skipping `MANIFEST.md` | Assets become orphaned; nobody knows where they came from. | Write the manifest before reporting HF complete. |
