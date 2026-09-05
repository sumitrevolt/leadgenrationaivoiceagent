---
name: create-image
description: |
  Generate and edit images via the `create_image` and `edit_image` tools.
  Use this skill whenever the user asks for image generation, image editing
  based on reference images, posters, illustrations, covers, UI mocks,
  social creatives, or style variations.
metadata:
  version: '2.2.3'
---

# Create Image

Single skill for generating and editing images through the `create_image` and `edit_image` tools. Call these tools directly — no bash commands needed.

## When to Use

Invoke this skill whenever the user wants to:

- generate a brand-new image from a description
- edit an existing image with a reference image
- produce posters, illustrations, hero images, covers, social creatives, UI mock visuals, or stylistic variants
- regenerate an image with changed style, composition, subject, or palette

Do **not** use this skill to analyze or describe an existing image. Use a vision-capable read path instead.

## Tool Call Shape

Two tools are available:

- `create_image` — generate new images from prompts
- `edit_image` — edit/transform based on a reference image

### `create_image`

```json
{
  "n": 1,
  "images": [
    {
      "prompt": "A cyberpunk cat on a rain-soaked rooftop at night",
      "size": "1024x1024",
      "background": "opaque",
      "moderation": "auto",
      "output_compression": 100,
      "output_format": "png"
    }
  ]
}
```

Top-level parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `n` | integer | **yes** | 1–4, must equal `images` array length |
| `images` | array | **yes** | Array of image generation items |
| `use_styles` | boolean | no | Style selection mode. `n` and `images.length` must match and stay within 1–4. Mutually exclusive with `use_picture` |
| `use_picture` | boolean | no | Picture mode. Mutually exclusive with `use_styles` |

`images[i]` item parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | **yes** | Non-empty generation instruction |
| `size` | string | no | `"<w>x<h>"` or `"auto"`. Default `"1024x1024"` |
| `background` | string | no | `"opaque"` / `"transparent"` / `"auto"` |
| `moderation` | string | no | `"low"` or `"auto"` |
| `output_compression` | integer | no | 0–100 |
| `output_format` | string | no | `"png"` / `"jpeg"` / `"webp"` |
| `title` | string | no | Only allowed when `use_styles=true` or `use_picture=true` |
| `palettes` | string[] | no | `#hex` color array, only allowed when `use_styles=true` |

### `edit_image`

```json
{
  "n": 1,
  "images": [
    {
      "prompt": "Recolor with warm tones, add subtle film grain",
      "image_path": "/absolute/path/to/source.png"
    }
  ]
}
```

Top-level parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `n` | integer | **yes** | 1–4, must equal `images` array length |
| `images` | array | **yes** | Array of edit items |
| `use_styles` | boolean | no | Style selection mode. `n` and `images.length` must match and stay within 1–4. Mutually exclusive with `use_picture` |
| `use_picture` | boolean | no | Picture mode. Mutually exclusive with `use_styles` |

`images[i]` item parameters:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `prompt` | string | **yes** | Non-empty edit instruction |
| `image_path` | string | **yes** | Absolute path to the source image |
| `mask` | string | no | Absolute path to an Alpha-channel mask image |
| `size` | string | no | `"<w>x<h>"` or `"auto"` |
| `background` | string | no | `"opaque"` / `"transparent"` / `"auto"` |
| `moderation` | string | no | `"low"` or `"auto"` |
| `output_compression` | integer | no | 0–100 (must be `number`, not string) |
| `output_format` | string | no | `"png"` / `"jpeg"` / `"webp"` |
| `title` | string | no | Only allowed when `use_styles=true` or `use_picture=true` |
| `palettes` | string[] | no | `#hex` color array, only allowed when `use_styles=true` |

### Key Differences

| | `create_image` | `edit_image` |
|--|--|--|
| Unique item params | none | `image_path` (required), `mask` |
| Shared top-level intent flags | `use_styles`, `use_picture` | `use_styles`, `use_picture` |
| `title` restriction | requires `use_styles` or `use_picture` | requires `use_styles` or `use_picture` |
| Integer compat | accepts string `"3"` | `number` only |
| Partial failure format | JSON `warnings` array | text prefix `Partial failures:` |

### Intent Flags

`use_picture` and `use_styles` are workflow intent markers supported by both `create_image` and `edit_image`. Omit both for ordinary asset generation, including material images, component images, illustrations, supporting artwork, photos, covers, social creatives, product shots, hero art, backgrounds, icons, and any other standalone image.

- `use_styles=true` — style-option generation mode. Use whenever generating style direction images that the user compares and chooses from. `n` and `images.length` must match and stay within 1–4. Each `images[i]` must include `title` and `palettes`. Mutually exclusive with `use_picture`.
- `use_picture=true` — complete-design-comp output mode. Use only when generating full page/screen design comps for user review before implementation. In `design-then-build` stage 3, use this on `edit_image` with the selected comp as `image_path`. Each `images[i]` must include `title`. Mutually exclusive with `use_styles`.
- `title` is bound to `use_styles` or `use_picture` on both tools. Never pass `title` without one of these flags.

