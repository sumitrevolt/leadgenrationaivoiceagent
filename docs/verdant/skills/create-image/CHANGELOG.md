# Changelog

## 2.2.1 — 2026-06-24

- Remove the outdated `use_styles=true` requirement that forced exactly 4 `images` items.
- Clarify that style mode keeps the normal `n` / `images.length` range of 1–4 and must use matching counts.

## 2.2.0 — 2026-06-23

- Remove the image tool `model` parameter from skill documentation and examples to match the current public tool schema.
- Keep image examples focused on exposed capability parameters such as `prompt`, `image_path`, `mask`, `size`, `background`, `output_format`, `title`, and `palettes`.
- Document `mask` as an Alpha-channel mask for local edit regions.

## 2.1.0 — 2026-06-16

- Fix workflow intent flag documentation: both `create_image` and `edit_image` support top-level `use_styles` and `use_picture`.
- Bind `title` to `use_styles=true` or `use_picture=true` on both tools.
- Document referenced page/screen design comps as `edit_image + use_picture=true + image_path + title`; ordinary asset edits still omit both intent flags.

---

## 2.0.0 — 2026-06-16

- **Breaking**: Migrate from `verdent-image` CLI commands to `create_image` / `edit_image` tool calls.
- Replace all bash command examples with JSON tool-call format.
- `create_image`: top-level params `n`, `images`, `use_styles`, `use_picture`; all generation params (`size`, `prompt`, `title`, `palettes`, etc.) are inside each `images[i]`.
- `edit_image`: top-level params `n`, `images`, `use_styles`, `use_picture`; each `images[i]` has `prompt`, `image_path` (required, string), `mask`, `title`, etc.
- `title` requires `use_styles` or `use_picture` on both image tools.
- Remove Bash Interception Contract section (no longer applicable).
- Add Key Differences table and Execution Model section.
- Update all Do/Don't and Troubleshooting guidance.

---

## 1.2.0 — 2026-05-30

- Restore `--use-picture` on the CLI surface and docs/examples, then restrict image intent flags to workflow-only usage: `--use-styles` is for stage-1 style direction images, `--use-picture` is for stage-3 complete page/screen design comps, and ordinary assets/component images/illustrations/supporting artwork must omit both.

---

## 1.1.0 — 2026-05-30

- Add `--title` (plain string) as a required parameter when using `--use-styles` or `--use-picture`, and `--palette` (JSON array of 3 `#RRGGBB` colors) as an additional requirement when using `--use-styles`.
- Clarify `--use-picture` and `--use-styles` are both optional flags, not mandatory one-of. Omit both for plain asset/image generation.
- `--use-picture`: design comp output mode only (style boards, page comps). Normal image/asset generation does not need this flag; `--use-picture` must be accompanied by `--title`.
- `--use-styles`: style-option generation mode; it must be accompanied by `--title` and `--palette`.
- `--title` is a plain string (not JSON array). Example: `--title "Minimalist"`.

---

## 1.0.6 — 2026-05-29

- Initial stable release with `verdent-image generate` and `verdent-image edit` commands.
