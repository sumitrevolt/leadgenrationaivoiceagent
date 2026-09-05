# Stage 3 — Extended Pages

Goal: design additional pages beyond the primary screen, confirm with the user, then restore them all into working frontend code — maintaining the same style direction chosen in stage 1.

## When to run this stage

Run **only** when the user explicitly confirms they want to design other related pages (asked at the end of stage 2). Do not assume or auto-trigger.

## 3a. Per-page comps

Before generating the additional page designs, tell the user — in plain language and in their own conversation language — that producing these page designs is expected to take **about 5–10 minutes**. Phrase it as an estimate (e.g. "around 5–10 minutes" / "around 5–10 minutes"). Do not use the words "stage", "phase", or any internal step numbers.

1. **Enumerate every additional page first.** List the pages back to the user before generating, so they can correct gaps cheaply.
2. **Generate one image per page in the chosen style.** Same type system, palette, grid, and decorative language as the picked stage-1 comp. This is now a design system — not exploration. Drift between pages reads as carelessness. Pass the picked stage-1 comp path via `edit_image` with `use_picture=true`, with each `images[i]` containing `image_path="/path/to/comp.png"` and page-specific `title` on every per-page comp call so the selected style anchor and review identity are explicit.
3. **Include major states as separate frames where relevant** — empty, loaded, modal, error.
4. Save under `<project-root>/verdent-design/stage2/pages/` with names `page-{n}-{name}.png`.

Example `edit_image` tool call:

```json
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

## 3b. Product spec image

A separate image (or set of images) that explains the product to a **non-developer**.

**Content:**
- User journey
- Page flow
- What each screen does, in plain language
- Data model (if applicable)
- Who-can-do-what for full-stack (role × permission map)

**Visual language:** diagram, flowchart, annotated wireframe blocks. Plain, legible, labeled. The image's color style may stay consistent with the product's design style, but it is **not** a beautified design comp.

**Hard rule:** do not embed the per-page design comps inside the spec image. They are separate artifacts with separate audiences (a designer reads comps; a stakeholder reads the spec).

Save under `<project-root>/verdent-design/stage2/spec/` with names `spec-{n}-{topic}.png`.

Skip this artifact entirely for simple requirements (e.g. just adding a few more static pages).

## Gate: confirm before restoration

Present the page designs and spec to the user. Confirm:
- The page list is complete.
- The spec matches their intent.

**Do not begin restoring new pages until the user confirms.**

## 3c. Restore all new pages

Before you start restoring the new pages into runnable code, tell the user — in plain language and in their own conversation language — that turning these page designs into working versions that run in the browser is expected to take **about 15–30 minutes**. Phrase it as an estimate (e.g. "around 15–30 minutes" / "around 15–30 minutes"). Do not use the words "stage", "phase", or any internal step numbers.

After user confirmation:

1. Apply the same high-fidelity restoration rules from `references/restoration.md` + `references/high-fidelity-assets.md` to every new page.
2. Maintain design consistency — same type system, palette, grid, interactions, and motion style as the primary screen.
3. Wire navigation between the primary screen (already live) and the new pages.
4. Save generated assets following the same folder conventions.
5. Run the same self-check: text 1:1, assets generated (full HF pipeline: icons as SVG, logos with solid + alpha), interactions wired, responsive at 360 / 768 / 1440.

## Gate: stage 3 complete

All new pages are restored, responsive, and wired into navigation. Run `ls` on output folders to verify. Then proceed to stage 4.

## Common mistakes

| Mistake | Why it fails | Fix |
|---|---|---|
| Drift in palette / type / grid across pages | Reads as careless; user loses trust in the system. | Pin the design system from the picked comp; reuse it. |
| Skipping page enumeration | The user discovers missing pages after restoration; rework is expensive. | List pages first, confirm, then generate. |
| Producing the spec image as a beautified design comp | Stakeholders cannot read flow; mixes audiences. | Keep spec diagrammatic and labeled. |
| Embedding comps inside the spec image | Same artifact serving two audiences = serves neither well. | Keep them as separate files. |
| Starting restoration before user confirms designs | User may want changes; premature code is thrown away. | Always wait for explicit confirmation. |
| Inconsistent navigation between primary screen and new pages | Product feels disconnected. | Wire routes and nav links for all pages together. |