### Execution Model

Each `images[i]` item spawns an independent generation process (fixed `n=1` per item). All items run concurrently via `Promise.all`. Partial failures are reported without blocking successful results.

## Prompt Authoring Rules

- **Do not parrot the user verbatim.** Translate intent into an image prompt: subject, composition, style, color, lighting, framing, camera or medium, quality cues when relevant.
- **Do not over-invent.** Preserve every concrete requirement the user gave (subject, scene, palette, aspect ratio, characters, text overlays, product details). Do not add subjects, brands, or style shifts the user never asked for.
- Keep the prompt focused and sentence-like.
- Write the prompt in English by default. Match another language only if the user's creative explicitly requires it (for example, on-image text in that language).

### Multiple Images and Style Variations

- Use `n` + multiple `images` items for distinct prompts. Each item can have its own `prompt`, `size`, `background`, `output_format`, etc.
- For same-subject variations sharing one visual brief, use `n=1` per item and vary only the style-specific language in each `images[i].prompt`.
- When the user asks for multiple styles, variations, directions, or options, generate separate standalone images. Do **not** write prompts that ask for a grid, collage, split-screen, contact sheet, comparison board, panels, quadrants, tiles, or "four styles in one image" unless the user explicitly requests a single combined layout.
- Correct: `{ "n": 1, "images": [{ "prompt": "A minimalist ceramic teapot product poster, soft studio lighting, calm neutral palette" }] }`
- Wrong: `{ "n": 1, "images": [{ "prompt": "Create four different styles of a ceramic teapot poster, divided into four panels" }] }`
- For distinct named styles that must each be represented exactly once, use `n` equal to the style count and create one `images[i]` per style, each with its own prompt.

## Reference Images Rules

Only applies to `edit_image`:

- `image_path` takes an **absolute file path**, not a URL and not base64.
- When the user dragged in or `@mentioned` images, use those exact paths as provided. Do not invent, rename, or summarize them.
- `mask` is optional. Use it only when the user provides or asks to use a mask image.
- A mask uses its Alpha channel to control the local edit region. Areas outside the mask should be preserved as much as possible.

## Output Handling

### `create_image` output

**Normal / picture mode success:**

```json
{
  "status": "ok",
  "operation": "generate",
  "count": 2,
  "images": [
    { "path": "/abs/path.png", "image_media_type": "image/png", "size": "1024x1024", "quality": null, "title": "optional" }
  ],
  "warnings": ["images[1]: exited with code 1"]
}
```

- `warnings` only present on partial failure.

**Style mode success** (`use_styles=true`):

```json
{
  "status": "ok",
  "styles": [
    { "id": "style-1", "title": "Style 1", "path": "/abs/path.png", "palette": ["#hex"], "image_media_type": "image/png", "size": null, "quality": null }
  ]
}
```

**Full failure:** `{ content: "error message", is_error: true }`

### `edit_image` output

**Success:**

```json
{
  "status": "ok",
  "operation": "edit",
  "count": 1,
  "images": [
    { "path": "/abs/path.png", "image_media_type": "image/png", "size": null, "quality": null, "title": "optional" }
  ]
}
```

**Partial failure:** Output is prefixed with `Partial failures:\nimages[1] failed: ...\n\n`

**Full failure:** `{ content: "error message", is_error: true }`

### Save directories

| Context | Directory |
|---------|-----------|
| Default (worker or global usage) | `~/.verdent/generate_images` |
| When invoked inside the Verdent manager or base workspace | `<project-root>/verdent-design` |

## End-to-End Patterns

### Pattern 1. Simple generation

User asks for a cyberpunk cat illustration.

```json
// create_image tool call
{
  "n": 1,
  "images": [
    {
      "prompt": "A cyberpunk cat sitting on a rain-soaked rooftop at night, neon signs reflecting in puddles, cinematic lighting, shallow depth of field, high detail",
      "size": "1024x1024"
    }
  ]
}
```

Then tell the user the image was generated and show the saved path from the tool result.

### Pattern 2. Photorealistic product shot

User wants a glossy red apple product photo.

```json
// create_image tool call
{
  "n": 1,
  "images": [
    {
      "prompt": "A giant gleaming red apple, hyper-realistic, dewdrops on glossy skin, vibrant saturated red with subtle yellow highlights, fresh green leaf still attached to the stem, dramatic studio lighting on pure white background, ultra detailed macro photography, 8k quality",
      "size": "1024x1024"
    }
  ]
}
```

### Pattern 3. Full design comp for user review before build

User wants a complete SaaS dashboard design comp for approval before implementation. If the comp is generated from an approved style/reference image, use `edit_image` with `image_path` instead.

```json
// create_image tool call
{
  "n": 1,
  "use_picture": true,
  "images": [
    {
      "prompt": "A complete SaaS analytics dashboard design comp, modern B2B product style, left sidebar navigation, top search bar, KPI cards, analytics charts, recent activity table, polished typography, subtle blue accent, light theme, high-fidelity UI mockup",
      "size": "1792x1024",
      "title": "SaaS Dashboard Comp"
    }
  ]
}
```

### Pattern 4. Edit with a single reference

User dragged `cover.png` and asked to recolor it with warm tones and add subtle grain.

```json
// edit_image tool call
{
  "n": 1,
  "images": [
    {
      "prompt": "Recolor this cover with warm tones (amber, soft red, gold), add subtle film grain, preserve original composition and subjects",
      "image_path": "/Users/me/cover.png"
    }
  ]
}
```

### Pattern 5. Referenced full design comp for user review before build

User picked one style comp and wants another complete page in that same direction.

```json
// edit_image tool call
{
  "n": 1,
  "use_picture": true,
  "images": [
    {
      "prompt": "Design the pricing page in the same visual style, type system, palette, grid, material language, and brand tone as the selected reference image. Create one complete page comp, not a style exploration.",
      "image_path": "/project/verdent-design/stage1/comp-2-editorial.png",
      "title": "Pricing Page"
    }
  ]
}
```

### Pattern 6. Edit with a mask

User provided an indoor lounge photo and a mask image, then asked to add a pink flamingo only inside the masked pool area.

```json
// edit_image tool call
{
  "n": 1,
  "images": [
    {
      "prompt": "A sunlit indoor lounge area with a pool containing a pink flamingo floating gracefully on the water surface, warm natural lighting, maintaining original architecture",
      "image_path": "/path/to/indoor-lounge.jpg",
      "mask": "/path/to/pool-mask.png"
    }
  ]
}
```

### Pattern 7. Multiple style directions (stage-1)

User wants 4 style directions for a landing page.

```json
// create_image tool call
{
  "n": 4,
  "use_styles": true,
  "images": [
    {
      "prompt": "Output one independent design comp (one cohesive page, not a collage or comparison) — Minimalist editorial landing page, generous whitespace, serif headings, muted earth tones",
      "title": "Minimalist Editorial",
      "palettes": ["#F5F0EB", "#1A1A2E", "#E94560"]
    },
    {
      "prompt": "Output one independent design comp (one cohesive page, not a collage or comparison) — Futuristic tech landing page, dark background, cyan neon accents, bold sans-serif",
      "title": "Futuristic Tech",
      "palettes": ["#0A0E1A", "#E8F4FF", "#00F0FF"]
    },
    {
      "prompt": "Output one independent design comp (one cohesive page, not a collage or comparison) — Playful illustration-driven landing page, rounded shapes, candy colors, hand-drawn feel",
      "title": "Playful Illustration",
      "palettes": ["#FFF8E7", "#FF6B6B", "#4ECDC4"]
    },
    {
      "prompt": "Output one independent design comp (one cohesive page, not a collage or comparison) — Premium luxury landing page, black and gold palette, elegant serif typography, editorial photography",
      "title": "Premium Luxury",
      "palettes": ["#0D0D0D", "#F5F5F5", "#C9A84C"]
    }
  ]
}
```

## Do and Don't

**Do**

- Add `use_picture=true` only for complete design comps, or `use_styles=true` only for stage-1 style direction images. Both flags are valid on `create_image` and `edit_image`. Omit both for normal asset generation/editing.
- Craft a faithful, tight image prompt from the user's intent.
- Pass drag or `@`-mentioned image paths verbatim into `image_path`.
- Use `mask` only when the user provides a mask image path or explicitly asks for masked-region editing.
- Set `n` equal to the `images` array length.

**Don't**

- Don't use the old CLI form `verdent-image generate` / `verdent-image edit`. Use `create_image` / `edit_image` tool calls directly.
- Don't pass `title` without `use_picture=true` or `use_styles=true`.
- Don't use `palettes` without `use_styles=true`.
- Don't combine `use_picture` and `use_styles` in the same call.
- Don't use `use_picture` outside complete design comp generation.
- Don't use `use_styles` outside stage-1 style direction generation.
- Don't add `use_picture` or `use_styles` to ordinary generated assets, component images, illustrations, supporting artwork, photos, covers, product shots, hero art, backgrounds, or reference-based asset edits.

## Troubleshooting

- **Partial failure warning.** Some `images[i]` items may fail while others succeed. Check `warnings` (on `create_image`) or the `Partial failures:` text prefix (on `edit_image`) for details.
- **Error about reference path not found.** Verify the path exists before retrying. Do not retry with the same invalid path.
- **Very long edits.** Image generation may take tens of seconds. Do not retry on the first wait.
- **`is_error: true` response.** All items failed. Check the error message and fix the inputs.
